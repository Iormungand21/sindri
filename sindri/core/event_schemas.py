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
    duration_ms: Optional[float] = Field(
        None, description="Tool execution duration in milliseconds"
    )


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


class ModelRoutedData(BaseModel):
    """Payload for MODEL_ROUTED event (ROADMAP Item 10: Model-Aware Routing)."""

    task_id: str = Field(..., description="Task identifier")
    agent: str = Field(..., description="Agent name")
    routed_model: str = Field(..., description="Model selected by router")
    original_model: str = Field(..., description="Agent's default model")
    category: Optional[str] = Field(None, description="Task category (e.g., code_generation)")
    reason: str = Field(..., description="Routing reason (e.g., routed:code_generation)")
    score: Optional[float] = Field(None, description="Routing confidence score (0.0-1.0)")
    already_loaded: bool = Field(False, description="Whether model was already loaded")


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


class PlanAwaitingApprovalData(BaseModel):
    """Payload for PLAN_AWAITING_APPROVAL event."""

    task_id: str = Field(..., description="Task ID waiting for plan approval")
    plan_id: str = Field(..., description="Plan identifier (UUID)")
    step_count: int = Field(..., description="Number of steps in the plan")


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


# === Background Indexer Event Payloads (ROADMAP Item 4: Multi-Project Workspace Index) ===


class IndexQueuedData(BaseModel):
    """Payload for INDEX_QUEUED event."""

    project_path: str = Field(..., description="Absolute path to the project")
    project_name: str = Field(..., description="Display name of the project")
    priority: int = Field(..., description="Queue priority (1=highest, 10=lowest)")
    queue_position: int = Field(..., description="Position in the indexer queue")


class IndexStartedData(BaseModel):
    """Payload for INDEX_STARTED event."""

    project_path: str = Field(..., description="Absolute path to the project")
    project_name: str = Field(..., description="Display name of the project")
    total_files: int = Field(..., description="Total files to index (estimated)")
    force: bool = Field(default=False, description="Whether this is a forced re-index")


class IndexProgressData(BaseModel):
    """Payload for INDEX_PROGRESS event."""

    project_path: str = Field(..., description="Absolute path to the project")
    project_name: str = Field(..., description="Display name of the project")
    files_processed: int = Field(..., description="Number of files processed so far")
    total_files: int = Field(..., description="Total files to process")
    chunks_added: int = Field(..., description="Embedding chunks added so far")
    files_skipped: int = Field(default=0, description="Files skipped (unchanged)")
    percent_complete: float = Field(..., description="Progress percentage (0-100)")


class IndexCompletedData(BaseModel):
    """Payload for INDEX_COMPLETED event."""

    project_path: str = Field(..., description="Absolute path to the project")
    project_name: str = Field(..., description="Display name of the project")
    files_indexed: int = Field(..., description="Total files successfully indexed")
    files_skipped: int = Field(default=0, description="Files skipped (unchanged)")
    files_failed: int = Field(default=0, description="Files that failed to index")
    chunks_added: int = Field(..., description="Total embedding chunks created")
    chunks_removed: int = Field(default=0, description="Chunks removed (deleted/changed files)")
    duration_seconds: float = Field(..., description="Total indexing duration")


class IndexFailedData(BaseModel):
    """Payload for INDEX_FAILED event."""

    project_path: str = Field(..., description="Absolute path to the project")
    project_name: str = Field(..., description="Display name of the project")
    error: str = Field(..., description="Error message describing the failure")
    files_processed: int = Field(default=0, description="Files processed before failure")
    duration_seconds: float = Field(default=0.0, description="Duration until failure")


class IndexFileProcessedData(BaseModel):
    """Payload for INDEX_FILE_PROCESSED event (detailed progress)."""

    project_path: str = Field(..., description="Absolute path to the project")
    file_path: str = Field(..., description="Relative path of the indexed file")
    chunks_created: int = Field(..., description="Number of chunks created for this file")
    skipped: bool = Field(default=False, description="Whether file was skipped (unchanged)")


class IndexerStartedData(BaseModel):
    """Payload for INDEXER_STARTED event."""

    queued_projects: int = Field(..., description="Number of projects in the queue")
    auto_index_enabled: bool = Field(default=True, description="Whether auto-indexing is enabled")


class IndexerStoppedData(BaseModel):
    """Payload for INDEXER_STOPPED event."""

    reason: str = Field(default="user_requested", description="Reason for stopping")
    projects_indexed: int = Field(default=0, description="Projects indexed in this session")


