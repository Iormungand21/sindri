"""Strongly-typed event payload schemas for API contract.

This module defines Pydantic models for all WebSocket event payloads,
enabling JSON Schema generation and TypeScript type auto-generation.

API Version: 1.0.0
"""

from typing import Optional, Any
from pydantic import BaseModel, Field

# API Contract Version
API_VERSION = "1.0.0"


# === Event Payload Models ===
# These define the expected structure of Event.data for each EventType


class TaskCreatedData(BaseModel):
    """Payload for TASK_CREATED event."""

    task_id: str = Field(..., description="Unique task identifier (UUID)")
    description: Optional[str] = Field(None, description="Task description")
    task: Optional[str] = Field(None, description="Task description (alias)")
    status: Optional[str] = Field(None, description="Initial task status")
    parent_id: Optional[str] = Field(None, description="Parent task ID if delegated")
    agent: Optional[str] = Field(None, description="Assigned agent name")


class TaskStatusChangedData(BaseModel):
    """Payload for TASK_STATUS_CHANGED event."""

    task_id: str = Field(..., description="Task identifier")
    status: str = Field(
        ..., description="New status: pending, running, waiting, complete, failed, cancelled"
    )


class AgentOutputData(BaseModel):
    """Payload for AGENT_OUTPUT event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name that produced output")
    text: str = Field(..., description="Agent's text output")


class ToolCalledData(BaseModel):
    """Payload for TOOL_CALLED event."""

    task_id: str = Field(..., description="Task identifier")
    name: str = Field(..., description="Tool name that was called")
    success: bool = Field(..., description="Whether the tool call succeeded")
    result: Optional[str] = Field(None, description="Tool output or error message")


class DelegationStartData(BaseModel):
    """Payload for DELEGATION_START event."""

    task_id: str = Field(..., description="Child task ID")
    parent_task_id: str = Field(..., description="Parent task ID")
    parent_agent: str = Field(..., description="Agent that delegated")
    child_agent: str = Field(..., description="Agent receiving delegation")
    task: str = Field(..., description="Delegated task description")


class DelegationCompleteData(BaseModel):
    """Payload for DELEGATION_COMPLETE event."""

    task_id: str = Field(..., description="Child task ID")
    parent_task_id: str = Field(..., description="Parent task ID")
    parent_agent: str = Field(..., description="Agent that delegated")
    child_agent: str = Field(..., description="Agent that completed task")
    status: str = Field(..., description="Final status of child task")


class DelegationFailedData(BaseModel):
    """Payload for DELEGATION_FAILED event."""

    task_id: str = Field(..., description="Child task ID")
    parent_task_id: str = Field(..., description="Parent task ID")
    parent_agent: str = Field(..., description="Agent that delegated")
    child_agent: str = Field(..., description="Agent that failed")
    error: Optional[str] = Field(None, description="Error message")


class ModelLoadedData(BaseModel):
    """Payload for MODEL_LOADED event."""

    model: str = Field(..., description="Model name that was loaded")
    task_id: Optional[str] = Field(None, description="Task that triggered loading")
    agent: Optional[str] = Field(None, description="Agent using the model")
    vram_gb: Optional[float] = Field(None, description="VRAM consumed in GB")


class ModelUnloadedData(BaseModel):
    """Payload for MODEL_UNLOADED event."""

    model: str = Field(..., description="Model name that was unloaded")
    reason: Optional[str] = Field(None, description="Reason for unloading")


class ModelDegradedData(BaseModel):
    """Payload for MODEL_DEGRADED event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    primary_model: str = Field(..., description="Original model that couldn't load")
    fallback_model: str = Field(..., description="Fallback model being used")
    reason: Optional[str] = Field(None, description="Reason for degradation")


