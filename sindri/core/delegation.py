"""Delegation: spawning child tasks from parent agents.

Phase 6.2: Pre-warming support for model caching.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
import structlog

from sindri.core.tasks import Task, TaskStatus
from sindri.core.events import Event, EventType
from sindri.core.scheduler import TaskScheduler
from sindri.agents.registry import AGENTS

if TYPE_CHECKING:
    from sindri.llm.manager import ModelManager

log = structlog.get_logger()


@dataclass
class DelegationRequest:
    """Request to delegate work to another agent."""

    target_agent: str
    task_description: str
    context: dict
    constraints: list[str]
    success_criteria: list[str]


class DelegationManager:
    """Handles parent-child task relationships.

    Phase 6.2: Supports model pre-warming during delegation.
    """

    def __init__(
        self,
        scheduler: TaskScheduler,
        state=None,
        model_manager: Optional["ModelManager"] = None,
        event_bus=None,
    ):
        self.scheduler = scheduler
        self.state = state  # SessionState for updating parent sessions
        self.model_manager = model_manager  # For pre-warming
        self.event_bus = event_bus
        log.info(
            "delegation_manager_initialized", prewarm_enabled=model_manager is not None
        )

    async def delegate(self, parent_task: Task, request: DelegationRequest) -> Task:
        """Create and schedule a child task.

        Phase 6.2: Triggers model pre-warming for the target agent.
        """
        agent = AGENTS.get(request.target_agent)
        if not agent:
            raise ValueError(f"Unknown agent: {request.target_agent}")

        # Verify parent can delegate to this agent
        parent_agent = AGENTS.get(parent_task.assigned_agent)
        if parent_agent and not parent_agent.can_delegate_to(request.target_agent):
            raise ValueError(
                f"{parent_task.assigned_agent} cannot delegate to {request.target_agent}"
            )

        # Phase 6.2: Pre-warm the target agent's model in background
        if self.model_manager:
            await self.model_manager.pre_warm(agent.model, agent.estimated_vram_gb)

        child = Task(
            parent_id=parent_task.id,
            description=request.task_description,
            task_type=agent.name,
            assigned_agent=request.target_agent,
            priority=parent_task.priority + 1,  # Children are lower priority
            context={
                "parent_context": parent_task.context,
                "delegation": request.context,
                "constraints": request.constraints,
                "success_criteria": request.success_criteria,
            },
        )

        # Add to parent's subtasks
        parent_task.add_subtask(child.id)
        parent_task.status = TaskStatus.WAITING

        # Schedule child
        self.scheduler.add_task(child)

        log.info(
            "task_delegated",
            parent_id=parent_task.id,
            child_id=child.id,
            from_agent=parent_task.assigned_agent,
            to_agent=request.target_agent,
            prewarm_triggered=self.model_manager is not None,
            description=request.task_description[:50],
        )
        if self.event_bus:
            self.event_bus.emit(
                Event(
                    type=EventType.DELEGATION_START,
                    data={
                        "task_id": child.id,
                        "parent_task_id": parent_task.id,
                        "parent_agent": parent_task.assigned_agent,
                        "child_agent": request.target_agent,
                        "task": request.task_description,
                    },
                    task_id=parent_task.id,
                )
            )

        return child

    async def child_completed(self, child: Task):
        """Handle child task completion."""

        if not child.parent_id:
            return

        parent = self.scheduler.get_task(child.parent_id)
        if not parent:
            return

        log.info(
            "child_completed",
            child_id=child.id,
            parent_id=parent.id,
            success=child.status == TaskStatus.COMPLETE,
        )
        if self.event_bus:
            self.event_bus.emit(
                Event(
                    type=EventType.DELEGATION_COMPLETE,
                    data={
                        "task_id": child.id,
                        "parent_task_id": parent.id,
                        "parent_agent": parent.assigned_agent,
                        "child_agent": child.assigned_agent,
                        "status": child.status.value,
                    },
                    task_id=parent.id,
                )
            )

        # Inject child result into parent's session
        if self.state and hasattr(parent, "session_id"):
            try:
                parent_session = await self.state.load_session(parent.session_id)
                if parent_session:
                    # Add tool result with child's output
                    result_text = (
                        f"Child task completed successfully!\n"
                        f"Agent: {child.assigned_agent}\n"
                        f"Task: {child.description}\n"
                        f"Result: {child.result.get('output', 'Task completed') if child.result else 'Task completed'}"
                    )
                    parent_session.add_turn("tool", result_text)
                    await self.state.save_session(parent_session)
                    log.info(
                        "injected_child_result_to_parent",
                        parent_id=parent.id,
                        child_id=child.id,
                    )
            except Exception as e:
                log.warning(
                    "failed_to_inject_child_result", parent_id=parent.id, error=str(e)
                )

        # Check if all children complete
        all_complete = all(
            self.scheduler.get_task(sid).status == TaskStatus.COMPLETE
            for sid in parent.subtask_ids
            if self.scheduler.get_task(sid)
        )

        if all_complete:
            log.info(
                "all_children_complete",
                parent_id=parent.id,
                num_children=len(parent.subtask_ids),
            )
            # Resume parent
            parent.status = TaskStatus.PENDING
            # Re-add to pending queue
            import heapq

            heapq.heappush(self.scheduler.pending, (parent.priority, parent.id))

    async def child_failed(self, child: Task):
        """Handle child task failure."""

        if not child.parent_id:
            return

        parent = self.scheduler.get_task(child.parent_id)
        if not parent:
            return

        log.warning(
            "child_failed", child_id=child.id, parent_id=parent.id, error=child.error
        )
        if self.event_bus:
            self.event_bus.emit(
                Event(
                    type=EventType.DELEGATION_FAILED,
                    data={
                        "task_id": child.id,
                        "parent_task_id": parent.id,
                        "parent_agent": parent.assigned_agent,
                        "child_agent": child.assigned_agent,
                        "error": child.error,
                    },
                    task_id=parent.id,
                )
            )

        # For now, fail the parent too
        # In future, could implement retry logic
        parent.status = TaskStatus.FAILED
        parent.error = f"Child task {child.id} failed: {child.error}"

    async def plan_approved(self, task_id: str, plan_id: str):
        """Handle plan approval - resume the waiting task.

        Called when a user approves a plan that a task was waiting for.

        Args:
            task_id: The task that was waiting for plan approval
            plan_id: The approved plan ID
        """
        task = self.scheduler.get_task(task_id)
        if not task:
            log.warning("plan_approved_task_not_found", task_id=task_id, plan_id=plan_id)
            return False

        if task.status != TaskStatus.WAITING:
            log.warning(
                "plan_approved_task_not_waiting",
                task_id=task_id,
                plan_id=plan_id,
                status=task.status.value,
            )
            return False

        # Verify this task was waiting for this plan
        pending_plan = task.metadata.get("pending_plan_id") if task.metadata else None
        if pending_plan != plan_id:
            log.warning(
                "plan_approved_plan_mismatch",
                task_id=task_id,
                expected=pending_plan,
                got=plan_id,
            )
            return False

        log.info("plan_approved_resuming_task", task_id=task_id, plan_id=plan_id)

        # Clear the pending plan from metadata
        if task.metadata:
            task.metadata.pop("pending_plan_id", None)

        # Resume the task
        task.status = TaskStatus.PENDING
        import heapq
        heapq.heappush(self.scheduler.pending, (task.priority, task.id))

        # Emit event for TUI
        if self.event_bus:
            self.event_bus.emit(
                Event(
                    type=EventType.PLAN_APPROVED,
                    data={
                        "task_id": task_id,
                        "plan_id": plan_id,
                        "agent": task.assigned_agent,
                    },
                    task_id=task_id,
                )
            )

        return True

    async def plan_rejected(self, task_id: str, plan_id: str, reason: Optional[str] = None):
        """Handle plan rejection - fail the waiting task.

        Called when a user rejects a plan that a task was waiting for.

        Args:
            task_id: The task that was waiting for plan approval
            plan_id: The rejected plan ID
            reason: Optional rejection reason
        """
        task = self.scheduler.get_task(task_id)
        if not task:
            log.warning("plan_rejected_task_not_found", task_id=task_id, plan_id=plan_id)
            return False

        if task.status != TaskStatus.WAITING:
            log.warning(
                "plan_rejected_task_not_waiting",
                task_id=task_id,
                plan_id=plan_id,
                status=task.status.value,
            )
            return False

        log.info("plan_rejected_failing_task", task_id=task_id, plan_id=plan_id, reason=reason)

        # Fail the task
        task.status = TaskStatus.FAILED
        task.error = f"Plan {plan_id} rejected: {reason or 'User rejected plan'}"

        # Emit event for TUI
        if self.event_bus:
            self.event_bus.emit(
                Event(
                    type=EventType.PLAN_REJECTED,
                    data={
                        "task_id": task_id,
                        "plan_id": plan_id,
                        "reason": reason,
                    },
                    task_id=task_id,
                )
            )

        return True