class IndexerPausedData(BaseModel):
    """Payload for INDEXER_PAUSED event."""

    reason: str = Field(..., description="Reason for pausing (e.g., VRAM constraints)")
    resume_after_seconds: Optional[int] = Field(None, description="Expected resume time")


# === Performance Telemetry Stream Event Payloads (ROADMAP Item 7) ===


class VRAMSnapshot(BaseModel):
    """VRAM state at a point in time."""

    total_gb: float = Field(..., description="Total VRAM capacity in GB")
    used_gb: float = Field(..., description="VRAM currently in use in GB")
    free_gb: float = Field(..., description="Available VRAM in GB")
    loaded_models: list[str] = Field(default_factory=list, description="Currently loaded models")
    cache_hit_rate: float = Field(default=0.0, description="Model cache hit rate (0.0-1.0)")


class ConcurrencySnapshot(BaseModel):
    """Task concurrency state at a point in time."""

    running_tasks: int = Field(..., description="Currently executing tasks")
    pending_tasks: int = Field(..., description="Tasks waiting to execute")
    waiting_tasks: int = Field(default=0, description="Tasks waiting on dependencies")
    batch_size: int = Field(default=0, description="Current parallel batch size")


class AgentTimingStats(BaseModel):
    """Timing statistics for an agent."""

    agent_name: str = Field(..., description="Agent name")
    model_name: str = Field(default="", description="Model used by agent")
    total_iterations: int = Field(default=0, description="Total iterations executed")
    total_duration_ms: float = Field(default=0.0, description="Total execution time in ms")
    avg_iteration_ms: float = Field(default=0.0, description="Average iteration time in ms")
    p95_iteration_ms: Optional[float] = Field(None, description="95th percentile iteration time")


class ToolTimingStats(BaseModel):
    """Timing statistics for a tool."""

    tool_name: str = Field(..., description="Tool name")
    call_count: int = Field(default=0, description="Total number of calls")
    total_duration_ms: float = Field(default=0.0, description="Total execution time in ms")
    avg_duration_ms: float = Field(default=0.0, description="Average execution time in ms")
    success_rate: float = Field(default=1.0, description="Success rate (0.0-1.0)")
    p95_duration_ms: Optional[float] = Field(None, description="95th percentile duration")


class TelemetryTickData(BaseModel):
    """Payload for TELEMETRY_TICK event (periodic updates every 2 seconds)."""

    timestamp: float = Field(..., description="Unix timestamp of the tick")
    session_id: Optional[str] = Field(None, description="Active session ID")
    vram: VRAMSnapshot = Field(..., description="Current VRAM state")
    concurrency: ConcurrencySnapshot = Field(..., description="Current task concurrency state")
    session_duration_seconds: float = Field(default=0.0, description="Current session duration")
    current_agent: Optional[str] = Field(None, description="Currently executing agent")
    current_iteration: int = Field(default=0, description="Current iteration number")


class TelemetrySnapshotData(BaseModel):
    """Payload for TELEMETRY_SNAPSHOT event (full dump on demand or session end)."""

    timestamp: float = Field(..., description="Unix timestamp of the snapshot")
    session_id: str = Field(..., description="Session ID")
    session_duration_seconds: float = Field(..., description="Total session duration")
    vram: VRAMSnapshot = Field(..., description="VRAM state")
    concurrency: ConcurrencySnapshot = Field(..., description="Task concurrency state")
    agent_stats: list[AgentTimingStats] = Field(
        default_factory=list, description="Per-agent timing statistics"
    )
    tool_stats: list[ToolTimingStats] = Field(
        default_factory=list, description="Per-tool timing statistics"
    )
    total_iterations: int = Field(default=0, description="Total iterations across all agents")
    total_tool_calls: int = Field(default=0, description="Total tool calls across all tools")
    llm_time_seconds: float = Field(default=0.0, description="Total LLM inference time")
    tool_time_seconds: float = Field(default=0.0, description="Total tool execution time")


# === Triggers & Automations events (ROADMAP Item 9) ===


class TriggerCreatedData(BaseModel):
    """Payload for TRIGGER_CREATED event."""

    trigger_id: str = Field(..., description="Trigger identifier (UUID)")
    name: str = Field(..., description="Trigger name")
    trigger_type: str = Field(..., description="Trigger type: cron, webhook, event")