class ErrorData(BaseModel):
    """Payload for ERROR event."""

    task_id: Optional[str] = Field(None, description="Task identifier if applicable")
    error: str = Field(..., description="Error message")
    error_type: Optional[str] = Field(
        None,
        description="Error category: model_load_failure, task_failure, agent_stuck, task_exception",
    )
    agent: Optional[str] = Field(None, description="Agent name if applicable")
    model: Optional[str] = Field(None, description="Model name if applicable")
    fallback_model: Optional[str] = Field(None, description="Fallback model if tried")
    description: Optional[str] = Field(None, description="Task description excerpt")
    reason: Optional[str] = Field(None, description="Detailed reason")
    nudge_count: Optional[int] = Field(None, description="Number of recovery attempts")
    suggestion: Optional[str] = Field(None, description="Suggested action")


class IterationStartData(BaseModel):
    """Payload for ITERATION_START event."""

    task_id: str = Field(..., description="Task identifier")
    iteration: int = Field(..., description="Current iteration number (1-indexed)")
    agent: str = Field(..., description="Agent name")


class IterationEndData(BaseModel):
    """Payload for ITERATION_END event."""

    task_id: str = Field(..., description="Task identifier")
    iteration: int = Field(..., description="Completed iteration number")
    duration_ms: Optional[float] = Field(None, description="Iteration duration in milliseconds")


class IterationWarningData(BaseModel):
    """Payload for ITERATION_WARNING event."""

    task_id: str = Field(..., description="Task identifier")
    remaining: int = Field(..., description="Remaining iterations before limit")
    message: str = Field(..., description="Warning message")


class ParallelBatchStartData(BaseModel):
    """Payload for PARALLEL_BATCH_START event."""

    batch_id: str = Field(..., description="Unique batch identifier")
    task_ids: list[str] = Field(..., description="List of task IDs in this batch")
    count: int = Field(..., description="Number of tasks in batch")


class ParallelBatchEndData(BaseModel):
    """Payload for PARALLEL_BATCH_END event."""

    batch_id: str = Field(..., description="Batch identifier")
    completed: int = Field(..., description="Number of successfully completed tasks")
    failed: int = Field(..., description="Number of failed tasks")
    duration_ms: Optional[float] = Field(None, description="Total batch duration")


class StreamingStartData(BaseModel):
    """Payload for STREAMING_START event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    model: str = Field(..., description="Model generating the stream")


class StreamingTokenData(BaseModel):
    """Payload for STREAMING_TOKEN event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    token: str = Field(..., description="Individual token/text chunk")


class StreamingEndData(BaseModel):
    """Payload for STREAMING_END event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    content_length: int = Field(..., description="Total content length in characters")


class PlanProposedData(BaseModel):
    """Payload for PLAN_PROPOSED event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent proposing the plan")
    plan: dict[str, Any] = Field(..., description="Structured plan object")
    formatted: str = Field(..., description="Human-readable plan text")
    step_count: int = Field(..., description="Number of steps in plan")
    agents: Optional[list[str]] = Field(None, description="Agents involved in plan")
    estimated_vram_gb: Optional[float] = Field(None, description="Estimated VRAM needed")


class PlanApprovedData(BaseModel):
    """Payload for PLAN_APPROVED event."""

    task_id: str = Field(..., description="Task identifier")
    plan_id: Optional[str] = Field(None, description="Plan identifier")


class PlanRejectedData(BaseModel):
    """Payload for PLAN_REJECTED event."""

    task_id: str = Field(..., description="Task identifier")
    plan_id: Optional[str] = Field(None, description="Plan identifier")
    reason: Optional[str] = Field(None, description="Reason for rejection")


class PatternLearnedData(BaseModel):
    """Payload for PATTERN_LEARNED event."""

    task_id: str = Field(..., description="Task identifier")
    pattern_id: str = Field(..., description="Unique pattern identifier")
    agent: str = Field(..., description="Agent that learned the pattern")
    iterations: int = Field(..., description="Iterations taken to complete")
    tools: list[str] = Field(..., description="Tools used in the pattern")


class MetricsUpdatedData(BaseModel):
    """Payload for METRICS_UPDATED event."""

    task_id: str = Field(..., description="Task identifier")
    session_id: str = Field(..., description="Session identifier")
    iteration: int = Field(..., description="Current iteration number")
    duration_seconds: float = Field(..., description="Session duration so far")


