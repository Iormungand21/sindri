"""Delegation: spawning child tasks from parent agents."""

from dataclasses import dataclass
from typing import Optional
import structlog

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.agents.registry import AGENTS

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
    """Handles parent-child task relationships."""

    def __init__(self, scheduler: TaskScheduler, state=None):
        self.scheduler = scheduler
        self.state = state  # SessionState for updating parent sessions
        log.info("delegation_manager_initialized")

    async def delegate(
        self,
        parent_task: Task,
        request: DelegationRequest
    ) -> Task:
        """Create and schedule a child task."""

        agent = AGENTS.get(request.target_agent)
        if not agent:
            raise ValueError(f"Unknown agent: {request.target_agent}")

        # Verify parent can delegate to this agent
        parent_agent = AGENTS.get(parent_task.assigned_agent)
        if parent_agent and not parent_agent.can_delegate_to(request.target_agent):
            raise ValueError(
                f"{parent_task.assigned_agent} cannot delegate to {request.target_agent}"
            )

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
            }
        )

        # Add to parent's subtasks
        parent_task.add_subtask(child.id)
        parent_task.status = TaskStatus.WAITING

        # Schedule child
        self.scheduler.add_task(child)

        log.info("task_delegated",
                 parent_id=parent_task.id,
                 child_id=child.id,
                 from_agent=parent_task.assigned_agent,
                 to_agent=request.target_agent,
                 description=request.task_description[:50])

        return child

    async def child_completed(self, child: Task):
        """Handle child task completion."""

        if not child.parent_id:
            return

        parent = self.scheduler.get_task(child.parent_id)
        if not parent:
            return

        log.info("child_completed",
                 child_id=child.id,
                 parent_id=parent.id,
                 success=child.status == TaskStatus.COMPLETE)

        # Inject child result into parent's session
        if self.state and hasattr(parent, 'session_id'):
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
                    log.info("injected_child_result_to_parent",
                             parent_id=parent.id,
                             child_id=child.id)
            except Exception as e:
                log.warning("failed_to_inject_child_result",
                           parent_id=parent.id,
                           error=str(e))

        # Check if all children complete
        all_complete = all(
            self.scheduler.get_task(sid).status == TaskStatus.COMPLETE
            for sid in parent.subtask_ids
            if self.scheduler.get_task(sid)
        )

        if all_complete:
            log.info("all_children_complete",
                     parent_id=parent.id,
                     num_children=len(parent.subtask_ids))
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

        log.warning("child_failed",
                    child_id=child.id,
                    parent_id=parent.id,
                    error=child.error)

        # For now, fail the parent too
        # In future, could implement retry logic
        parent.status = TaskStatus.FAILED
        parent.error = f"Child task {child.id} failed: {child.error}"