class TriggerUpdatedData(BaseModel):
    """Payload for TRIGGER_UPDATED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    name: str = Field(..., description="Trigger name")
    fields_updated: list[str] = Field(
        default_factory=list, description="List of fields that were updated"
    )


class TriggerDeletedData(BaseModel):
    """Payload for TRIGGER_DELETED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    name: str = Field(..., description="Trigger name")


class TriggerEnabledData(BaseModel):
    """Payload for TRIGGER_ENABLED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    name: str = Field(..., description="Trigger name")


class TriggerDisabledData(BaseModel):
    """Payload for TRIGGER_DISABLED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    name: str = Field(..., description="Trigger name")


class TriggerStartedData(BaseModel):
    """Payload for TRIGGER_STARTED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    trigger_name: str = Field(..., description="Trigger name")
    trigger_type: str = Field(..., description="Trigger type: cron, webhook, event")
    run_id: str = Field(..., description="Trigger run identifier (UUID)")


class TriggerCompletedData(BaseModel):
    """Payload for TRIGGER_COMPLETED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    trigger_name: str = Field(..., description="Trigger name")
    run_id: str = Field(..., description="Trigger run identifier")
    task_id: Optional[str] = Field(None, description="Created task identifier")
    success: bool = Field(True, description="Whether the trigger execution succeeded")
    duration_ms: Optional[float] = Field(None, description="Execution duration in milliseconds")


class TriggerFailedData(BaseModel):
    """Payload for TRIGGER_FAILED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    trigger_name: str = Field(..., description="Trigger name")
    run_id: str = Field(..., description="Trigger run identifier")
    error: str = Field(..., description="Error message")
    duration_ms: Optional[float] = Field(None, description="Execution duration in milliseconds")


class TriggerRateLimitedData(BaseModel):
    """Payload for TRIGGER_RATE_LIMITED event."""

    trigger_id: str = Field(..., description="Trigger identifier")
    trigger_name: str = Field(..., description="Trigger name")
    rate_limit_per_minute: int = Field(..., description="Configured rate limit")


class TriggerSchedulerStartedData(BaseModel):
    """Payload for TRIGGER_SCHEDULER_STARTED event."""

    tick_interval_seconds: int = Field(..., description="Scheduler tick interval in seconds")


class TriggerSchedulerStoppedData(BaseModel):
    """Payload for TRIGGER_SCHEDULER_STOPPED event."""

    reason: str = Field(..., description="Reason for stopping")
    triggers_fired: int = Field(default=0, description="Total triggers fired during runtime")


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
    "PLAN_AWAITING_APPROVAL": PlanAwaitingApprovalData,
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
    # Background Indexer events (ROADMAP Item 4: Multi-Project Workspace Index)
    "INDEX_QUEUED": IndexQueuedData,
    "INDEX_STARTED": IndexStartedData,
    "INDEX_PROGRESS": IndexProgressData,
    "INDEX_COMPLETED": IndexCompletedData,
    "INDEX_FAILED": IndexFailedData,
    "INDEX_FILE_PROCESSED": IndexFileProcessedData,
    "INDEXER_STARTED": IndexerStartedData,
    "INDEXER_STOPPED": IndexerStoppedData,
    "INDEXER_PAUSED": IndexerPausedData,
    # Performance Telemetry Stream (ROADMAP Item 7)
    "TELEMETRY_TICK": TelemetryTickData,
    "TELEMETRY_SNAPSHOT": TelemetrySnapshotData,
    # Triggers & Automations (ROADMAP Item 9)
    "TRIGGER_CREATED": TriggerCreatedData,
    "TRIGGER_UPDATED": TriggerUpdatedData,
    "TRIGGER_DELETED": TriggerDeletedData,
    "TRIGGER_ENABLED": TriggerEnabledData,
    "TRIGGER_DISABLED": TriggerDisabledData,
    "TRIGGER_STARTED": TriggerStartedData,
    "TRIGGER_COMPLETED": TriggerCompletedData,
    "TRIGGER_FAILED": TriggerFailedData,
    "TRIGGER_RATE_LIMITED": TriggerRateLimitedData,
    "TRIGGER_SCHEDULER_STARTED": TriggerSchedulerStartedData,
    "TRIGGER_SCHEDULER_STOPPED": TriggerSchedulerStoppedData,
    # Model-Aware Routing (ROADMAP Item 10)
    "MODEL_ROUTED": ModelRoutedData,
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
