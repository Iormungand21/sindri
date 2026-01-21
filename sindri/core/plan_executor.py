"""Plan executor for step-by-step execution with approval gates.

This module implements the core execution logic for Plan-First Execution
(ROADMAP.md Item 2), orchestrating step-by-step execution with checkpointing
and user approval gates.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Awaitable
import structlog

from sindri.core.plan_execution import (
    PersistentPlan,
    PersistentPlanStep,
    PlanStatus,
    StepStatus,
    StepCheckpoint,
    StepResult,
    ApprovalStatus,
)
from sindri.core.events import EventBus, Event, EventType
from sindri.persistence.plans import PlanStore

log = structlog.get_logger()


@dataclass
class PlanExecutorConfig:
    """Configuration for plan executor."""

    # Checkpoint every N iterations
    checkpoint_interval: int = 3

    # Timeout for step execution (seconds)
    step_timeout: float = 600.0

    # Auto-approve steps that don't require explicit approval
    auto_approve_simple_steps: bool = False

    # Maximum time to wait for user approval (seconds)
    approval_timeout: float = 300.0


@dataclass
class PlanExecutionResult:
    """Result of executing a complete plan."""

    success: bool
    plan: PersistentPlan
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


class PlanExecutor:
    """Executes plans step-by-step with approval gates and checkpointing.

    This class orchestrates the execution of persistent plans, handling:
    - Step-by-step execution with dependency resolution
    - User approval gates before and after steps
    - Checkpoint saving for crash recovery
    - Step re-run and resume capabilities
    """

    def __init__(
        self,
        plan_store: PlanStore,
        event_bus: Optional[EventBus] = None,
        config: Optional[PlanExecutorConfig] = None,
        step_executor: Optional[Callable[[PersistentPlanStep], Awaitable[StepResult]]] = None,
    ):
        """Initialize plan executor.

        Args:
            plan_store: Store for plan persistence
            event_bus: Event bus for UI notifications
            config: Executor configuration
            step_executor: Callback to execute individual steps (if not provided,
                          steps will need to be executed externally)
        """
        self.plan_store = plan_store
        self.event_bus = event_bus or EventBus()
        self.config = config or PlanExecutorConfig()
        self._step_executor = step_executor

        # Approval state (for external approval handling)
        self._pending_approval: Optional[str] = None  # step_id awaiting approval
        self._approval_event = asyncio.Event()
        self._approval_result: Optional[ApprovalStatus] = None

    def _emit(self, event_type: EventType, data: dict, task_id: Optional[str] = None):
        """Emit an event to the event bus."""
        self.event_bus.emit(Event(type=event_type, data=data, task_id=task_id))

    # ============== Plan Execution ==============

    async def execute_plan(self, plan: PersistentPlan) -> PlanExecutionResult:
        """Execute a plan step-by-step with approval gates.

        Args:
            plan: The plan to execute (must be in APPROVED status)

        Returns:
            PlanExecutionResult with execution outcome
        """
        start_time = datetime.now()

        # Validate plan status
        if plan.status != PlanStatus.APPROVED:
            return PlanExecutionResult(
                success=False,
                plan=plan,
                error=f"Plan must be in APPROVED status, got {plan.status.value}",
            )

        # Update plan status to EXECUTING
        plan.status = PlanStatus.EXECUTING
        await self.plan_store.update_plan_status(plan.id, PlanStatus.EXECUTING)

        self._emit(
            EventType.PLAN_EXECUTION_STARTED,
            {"plan_id": plan.id, "task_summary": plan.task_summary, "steps": len(plan.steps)},
            task_id=plan.task_id,
        )

        completed = 0
        failed = 0
        skipped = 0

        try:
            # Execute steps in dependency order
            while True:
                next_step = plan.get_next_ready_step()
                if not next_step:
                    # Check if we're done or stuck
                    if plan.all_steps_complete():
                        break
                    elif plan.has_failed_steps():
                        # Cannot proceed due to failed dependencies
                        plan.status = PlanStatus.FAILED
                        await self.plan_store.update_plan_status(
                            plan.id, PlanStatus.FAILED
                        )
                        return PlanExecutionResult(
                            success=False,
                            plan=plan,
                            completed_steps=completed,
                            failed_steps=failed,
                            skipped_steps=skipped,
                            error="Plan failed due to step failures",
                            duration_seconds=(datetime.now() - start_time).total_seconds(),
                        )
                    else:
                        # All remaining steps have unmet dependencies
                        break

                # Request approval if required
                if next_step.approval_required and not self.config.auto_approve_simple_steps:
                    approval = await self._await_step_approval(next_step)
                    if approval == ApprovalStatus.REJECTED:
                        # User rejected - skip this step
                        next_step.status = StepStatus.SKIPPED
                        await self.plan_store.update_step_status(
                            next_step.id, StepStatus.SKIPPED
                        )
                        skipped += 1
                        continue

                # Execute the step
                result = await self.execute_step(next_step)

                if result.success:
                    completed += 1

                    # Request result acceptance if needed
                    if next_step.approval_required:
                        acceptance = await self._await_result_acceptance(next_step, result)
                        if acceptance == ApprovalStatus.REJECTED:
                            # User rejected result - mark as failed
                            next_step.status = StepStatus.FAILED
                            next_step.error = "Result rejected by user"
                            await self.plan_store.update_step_status(
                                next_step.id,
                                StepStatus.FAILED,
                                error="Result rejected by user",
                            )
                            failed += 1
                            continue
                else:
                    failed += 1

            # Plan completed
            if failed == 0:
                plan.status = PlanStatus.COMPLETED
                plan.completed_at = datetime.now()
                await self.plan_store.update_plan_status(
                    plan.id, PlanStatus.COMPLETED, completed_at=plan.completed_at
                )
            else:
                plan.status = PlanStatus.FAILED
                await self.plan_store.update_plan_status(plan.id, PlanStatus.FAILED)

            return PlanExecutionResult(
                success=failed == 0,
                plan=plan,
                completed_steps=completed,
                failed_steps=failed,
                skipped_steps=skipped,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except asyncio.CancelledError:
            # Plan was cancelled
            plan.status = PlanStatus.CANCELLED
            await self.plan_store.update_plan_status(plan.id, PlanStatus.CANCELLED)
            raise

        except Exception as e:
            log.error("plan_execution_error", plan_id=plan.id, error=str(e))
            plan.status = PlanStatus.FAILED
            await self.plan_store.update_plan_status(plan.id, PlanStatus.FAILED)
            return PlanExecutionResult(
                success=False,
                plan=plan,
                completed_steps=completed,
                failed_steps=failed,
                skipped_steps=skipped,
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    async def execute_step(self, step: PersistentPlanStep) -> StepResult:
        """Execute a single step with checkpointing.

        Args:
            step: The step to execute

        Returns:
            StepResult with execution outcome
        """
        # Update step status
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now()
        await self.plan_store.update_step_status(
            step.id, StepStatus.RUNNING, started_at=step.started_at
        )

        self._emit(
            EventType.STEP_STARTED,
            {
                "step_id": step.id,
                "step_number": step.step_number,
                "description": step.description,
                "agent": step.agent,
            },
        )

        try:
            # Execute the step using the configured executor
            if self._step_executor:
                result = await self._step_executor(step)
            else:
                # No executor configured - create a placeholder result
                result = StepResult(
                    success=True,
                    output="Step execution delegated to external system",
                    iterations_used=0,
                )

            # Update step with result
            step.result = result
            step.iterations_used = result.iterations_used
            step.completed_at = datetime.now()

            if result.success:
                step.status = StepStatus.COMPLETED
                await self.plan_store.update_step_status(
                    step.id,
                    StepStatus.COMPLETED,
                    completed_at=step.completed_at,
                    iterations_used=step.iterations_used,
                )
                await self.plan_store.save_step_result(step.id, result)

                self._emit(
                    EventType.STEP_COMPLETED,
                    {
                        "step_id": step.id,
                        "step_number": step.step_number,
                        "iterations_used": result.iterations_used,
                        "files_modified": result.files_modified,
                    },
                )
            else:
                step.status = StepStatus.FAILED
                step.error = result.error
                await self.plan_store.update_step_status(
                    step.id,
                    StepStatus.FAILED,
                    completed_at=step.completed_at,
                    iterations_used=step.iterations_used,
                    error=result.error,
                )

                self._emit(
                    EventType.STEP_FAILED,
                    {
                        "step_id": step.id,
                        "step_number": step.step_number,
                        "error": result.error,
                    },
                )

            return result

        except Exception as e:
            log.error("step_execution_error", step_id=step.id, error=str(e))
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now()
            await self.plan_store.update_step_status(
                step.id,
                StepStatus.FAILED,
                completed_at=step.completed_at,
                error=str(e),
            )

            self._emit(
                EventType.STEP_FAILED,
                {"step_id": step.id, "step_number": step.step_number, "error": str(e)},
            )

            return StepResult(
                success=False, output="", iterations_used=0, error=str(e)
            )

    async def save_checkpoint(self, step: PersistentPlanStep, checkpoint: StepCheckpoint):
        """Save a checkpoint for a step.

        Args:
            step: The step being executed
            checkpoint: Checkpoint data to save
        """
        step.checkpoint = checkpoint
        await self.plan_store.save_step_checkpoint(step.id, checkpoint)

        self._emit(
            EventType.STEP_CHECKPOINTED,
            {
                "step_id": step.id,
                "step_number": step.step_number,
                "iteration": checkpoint.iteration,
            },
        )

    async def resume_step(self, step_id: str) -> Optional[StepResult]:
        """Resume a step from its last checkpoint.

        Args:
            step_id: The step ID to resume

        Returns:
            StepResult if step was resumed and completed, None if no checkpoint
        """
        step = await self.plan_store.load_step(step_id)
        if not step:
            log.warning("step_not_found", step_id=step_id)
            return None

        checkpoint = await self.plan_store.load_step_checkpoint(step_id)
        if not checkpoint:
            log.warning("no_checkpoint_for_step", step_id=step_id)
            return None

        # Reset step status to running
        step.status = StepStatus.RUNNING
        step.checkpoint = checkpoint
        await self.plan_store.update_step_status(step_id, StepStatus.RUNNING)

        log.info(
            "resuming_step",
            step_id=step_id,
            from_iteration=checkpoint.iteration,
        )

        # Execute from checkpoint
        return await self.execute_step(step)

    async def rerun_step(self, step_id: str) -> Optional[StepResult]:
        """Re-run a step from scratch.

        Args:
            step_id: The step ID to re-run

        Returns:
            StepResult if step was re-run, None if step not found
        """
        step = await self.plan_store.load_step(step_id)
        if not step:
            log.warning("step_not_found", step_id=step_id)
            return None

        # Reset step state
        step.status = StepStatus.PENDING
        step.started_at = None
        step.completed_at = None
        step.iterations_used = 0
        step.checkpoint = None
        step.result = None
        step.error = None

        # Clear checkpoint in database
        await self.plan_store.save_step_checkpoint(step_id, None)
        await self.plan_store.update_step_status(step_id, StepStatus.PENDING)

        self._emit(
            EventType.STEP_RERUN_REQUESTED,
            {"step_id": step_id, "step_number": step.step_number},
        )

        log.info("rerunning_step", step_id=step_id)

        # Execute fresh
        return await self.execute_step(step)

    # ============== Approval Handling ==============

    async def _await_step_approval(self, step: PersistentPlanStep) -> ApprovalStatus:
        """Wait for user approval to start a step.

        Args:
            step: The step awaiting approval

        Returns:
            ApprovalStatus from user
        """
        step.status = StepStatus.AWAITING_APPROVAL
        await self.plan_store.update_step_status(step.id, StepStatus.AWAITING_APPROVAL)

        self._emit(
            EventType.STEP_AWAITING_APPROVAL,
            {
                "step_id": step.id,
                "step_number": step.step_number,
                "description": step.description,
                "agent": step.agent,
            },
        )

        # Set up approval wait
        self._pending_approval = step.id
        self._approval_event.clear()
        self._approval_result = None

        # Wait for approval with timeout
        try:
            await asyncio.wait_for(
                self._approval_event.wait(), timeout=self.config.approval_timeout
            )
            result = self._approval_result or ApprovalStatus.APPROVED
        except asyncio.TimeoutError:
            log.warning("step_approval_timeout", step_id=step.id)
            result = ApprovalStatus.APPROVED  # Default to approve on timeout

        # Update step approval status
        if result == ApprovalStatus.APPROVED:
            step.approval_status = ApprovalStatus.APPROVED
            step.approved_at = datetime.now()
            step.status = StepStatus.APPROVED
            await self.plan_store.update_step_approval(
                step.id, ApprovalStatus.APPROVED, approved_at=step.approved_at
            )

            self._emit(
                EventType.STEP_APPROVED,
                {"step_id": step.id, "step_number": step.step_number},
            )
        else:
            step.approval_status = ApprovalStatus.REJECTED
            await self.plan_store.update_step_approval(
                step.id, ApprovalStatus.REJECTED, rejection_reason="User rejected"
            )

            self._emit(
                EventType.STEP_REJECTED,
                {"step_id": step.id, "step_number": step.step_number},
            )

        self._pending_approval = None
        return result

    async def _await_result_acceptance(
        self, step: PersistentPlanStep, result: StepResult
    ) -> ApprovalStatus:
        """Wait for user acceptance of a step result.

        Args:
            step: The step with result
            result: The result to accept/reject

        Returns:
            ApprovalStatus from user
        """
        self._emit(
            EventType.STEP_RESULT_PENDING,
            {
                "step_id": step.id,
                "step_number": step.step_number,
                "output": result.output[:500],  # Truncate for event
                "files_modified": result.files_modified,
            },
        )

        # Set up approval wait
        self._pending_approval = f"{step.id}:result"
        self._approval_event.clear()
        self._approval_result = None

        try:
            await asyncio.wait_for(
                self._approval_event.wait(), timeout=self.config.approval_timeout
            )
            approval = self._approval_result or ApprovalStatus.APPROVED
        except asyncio.TimeoutError:
            approval = ApprovalStatus.APPROVED  # Default to accept on timeout

        if approval == ApprovalStatus.APPROVED:
            self._emit(
                EventType.STEP_RESULT_ACCEPTED,
                {"step_id": step.id, "step_number": step.step_number},
            )
        else:
            self._emit(
                EventType.STEP_RESULT_REJECTED,
                {"step_id": step.id, "step_number": step.step_number},
            )

        self._pending_approval = None
        return approval

    def approve_pending(self, approval: ApprovalStatus = ApprovalStatus.APPROVED):
        """Approve or reject the pending step/result.

        Called by UI to respond to approval requests.

        Args:
            approval: The approval decision
        """
        if self._pending_approval:
            self._approval_result = approval
            self._approval_event.set()

    # ============== Plan Approval ==============

    async def approve_plan(self, plan_id: str) -> bool:
        """Approve a plan for execution.

        Args:
            plan_id: The plan ID to approve

        Returns:
            True if approved, False if plan not found or not in PROPOSED status
        """
        plan = await self.plan_store.load_plan(plan_id)
        if not plan:
            return False

        if plan.status != PlanStatus.PROPOSED:
            log.warning(
                "plan_not_in_proposed_status",
                plan_id=plan_id,
                status=plan.status.value,
            )
            return False

        plan.status = PlanStatus.APPROVED
        plan.approved_at = datetime.now()
        await self.plan_store.update_plan_status(
            plan_id, PlanStatus.APPROVED, approved_at=plan.approved_at
        )

        self._emit(
            EventType.PLAN_APPROVED,
            {"plan_id": plan_id, "task_id": plan.task_id, "task_summary": plan.task_summary},
            task_id=plan.task_id,
        )

        log.info("plan_approved", plan_id=plan_id)
        return True

    async def reject_plan(self, plan_id: str, reason: Optional[str] = None) -> bool:
        """Reject a plan.

        Args:
            plan_id: The plan ID to reject
            reason: Optional rejection reason

        Returns:
            True if rejected, False if plan not found
        """
        plan = await self.plan_store.load_plan(plan_id)
        if not plan:
            return False

        plan.status = PlanStatus.REJECTED
        await self.plan_store.update_plan_status(plan_id, PlanStatus.REJECTED)

        self._emit(
            EventType.PLAN_REJECTED,
            {"plan_id": plan_id, "task_id": plan.task_id, "reason": reason},
            task_id=plan.task_id,
        )

        log.info("plan_rejected", plan_id=plan_id, reason=reason)
        return True