class PolicyViolationData(BaseModel):
    """Payload for POLICY_VIOLATION event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    violation_type: str = Field(
        ..., description="Type: max_tool_calls, max_files_touched, max_runtime, file_scope, tool_budget"
    )
    reason: str = Field(..., description="Human-readable explanation")
    escalation_mode: Optional[str] = Field(None, description="Escalation mode: deny, warn, escalate")
    tool: Optional[str] = Field(None, description="Tool name if tool-related violation")
    current_value: Optional[float] = Field(None, description="Current value that exceeded limit")
    limit_value: Optional[float] = Field(None, description="Configured limit value")


class PolicyWarningData(BaseModel):
    """Payload for POLICY_WARNING event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    warning_type: str = Field(..., description="Type of warning")
    message: str = Field(..., description="Warning message")
    percent_used: Optional[float] = Field(None, description="Percentage of limit used")


class PolicyEscalationData(BaseModel):
    """Payload for POLICY_ESCALATION event."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    escalation_type: str = Field(..., description="Type of escalation")
    reason: str = Field(..., description="Why escalation was triggered")
    context: Optional[str] = Field(None, description="Additional context")


# === Plan-First Execution Event Payloads (ROADMAP.md Item 2) ===


class PlanPersistedData(BaseModel):
    """Payload for PLAN_PERSISTED event."""

    plan_id: str = Field(..., description="Plan identifier (UUID)")
    task_summary: str = Field(..., description="Summary of the planned task")
    step_count: int = Field(..., description="Number of steps in the plan")
    agents: list[str] = Field(default_factory=list, description="Agents involved in plan")


class PlanExecutionStartedData(BaseModel):
    """Payload for PLAN_EXECUTION_STARTED event."""

    plan_id: str = Field(..., description="Plan identifier")
    task_summary: str = Field(..., description="Task summary")
    steps: int = Field(..., description="Total number of steps")


class PlanExecutionPausedData(BaseModel):
    """Payload for PLAN_EXECUTION_PAUSED event."""

    plan_id: str = Field(..., description="Plan identifier")
    current_step: int = Field(..., description="Step number that caused pause")
    reason: str = Field(..., description="Reason for pause")


class PlanExecutionResumedData(BaseModel):
    """Payload for PLAN_EXECUTION_RESUMED event."""

    plan_id: str = Field(..., description="Plan identifier")
    from_step: int = Field(..., description="Step number resuming from")


class StepAwaitingApprovalData(BaseModel):
    """Payload for STEP_AWAITING_APPROVAL event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number (1-indexed)")
    description: str = Field(..., description="Step description")
    agent: str = Field(..., description="Agent that will execute this step")


class StepApprovedData(BaseModel):
    """Payload for STEP_APPROVED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")


class StepRejectedData(BaseModel):
    """Payload for STEP_REJECTED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    reason: Optional[str] = Field(None, description="Rejection reason")


class StepStartedData(BaseModel):
    """Payload for STEP_STARTED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    description: str = Field(..., description="Step description")
    agent: str = Field(..., description="Agent executing this step")


class StepCheckpointedData(BaseModel):
    """Payload for STEP_CHECKPOINTED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    iteration: int = Field(..., description="Iteration count at checkpoint")


class StepCompletedData(BaseModel):
    """Payload for STEP_COMPLETED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    iterations_used: int = Field(..., description="Total iterations used")
    files_modified: list[str] = Field(default_factory=list, description="Files modified")


class StepFailedData(BaseModel):
    """Payload for STEP_FAILED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    error: str = Field(..., description="Error message")


class StepResultPendingData(BaseModel):
    """Payload for STEP_RESULT_PENDING event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    output: str = Field(..., description="Step output (may be truncated)")
    files_modified: list[str] = Field(default_factory=list, description="Files modified")


class StepResultAcceptedData(BaseModel):
    """Payload for STEP_RESULT_ACCEPTED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")


