"""Plan execution with approval gates and step-level checkpointing.

This module implements Plan-First Execution (ROADMAP.md Item 2):
1. Persist plans with user approval gates
2. Step-level checkpointing and re-run of individual steps
3. Partial results + explicit acceptance per step

## Two Modes of Plan Execution

### Mode 1: Agent-Guided Execution (Default)
When an agent proposes a plan via ProposePlanTool:
- The plan is persisted to the database with PROPOSED status
- The task pauses with WAITING status until the user approves
- On approval, the task resumes and the agent continues execution
- The agent uses the plan as guidance but executes autonomously
- This integrates with the main HierarchicalAgentLoop orchestration

### Mode 2: Step-by-Step Execution (PlanExecutor)
For fine-grained control, use PlanExecutor directly:
- Execute plans step-by-step with approval gates per step
- Checkpoint support for crash recovery and resume
- Re-run individual steps that failed
- Explicit acceptance/rejection of step results

Mode 1 is used when agents propose plans during task execution.
Mode 2 is available via the REST API for programmatic plan execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import uuid
import json


class PlanStatus(str, Enum):
    """Status of an execution plan."""

    PROPOSED = "proposed"  # Plan created, awaiting user approval
    APPROVED = "approved"  # User approved, ready to execute
    REJECTED = "rejected"  # User rejected the plan
    EXECUTING = "executing"  # Currently executing steps
    PAUSED = "paused"  # Paused awaiting step approval
    COMPLETED = "completed"  # All steps completed successfully
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # User cancelled


class StepStatus(str, Enum):
    """Status of a plan step."""

    PENDING = "pending"  # Not yet started
    AWAITING_APPROVAL = "awaiting_approval"  # Waiting for user to approve start
    APPROVED = "approved"  # Approved to run
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Failed
    SKIPPED = "skipped"  # User chose to skip


class ApprovalStatus(str, Enum):
    """Approval status for steps."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class StepCheckpoint:
    """Checkpoint data for resuming a step.

    Stores the execution state at a point in time so the step
    can be resumed after interruption or failure.
    """

    step_id: str
    iteration: int
    session_id: Optional[str] = None
    messages: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "step_id": self.step_id,
            "iteration": self.iteration,
            "session_id": self.session_id,
            "messages": self.messages,
            "tool_results": self.tool_results,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepCheckpoint":
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            step_id=data.get("step_id", ""),
            iteration=data.get("iteration", 0),
            session_id=data.get("session_id"),
            messages=data.get("messages", []),
            tool_results=data.get("tool_results", []),
            timestamp=timestamp,
        )