class StepResultRejectedData(BaseModel):
    """Payload for STEP_RESULT_REJECTED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")
    reason: Optional[str] = Field(None, description="Rejection reason")


class StepRerunRequestedData(BaseModel):
    """Payload for STEP_RERUN_REQUESTED event."""

    step_id: str = Field(..., description="Step identifier")
    step_number: int = Field(..., description="Step number")


# === Event Type to Payload Model Mapping ===

EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "TASK_CREATED": TaskCreatedData,
    "TASK_STATUS_CHANGED": TaskStatusChangedData,
    "AGENT_OUTPUT": AgentOutputData,
    "TOOL_CALLED": ToolCalledData,
    "DELEGATION_START": DelegationStartData,
    "DELEGATION_COMPLETE": DelegationCompleteData,
    "DELEGATION_FAILED": DelegationFailedData,
    "MODEL_LOADED": ModelLoadedData,
    "MODEL_UNLOADED": ModelUnloadedData,
    "MODEL_DEGRADED": ModelDegradedData,
    "ERROR": ErrorData,
    "ITERATION_START": IterationStartData,
    "ITERATION_END": IterationEndData,
    "ITERATION_WARNING": IterationWarningData,
    "PARALLEL_BATCH_START": ParallelBatchStartData,
    "PARALLEL_BATCH_END": ParallelBatchEndData,
    "STREAMING_START": StreamingStartData,
    "STREAMING_TOKEN": StreamingTokenData,
    "STREAMING_END": StreamingEndData,
    "PLAN_PROPOSED": PlanProposedData,
    "PLAN_APPROVED": PlanApprovedData,
    "PLAN_REJECTED": PlanRejectedData,
    "PATTERN_LEARNED": PatternLearnedData,
    "METRICS_UPDATED": MetricsUpdatedData,
    "POLICY_VIOLATION": PolicyViolationData,
    "POLICY_WARNING": PolicyWarningData,
    "POLICY_ESCALATION": PolicyEscalationData,
    # Plan-First Execution events (ROADMAP.md Item 2)
    "PLAN_PERSISTED": PlanPersistedData,
    "PLAN_EXECUTION_STARTED": PlanExecutionStartedData,
    "PLAN_EXECUTION_PAUSED": PlanExecutionPausedData,
    "PLAN_EXECUTION_RESUMED": PlanExecutionResumedData,
    "STEP_AWAITING_APPROVAL": StepAwaitingApprovalData,
    "STEP_APPROVED": StepApprovedData,
    "STEP_REJECTED": StepRejectedData,
    "STEP_STARTED": StepStartedData,
    "STEP_CHECKPOINTED": StepCheckpointedData,
    "STEP_COMPLETED": StepCompletedData,
    "STEP_FAILED": StepFailedData,
    "STEP_RESULT_PENDING": StepResultPendingData,
    "STEP_RESULT_ACCEPTED": StepResultAcceptedData,
    "STEP_RESULT_REJECTED": StepResultRejectedData,
    "STEP_RERUN_REQUESTED": StepRerunRequestedData,
}


def get_event_schema(event_type: str) -> dict[str, Any]:
    """Get JSON Schema for a specific event type.

    Args:
        event_type: Event type name (e.g., "TASK_CREATED")

    Returns:
        JSON Schema dictionary for the event payload

    Raises:
        KeyError: If event type is not recognized
    """
    model = EVENT_PAYLOAD_MODELS[event_type]
    return model.model_json_schema()


def get_all_event_schemas() -> dict[str, dict[str, Any]]:
    """Get JSON Schema for all event types.

    Returns:
        Dictionary mapping event type names to their JSON Schemas
    """
    return {
        event_type: model.model_json_schema()
        for event_type, model in EVENT_PAYLOAD_MODELS.items()
    }


def validate_event_data(event_type: str, data: dict[str, Any]) -> BaseModel:
    """Validate event data against its schema.

    Args:
        event_type: Event type name
        data: Event data payload to validate

    Returns:
        Validated Pydantic model instance

    Raises:
        KeyError: If event type is not recognized
        ValidationError: If data doesn't match schema
    """
    model = EVENT_PAYLOAD_MODELS[event_type]
    return model(**data)