@dataclass
class StepResult:
    """Result of executing a plan step.

    Contains the output, metrics, and any files modified during execution.
    """

    success: bool
    output: str
    iterations_used: int
    tool_calls: list[dict] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "iterations_used": self.iterations_used,
            "tool_calls": self.tool_calls,
            "files_modified": self.files_modified,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepResult":
        """Create from dictionary."""
        return cls(
            success=data.get("success", False),
            output=data.get("output", ""),
            iterations_used=data.get("iterations_used", 0),
            tool_calls=data.get("tool_calls", []),
            files_modified=data.get("files_modified", []),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PersistentPlanStep:
    """A plan step with persistence and approval tracking.

    Extends the basic PlanStep concept with:
    - Unique ID for database persistence
    - Execution status tracking
    - Checkpoint support for resume
    - Result storage
    - User approval workflow
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = ""
    step_number: int = 1
    description: str = ""
    agent: str = "huginn"
    status: StepStatus = StepStatus.PENDING
    dependencies: list[int] = field(default_factory=list)
    tool_hints: list[str] = field(default_factory=list)
    estimated_iterations: int = 5

    # Execution tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    iterations_used: int = 0

    # Checkpoint and session linkage
    child_task_id: Optional[str] = None
    session_id: Optional[str] = None
    checkpoint: Optional[StepCheckpoint] = None

    # Results
    result: Optional[StepResult] = None
    error: Optional[str] = None

    # Approval workflow
    approval_required: bool = True
    approval_status: Optional[ApprovalStatus] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    def is_ready(self, completed_steps: set[int]) -> bool:
        """Check if this step is ready to execute.

        A step is ready when all its dependencies have completed.
        """
        return all(dep in completed_steps for dep in self.dependencies)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "step_number": self.step_number,
            "description": self.description,
            "agent": self.agent,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "tool_hints": self.tool_hints,
            "estimated_iterations": self.estimated_iterations,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "iterations_used": self.iterations_used,
            "child_task_id": self.child_task_id,
            "session_id": self.session_id,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "approval_required": self.approval_required,
            "approval_status": self.approval_status.value if self.approval_status else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersistentPlanStep":
        """Create from dictionary."""
        # Parse datetimes
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        completed_at = data.get("completed_at")
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        approved_at = data.get("approved_at")
        if isinstance(approved_at, str):
            approved_at = datetime.fromisoformat(approved_at)

        # Parse nested objects
        checkpoint_data = data.get("checkpoint")
        checkpoint = StepCheckpoint.from_dict(checkpoint_data) if checkpoint_data else None

        result_data = data.get("result")
        result = StepResult.from_dict(result_data) if result_data else None

        # Parse enums
        status_str = data.get("status", "pending")
        status = StepStatus(status_str) if status_str else StepStatus.PENDING

        approval_status_str = data.get("approval_status")
        approval_status = ApprovalStatus(approval_status_str) if approval_status_str else None

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            plan_id=data.get("plan_id", ""),
            step_number=data.get("step_number", 1),
            description=data.get("description", ""),
            agent=data.get("agent", "huginn"),
            status=status,
            dependencies=data.get("dependencies", []),
            tool_hints=data.get("tool_hints", []),
            estimated_iterations=data.get("estimated_iterations", 5),
            started_at=started_at,
            completed_at=completed_at,
            iterations_used=data.get("iterations_used", 0),
            child_task_id=data.get("child_task_id"),
            session_id=data.get("session_id"),
            checkpoint=checkpoint,
            result=result,
            error=data.get("error"),
            approval_required=data.get("approval_required", True),
            approval_status=approval_status,
            approved_at=approved_at,
            rejection_reason=data.get("rejection_reason"),
        )


@dataclass
class PersistentPlan:
    """An execution plan with persistence and approval gates.

    Extends the basic ExecutionPlan concept with:
    - Unique ID for database persistence
    - Plan-level status tracking
    - Approval workflow (user must approve before execution)
    - Step-level tracking with individual approval gates
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    task_id: str = ""
    task_summary: str = ""
    rationale: str = ""
    risks: list[str] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PROPOSED
    total_estimated_vram_gb: float = 0.0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Steps
    steps: list[PersistentPlanStep] = field(default_factory=list)

    # Execution state
    current_step: int = 0  # 0 = not started, 1+ = step number

    def get_step(self, step_number: int) -> Optional[PersistentPlanStep]:
        """Get step by number (1-indexed)."""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None

    def get_step_by_id(self, step_id: str) -> Optional[PersistentPlanStep]:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_next_ready_step(self) -> Optional[PersistentPlanStep]:
        """Get the next step that's ready to execute.

        Returns the first pending step whose dependencies are all completed.
        """
        completed = {s.step_number for s in self.steps if s.status == StepStatus.COMPLETED}
        for step in sorted(self.steps, key=lambda s: s.step_number):
            if step.status == StepStatus.PENDING and step.is_ready(completed):
                return step
        return None

    def all_steps_complete(self) -> bool:
        """Check if all steps are complete."""
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps
        )

    def has_failed_steps(self) -> bool:
        """Check if any steps have failed."""
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def get_completed_steps(self) -> list[PersistentPlanStep]:
        """Get all completed steps."""
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    def get_pending_steps(self) -> list[PersistentPlanStep]:
        """Get all pending steps."""
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    def format_display(self) -> str:
        """Format plan for display in TUI/CLI."""
        lines = []
        lines.append(f"Plan: {self.task_summary}")
        lines.append(f"Status: {self.status.value}")
        lines.append("")

        for step in self.steps:
            status_icon = {
                StepStatus.PENDING: "[ ]",
                StepStatus.AWAITING_APPROVAL: "[?]",
                StepStatus.APPROVED: "[>]",
                StepStatus.RUNNING: "[~]",
                StepStatus.COMPLETED: "[+]",
                StepStatus.FAILED: "[X]",
                StepStatus.SKIPPED: "[-]",
            }.get(step.status, "[ ]")

            deps = (
                f" (after step {', '.join(map(str, step.dependencies))})"
                if step.dependencies
                else ""
            )
            lines.append(
                f"  {status_icon} {step.step_number}. [{step.agent}] {step.description}{deps}"
            )
            if step.tool_hints:
                lines.append(f"       Tools: {', '.join(step.tool_hints)}")

        lines.append("")
        if self.total_estimated_vram_gb > 0:
            lines.append(f"Estimated VRAM: ~{self.total_estimated_vram_gb:.1f}GB")

        if self.rationale:
            lines.append(f"Rationale: {self.rationale}")

        if self.risks:
            lines.append("Risks:")
            for risk in self.risks:
                lines.append(f"  - {risk}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "task_summary": self.task_summary,
            "rationale": self.rationale,
            "risks": self.risks,
            "status": self.status.value,
            "total_estimated_vram_gb": self.total_estimated_vram_gb,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersistentPlan":
        """Create from dictionary."""
        # Parse datetimes
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        approved_at = data.get("approved_at")
        if isinstance(approved_at, str):
            approved_at = datetime.fromisoformat(approved_at)

        completed_at = data.get("completed_at")
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        # Parse status
        status_str = data.get("status", "proposed")
        status = PlanStatus(status_str) if status_str else PlanStatus.PROPOSED

        # Parse steps
        steps_data = data.get("steps", [])
        steps = [PersistentPlanStep.from_dict(s) for s in steps_data]

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_id=data.get("session_id"),
            task_id=data.get("task_id", ""),
            task_summary=data.get("task_summary", ""),
            rationale=data.get("rationale", ""),
            risks=data.get("risks", []),
            status=status,
            total_estimated_vram_gb=data.get("total_estimated_vram_gb", 0.0),
            created_at=created_at,
            approved_at=approved_at,
            completed_at=completed_at,
            steps=steps,
            current_step=data.get("current_step", 0),
        )
