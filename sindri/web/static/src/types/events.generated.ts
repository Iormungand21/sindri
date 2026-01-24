/**
 * Auto-generated TypeScript types for Sindri WebSocket events.
 * API Version: 1.0.0
 *
 * DO NOT EDIT MANUALLY - regenerate with:
 *   python scripts/generate_typescript_types.py
 */

// === Event Payload Interfaces ===

/** Payload for TASK_CREATED event. */
export interface TASK_CREATEDData {
  /** Unique task identifier (UUID) */
  task_id: string;
  /** Task description */
  description?: string | null;
  /** Task description (alias) */
  task?: string | null;
  /** Initial task status */
  status?: string | null;
  /** Parent task ID if delegated */
  parent_id?: string | null;
  /** Assigned agent name */
  agent?: string | null;
}

/** Payload for TASK_STATUS_CHANGED event. */
export interface TASK_STATUS_CHANGEDData {
  /** Task identifier */
  task_id: string;
  /** New status: pending, running, waiting, complete, failed, cancelled */
  status: string;
}

/** Payload for AGENT_OUTPUT event. */
export interface AGENT_OUTPUTData {
  /** Task identifier */
  task_id: string;
  /** Agent name that produced output */
  agent: string;
  /** Agent's text output */
  text: string;
}

/** Payload for TOOL_CALLED event. */
export interface TOOL_CALLEDData {
  /** Task identifier */
  task_id: string;
  /** Tool name that was called */
  name: string;
  /** Whether the tool call succeeded */
  success: boolean;
  /** Tool output or error message */
  result?: string | null;
  /** Tool execution duration in milliseconds */
  duration_ms?: number | null;
}

/** Payload for DELEGATION_START event. */
export interface DELEGATION_STARTData {
  /** Child task ID */
  task_id: string;
  /** Parent task ID */
  parent_task_id: string;
  /** Agent that delegated */
  parent_agent: string;
  /** Agent receiving delegation */
  child_agent: string;
  /** Delegated task description */
  task: string;
}

/** Payload for DELEGATION_COMPLETE event. */
export interface DELEGATION_COMPLETEData {
  /** Child task ID */
  task_id: string;
  /** Parent task ID */
  parent_task_id: string;
  /** Agent that delegated */
  parent_agent: string;
  /** Agent that completed task */
  child_agent: string;
  /** Final status of child task */
  status: string;
}

/** Payload for DELEGATION_FAILED event. */
export interface DELEGATION_FAILEDData {
  /** Child task ID */
  task_id: string;
  /** Parent task ID */
  parent_task_id: string;
  /** Agent that delegated */
  parent_agent: string;
  /** Agent that failed */
  child_agent: string;
  /** Error message */
  error?: string | null;
}

/** Payload for MODEL_LOADED event. */
export interface MODEL_LOADEDData {
  /** Model name that was loaded */
  model: string;
  /** Task that triggered loading */
  task_id?: string | null;
  /** Agent using the model */
  agent?: string | null;
  /** VRAM consumed in GB */
  vram_gb?: number | null;
}

/** Payload for MODEL_UNLOADED event. */
export interface MODEL_UNLOADEDData {
  /** Model name that was unloaded */
  model: string;
  /** Reason for unloading */
  reason?: string | null;
}

/** Payload for MODEL_DEGRADED event. */
export interface MODEL_DEGRADEDData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Original model that couldn't load */
  primary_model: string;
  /** Fallback model being used */
  fallback_model: string;
  /** Reason for degradation */
  reason?: string | null;
}

/** Payload for ERROR event. */
export interface ERRORData {
  /** Task identifier if applicable */
  task_id?: string | null;
  /** Error message */
  error: string;
  /** Error category: model_load_failure, task_failure, agent_stuck, task_exception */
  error_type?: string | null;
  /** Agent name if applicable */
  agent?: string | null;
  /** Model name if applicable */
  model?: string | null;
  /** Fallback model if tried */
  fallback_model?: string | null;
  /** Task description excerpt */
  description?: string | null;
  /** Detailed reason */
  reason?: string | null;
  /** Number of recovery attempts */
  nudge_count?: number | null;
  /** Suggested action */
  suggestion?: string | null;
}

/** Payload for ITERATION_START event. */
export interface ITERATION_STARTData {
  /** Task identifier */
  task_id: string;
  /** Current iteration number (1-indexed) */
  iteration: number;
  /** Agent name */
  agent: string;
}

/** Payload for ITERATION_END event. */
export interface ITERATION_ENDData {
  /** Task identifier */
  task_id: string;
  /** Completed iteration number */
  iteration: number;
  /** Iteration duration in milliseconds */
  duration_ms?: number | null;
}

/** Payload for ITERATION_WARNING event. */
export interface ITERATION_WARNINGData {
  /** Task identifier */
  task_id: string;
  /** Remaining iterations before limit */
  remaining: number;
  /** Warning message */
  message: string;
}

/** Payload for PARALLEL_BATCH_START event. */
export interface PARALLEL_BATCH_STARTData {
  /** Unique batch identifier */
  batch_id: string;
  /** List of task IDs in this batch */
  task_ids: string[];
  /** Number of tasks in batch */
  count: number;
}

/** Payload for PARALLEL_BATCH_END event. */
export interface PARALLEL_BATCH_ENDData {
  /** Batch identifier */
  batch_id: string;
  /** Number of successfully completed tasks */
  completed: number;
  /** Number of failed tasks */
  failed: number;
  /** Total batch duration */
  duration_ms?: number | null;
}

/** Payload for STREAMING_START event. */
export interface STREAMING_STARTData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Model generating the stream */
  model: string;
}

/** Payload for STREAMING_TOKEN event. */
export interface STREAMING_TOKENData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Individual token/text chunk */
  token: string;
}

/** Payload for STREAMING_END event. */
export interface STREAMING_ENDData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Total content length in characters */
  content_length: number;
}

/** Payload for PLAN_PROPOSED event. */
export interface PLAN_PROPOSEDData {
  /** Task identifier */
  task_id: string;
  /** Agent proposing the plan */
  agent: string;
  /** Structured plan object */
  plan: Record<string, unknown>;
  /** Human-readable plan text */
  formatted: string;
  /** Number of steps in plan */
  step_count: number;
  /** Agents involved in plan */
  agents?: string[] | null;
  /** Estimated VRAM needed */
  estimated_vram_gb?: number | null;
}

/** Payload for PLAN_APPROVED event. */
export interface PLAN_APPROVEDData {
  /** Task identifier */
  task_id: string;
  /** Plan identifier */
  plan_id?: string | null;
}

/** Payload for PLAN_REJECTED event. */
export interface PLAN_REJECTEDData {
  /** Task identifier */
  task_id: string;
  /** Plan identifier */
  plan_id?: string | null;
  /** Reason for rejection */
  reason?: string | null;
}

/** Payload for PATTERN_LEARNED event. */
export interface PATTERN_LEARNEDData {
  /** Task identifier */
  task_id: string;
  /** Unique pattern identifier */
  pattern_id: string;
  /** Agent that learned the pattern */
  agent: string;
  /** Iterations taken to complete */
  iterations: number;
  /** Tools used in the pattern */
  tools: string[];
}

/** Payload for METRICS_UPDATED event. */
export interface METRICS_UPDATEDData {
  /** Task identifier */
  task_id: string;
  /** Session identifier */
  session_id: string;
  /** Current iteration number */
  iteration: number;
  /** Session duration so far */
  duration_seconds: number;
}

/** Payload for POLICY_VIOLATION event. */
export interface POLICY_VIOLATIONData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Type: max_tool_calls, max_files_touched, max_runtime, file_scope, tool_budget */
  violation_type: string;
  /** Human-readable explanation */
  reason: string;
  /** Escalation mode: deny, warn, escalate */
  escalation_mode?: string | null;
  /** Tool name if tool-related violation */
  tool?: string | null;
  /** Current value that exceeded limit */
  current_value?: number | null;
  /** Configured limit value */
  limit_value?: number | null;
}

/** Payload for POLICY_WARNING event. */
export interface POLICY_WARNINGData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Type of warning */
  warning_type: string;
  /** Warning message */
  message: string;
  /** Percentage of limit used */
  percent_used?: number | null;
}

/** Payload for POLICY_ESCALATION event. */
export interface POLICY_ESCALATIONData {
  /** Task identifier */
  task_id: string;
  /** Agent name */
  agent: string;
  /** Type of escalation */
  escalation_type: string;
  /** Why escalation was triggered */
  reason: string;
  /** Additional context */
  context?: string | null;
}

/** Payload for PLAN_PERSISTED event. */
export interface PLAN_PERSISTEDData {
  /** Plan identifier (UUID) */
  plan_id: string;
  /** Summary of the planned task */
  task_summary: string;
  /** Number of steps in the plan */
  step_count: number;
  /** Agents involved in plan */
  agents?: string[];
}

/** Payload for PLAN_AWAITING_APPROVAL event. */
export interface PLAN_AWAITING_APPROVALData {
  /** Task ID waiting for plan approval */
  task_id: string;
  /** Plan identifier (UUID) */
  plan_id: string;
  /** Number of steps in the plan */
  step_count: number;
}

/** Payload for PLAN_EXECUTION_STARTED event. */
export interface PLAN_EXECUTION_STARTEDData {
  /** Plan identifier */
  plan_id: string;
  /** Task summary */
  task_summary: string;
  /** Total number of steps */
  steps: number;
}

/** Payload for PLAN_EXECUTION_PAUSED event. */
export interface PLAN_EXECUTION_PAUSEDData {
  /** Plan identifier */
  plan_id: string;
  /** Step number that caused pause */
  current_step: number;
  /** Reason for pause */
  reason: string;
}

/** Payload for PLAN_EXECUTION_RESUMED event. */
export interface PLAN_EXECUTION_RESUMEDData {
  /** Plan identifier */
  plan_id: string;
  /** Step number resuming from */
  from_step: number;
}

/** Payload for STEP_AWAITING_APPROVAL event. */
export interface STEP_AWAITING_APPROVALData {
  /** Step identifier */
  step_id: string;
  /** Step number (1-indexed) */
  step_number: number;
  /** Step description */
  description: string;
  /** Agent that will execute this step */
  agent: string;
}

/** Payload for STEP_APPROVED event. */
export interface STEP_APPROVEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
}

/** Payload for STEP_REJECTED event. */
export interface STEP_REJECTEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Rejection reason */
  reason?: string | null;
}

/** Payload for STEP_STARTED event. */
export interface STEP_STARTEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Step description */
  description: string;
  /** Agent executing this step */
  agent: string;
}

/** Payload for STEP_CHECKPOINTED event. */
export interface STEP_CHECKPOINTEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Iteration count at checkpoint */
  iteration: number;
}

/** Payload for STEP_COMPLETED event. */
export interface STEP_COMPLETEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Total iterations used */
  iterations_used: number;
  /** Files modified */
  files_modified?: string[];
}

/** Payload for STEP_FAILED event. */
export interface STEP_FAILEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Error message */
  error: string;
}

/** Payload for STEP_RESULT_PENDING event. */
export interface STEP_RESULT_PENDINGData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Step output (may be truncated) */
  output: string;
  /** Files modified */
  files_modified?: string[];
}

/** Payload for STEP_RESULT_ACCEPTED event. */
export interface STEP_RESULT_ACCEPTEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
}

/** Payload for STEP_RESULT_REJECTED event. */
export interface STEP_RESULT_REJECTEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
  /** Rejection reason */
  reason?: string | null;
}

/** Payload for STEP_RERUN_REQUESTED event. */
export interface STEP_RERUN_REQUESTEDData {
  /** Step identifier */
  step_id: string;
  /** Step number */
  step_number: number;
}

/** Payload for INDEX_QUEUED event. */
export interface INDEX_QUEUEDData {
  /** Absolute path to the project */
  project_path: string;
  /** Display name of the project */
  project_name: string;
  /** Queue priority (1=highest, 10=lowest) */
  priority: number;
  /** Position in the indexer queue */
  queue_position: number;
}

/** Payload for INDEX_STARTED event. */
export interface INDEX_STARTEDData {
  /** Absolute path to the project */
  project_path: string;
  /** Display name of the project */
  project_name: string;
  /** Total files to index (estimated) */
  total_files: number;
  /** Whether this is a forced re-index */
  force?: boolean;
}

/** Payload for INDEX_PROGRESS event. */
export interface INDEX_PROGRESSData {
  /** Absolute path to the project */
  project_path: string;
  /** Display name of the project */
  project_name: string;
  /** Number of files processed so far */
  files_processed: number;
  /** Total files to process */
  total_files: number;
  /** Embedding chunks added so far */
  chunks_added: number;
  /** Files skipped (unchanged) */
  files_skipped?: number;
  /** Progress percentage (0-100) */
  percent_complete: number;
}

/** Payload for INDEX_COMPLETED event. */
export interface INDEX_COMPLETEDData {
  /** Absolute path to the project */
  project_path: string;
  /** Display name of the project */
  project_name: string;
  /** Total files successfully indexed */
  files_indexed: number;
  /** Files skipped (unchanged) */
  files_skipped?: number;
  /** Files that failed to index */
  files_failed?: number;
  /** Total embedding chunks created */
  chunks_added: number;
  /** Chunks removed (deleted/changed files) */
  chunks_removed?: number;
  /** Total indexing duration */
  duration_seconds: number;
}

/** Payload for INDEX_FAILED event. */
export interface INDEX_FAILEDData {
  /** Absolute path to the project */
  project_path: string;
  /** Display name of the project */
  project_name: string;
  /** Error message describing the failure */
  error: string;
  /** Files processed before failure */
  files_processed?: number;
  /** Duration until failure */
  duration_seconds?: number;
}

/** Payload for INDEX_FILE_PROCESSED event (detailed progress). */
export interface INDEX_FILE_PROCESSEDData {
  /** Absolute path to the project */
  project_path: string;
  /** Relative path of the indexed file */
  file_path: string;
  /** Number of chunks created for this file */
  chunks_created: number;
  /** Whether file was skipped (unchanged) */
  skipped?: boolean;
}

/** Payload for INDEXER_STARTED event. */
export interface INDEXER_STARTEDData {
  /** Number of projects in the queue */
  queued_projects: number;
  /** Whether auto-indexing is enabled */
  auto_index_enabled?: boolean;
}

/** Payload for INDEXER_STOPPED event. */
export interface INDEXER_STOPPEDData {
  /** Reason for stopping */
  reason?: string;
  /** Projects indexed in this session */
  projects_indexed?: number;
}

/** Payload for INDEXER_PAUSED event. */
export interface INDEXER_PAUSEDData {
  /** Reason for pausing (e.g., VRAM constraints) */
  reason: string;
  /** Expected resume time */
  resume_after_seconds?: number | null;
}

/** Payload for TELEMETRY_TICK event (periodic updates every 2 seconds). */
export interface TELEMETRY_TICKData {
  /** Unix timestamp of the tick */
  timestamp: number;
  /** Active session ID */
  session_id?: string | null;
  /** Current VRAM state */
  vram: VRAMSnapshot;
  /** Current task concurrency state */
  concurrency: ConcurrencySnapshot;
  /** Current session duration */
  session_duration_seconds?: number;
  /** Currently executing agent */
  current_agent?: string | null;
  /** Current iteration number */
  current_iteration?: number;
}

/** Payload for TELEMETRY_SNAPSHOT event (full dump on demand or session end). */
export interface TELEMETRY_SNAPSHOTData {
  /** Unix timestamp of the snapshot */
  timestamp: number;
  /** Session ID */
  session_id: string;
  /** Total session duration */
  session_duration_seconds: number;
  /** VRAM state */
  vram: VRAMSnapshot;
  /** Task concurrency state */
  concurrency: ConcurrencySnapshot;
  /** Per-agent timing statistics */
  agent_stats?: AgentTimingStats[];
  /** Per-tool timing statistics */
  tool_stats?: ToolTimingStats[];
  /** Total iterations across all agents */
  total_iterations?: number;
  /** Total tool calls across all tools */
  total_tool_calls?: number;
  /** Total LLM inference time */
  llm_time_seconds?: number;
  /** Total tool execution time */
  tool_time_seconds?: number;
}

// === Event Type Union ===

export type EventType =
  | 'TASK_CREATED'
  | 'TASK_STATUS_CHANGED'
  | 'AGENT_OUTPUT'
  | 'TOOL_CALLED'
  | 'DELEGATION_START'
  | 'DELEGATION_COMPLETE'
  | 'DELEGATION_FAILED'
  | 'MODEL_LOADED'
  | 'MODEL_UNLOADED'
  | 'MODEL_DEGRADED'
  | 'ERROR'
  | 'ITERATION_START'
  | 'ITERATION_END'
  | 'ITERATION_WARNING'
  | 'PARALLEL_BATCH_START'
  | 'PARALLEL_BATCH_END'
  | 'STREAMING_START'
  | 'STREAMING_TOKEN'
  | 'STREAMING_END'
  | 'PLAN_PROPOSED'
  | 'PLAN_APPROVED'
  | 'PLAN_REJECTED'
  | 'PATTERN_LEARNED'
  | 'METRICS_UPDATED'
  | 'POLICY_VIOLATION'
  | 'POLICY_WARNING'
  | 'POLICY_ESCALATION'
  | 'PLAN_PERSISTED'
  | 'PLAN_AWAITING_APPROVAL'
  | 'PLAN_EXECUTION_STARTED'
  | 'PLAN_EXECUTION_PAUSED'
  | 'PLAN_EXECUTION_RESUMED'
  | 'STEP_AWAITING_APPROVAL'
  | 'STEP_APPROVED'
  | 'STEP_REJECTED'
  | 'STEP_STARTED'
  | 'STEP_CHECKPOINTED'
  | 'STEP_COMPLETED'
  | 'STEP_FAILED'
  | 'STEP_RESULT_PENDING'
  | 'STEP_RESULT_ACCEPTED'
  | 'STEP_RESULT_REJECTED'
  | 'STEP_RERUN_REQUESTED'
  | 'INDEX_QUEUED'
  | 'INDEX_STARTED'
  | 'INDEX_PROGRESS'
  | 'INDEX_COMPLETED'
  | 'INDEX_FAILED'
  | 'INDEX_FILE_PROCESSED'
  | 'INDEXER_STARTED'
  | 'INDEXER_STOPPED'
  | 'INDEXER_PAUSED'
  | 'TELEMETRY_TICK'
  | 'TELEMETRY_SNAPSHOT';

// === Event Type to Data Type Map ===

export interface EventTypeDataMap {
  TASK_CREATED: TASK_CREATEDData;
  TASK_STATUS_CHANGED: TASK_STATUS_CHANGEDData;
  AGENT_OUTPUT: AGENT_OUTPUTData;
  TOOL_CALLED: TOOL_CALLEDData;
  DELEGATION_START: DELEGATION_STARTData;
  DELEGATION_COMPLETE: DELEGATION_COMPLETEData;
  DELEGATION_FAILED: DELEGATION_FAILEDData;
  MODEL_LOADED: MODEL_LOADEDData;
  MODEL_UNLOADED: MODEL_UNLOADEDData;
  MODEL_DEGRADED: MODEL_DEGRADEDData;
  ERROR: ERRORData;
  ITERATION_START: ITERATION_STARTData;
  ITERATION_END: ITERATION_ENDData;
  ITERATION_WARNING: ITERATION_WARNINGData;
  PARALLEL_BATCH_START: PARALLEL_BATCH_STARTData;
  PARALLEL_BATCH_END: PARALLEL_BATCH_ENDData;
  STREAMING_START: STREAMING_STARTData;
  STREAMING_TOKEN: STREAMING_TOKENData;
  STREAMING_END: STREAMING_ENDData;
  PLAN_PROPOSED: PLAN_PROPOSEDData;
  PLAN_APPROVED: PLAN_APPROVEDData;
  PLAN_REJECTED: PLAN_REJECTEDData;
  PATTERN_LEARNED: PATTERN_LEARNEDData;
  METRICS_UPDATED: METRICS_UPDATEDData;
  POLICY_VIOLATION: POLICY_VIOLATIONData;
  POLICY_WARNING: POLICY_WARNINGData;
  POLICY_ESCALATION: POLICY_ESCALATIONData;
  PLAN_PERSISTED: PLAN_PERSISTEDData;
  PLAN_AWAITING_APPROVAL: PLAN_AWAITING_APPROVALData;
  PLAN_EXECUTION_STARTED: PLAN_EXECUTION_STARTEDData;
  PLAN_EXECUTION_PAUSED: PLAN_EXECUTION_PAUSEDData;
  PLAN_EXECUTION_RESUMED: PLAN_EXECUTION_RESUMEDData;
  STEP_AWAITING_APPROVAL: STEP_AWAITING_APPROVALData;
  STEP_APPROVED: STEP_APPROVEDData;
  STEP_REJECTED: STEP_REJECTEDData;
  STEP_STARTED: STEP_STARTEDData;
  STEP_CHECKPOINTED: STEP_CHECKPOINTEDData;
  STEP_COMPLETED: STEP_COMPLETEDData;
  STEP_FAILED: STEP_FAILEDData;
  STEP_RESULT_PENDING: STEP_RESULT_PENDINGData;
  STEP_RESULT_ACCEPTED: STEP_RESULT_ACCEPTEDData;
  STEP_RESULT_REJECTED: STEP_RESULT_REJECTEDData;
  STEP_RERUN_REQUESTED: STEP_RERUN_REQUESTEDData;
  INDEX_QUEUED: INDEX_QUEUEDData;
  INDEX_STARTED: INDEX_STARTEDData;
  INDEX_PROGRESS: INDEX_PROGRESSData;
  INDEX_COMPLETED: INDEX_COMPLETEDData;
  INDEX_FAILED: INDEX_FAILEDData;
  INDEX_FILE_PROCESSED: INDEX_FILE_PROCESSEDData;
  INDEXER_STARTED: INDEXER_STARTEDData;
  INDEXER_STOPPED: INDEXER_STOPPEDData;
  INDEXER_PAUSED: INDEXER_PAUSEDData;
  TELEMETRY_TICK: TELEMETRY_TICKData;
  TELEMETRY_SNAPSHOT: TELEMETRY_SNAPSHOTData;
}

// === Typed WebSocket Event (Discriminated Union) ===

export type TypedWebSocketEvent =
  | { type: 'TASK_CREATED'; data: TASK_CREATEDData; timestamp: number; task_id?: string | null }
  | { type: 'TASK_STATUS_CHANGED'; data: TASK_STATUS_CHANGEDData; timestamp: number; task_id?: string | null }
  | { type: 'AGENT_OUTPUT'; data: AGENT_OUTPUTData; timestamp: number; task_id?: string | null }
  | { type: 'TOOL_CALLED'; data: TOOL_CALLEDData; timestamp: number; task_id?: string | null }
  | { type: 'DELEGATION_START'; data: DELEGATION_STARTData; timestamp: number; task_id?: string | null }
  | { type: 'DELEGATION_COMPLETE'; data: DELEGATION_COMPLETEData; timestamp: number; task_id?: string | null }
  | { type: 'DELEGATION_FAILED'; data: DELEGATION_FAILEDData; timestamp: number; task_id?: string | null }
  | { type: 'MODEL_LOADED'; data: MODEL_LOADEDData; timestamp: number; task_id?: string | null }
  | { type: 'MODEL_UNLOADED'; data: MODEL_UNLOADEDData; timestamp: number; task_id?: string | null }
  | { type: 'MODEL_DEGRADED'; data: MODEL_DEGRADEDData; timestamp: number; task_id?: string | null }
  | { type: 'ERROR'; data: ERRORData; timestamp: number; task_id?: string | null }
  | { type: 'ITERATION_START'; data: ITERATION_STARTData; timestamp: number; task_id?: string | null }
  | { type: 'ITERATION_END'; data: ITERATION_ENDData; timestamp: number; task_id?: string | null }
  | { type: 'ITERATION_WARNING'; data: ITERATION_WARNINGData; timestamp: number; task_id?: string | null }
  | { type: 'PARALLEL_BATCH_START'; data: PARALLEL_BATCH_STARTData; timestamp: number; task_id?: string | null }
  | { type: 'PARALLEL_BATCH_END'; data: PARALLEL_BATCH_ENDData; timestamp: number; task_id?: string | null }
  | { type: 'STREAMING_START'; data: STREAMING_STARTData; timestamp: number; task_id?: string | null }
  | { type: 'STREAMING_TOKEN'; data: STREAMING_TOKENData; timestamp: number; task_id?: string | null }
  | { type: 'STREAMING_END'; data: STREAMING_ENDData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_PROPOSED'; data: PLAN_PROPOSEDData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_APPROVED'; data: PLAN_APPROVEDData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_REJECTED'; data: PLAN_REJECTEDData; timestamp: number; task_id?: string | null }
  | { type: 'PATTERN_LEARNED'; data: PATTERN_LEARNEDData; timestamp: number; task_id?: string | null }
  | { type: 'METRICS_UPDATED'; data: METRICS_UPDATEDData; timestamp: number; task_id?: string | null }
  | { type: 'POLICY_VIOLATION'; data: POLICY_VIOLATIONData; timestamp: number; task_id?: string | null }
  | { type: 'POLICY_WARNING'; data: POLICY_WARNINGData; timestamp: number; task_id?: string | null }
  | { type: 'POLICY_ESCALATION'; data: POLICY_ESCALATIONData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_PERSISTED'; data: PLAN_PERSISTEDData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_AWAITING_APPROVAL'; data: PLAN_AWAITING_APPROVALData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_EXECUTION_STARTED'; data: PLAN_EXECUTION_STARTEDData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_EXECUTION_PAUSED'; data: PLAN_EXECUTION_PAUSEDData; timestamp: number; task_id?: string | null }
  | { type: 'PLAN_EXECUTION_RESUMED'; data: PLAN_EXECUTION_RESUMEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_AWAITING_APPROVAL'; data: STEP_AWAITING_APPROVALData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_APPROVED'; data: STEP_APPROVEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_REJECTED'; data: STEP_REJECTEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_STARTED'; data: STEP_STARTEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_CHECKPOINTED'; data: STEP_CHECKPOINTEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_COMPLETED'; data: STEP_COMPLETEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_FAILED'; data: STEP_FAILEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_RESULT_PENDING'; data: STEP_RESULT_PENDINGData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_RESULT_ACCEPTED'; data: STEP_RESULT_ACCEPTEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_RESULT_REJECTED'; data: STEP_RESULT_REJECTEDData; timestamp: number; task_id?: string | null }
  | { type: 'STEP_RERUN_REQUESTED'; data: STEP_RERUN_REQUESTEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEX_QUEUED'; data: INDEX_QUEUEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEX_STARTED'; data: INDEX_STARTEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEX_PROGRESS'; data: INDEX_PROGRESSData; timestamp: number; task_id?: string | null }
  | { type: 'INDEX_COMPLETED'; data: INDEX_COMPLETEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEX_FAILED'; data: INDEX_FAILEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEX_FILE_PROCESSED'; data: INDEX_FILE_PROCESSEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEXER_STARTED'; data: INDEXER_STARTEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEXER_STOPPED'; data: INDEXER_STOPPEDData; timestamp: number; task_id?: string | null }
  | { type: 'INDEXER_PAUSED'; data: INDEXER_PAUSEDData; timestamp: number; task_id?: string | null }
  | { type: 'TELEMETRY_TICK'; data: TELEMETRY_TICKData; timestamp: number; task_id?: string | null }
  | { type: 'TELEMETRY_SNAPSHOT'; data: TELEMETRY_SNAPSHOTData; timestamp: number; task_id?: string | null };

// === Type Guard Helpers ===

export function isEventType<T extends EventType>(event: TypedWebSocketEvent, type: T): event is TypedWebSocketEvent & { type: T; data: EventTypeDataMap[T] } {
  return event.type === type;
}

// === All Event Types ===

export const ALL_EVENT_TYPES: EventType[] = [
  'TASK_CREATED',
  'TASK_STATUS_CHANGED',
  'AGENT_OUTPUT',
  'TOOL_CALLED',
  'DELEGATION_START',
  'DELEGATION_COMPLETE',
  'DELEGATION_FAILED',
  'MODEL_LOADED',
  'MODEL_UNLOADED',
  'MODEL_DEGRADED',
  'ERROR',
  'ITERATION_START',
  'ITERATION_END',
  'ITERATION_WARNING',
  'PARALLEL_BATCH_START',
  'PARALLEL_BATCH_END',
  'STREAMING_START',
  'STREAMING_TOKEN',
  'STREAMING_END',
  'PLAN_PROPOSED',
  'PLAN_APPROVED',
  'PLAN_REJECTED',
  'PATTERN_LEARNED',
  'METRICS_UPDATED',
  'POLICY_VIOLATION',
  'POLICY_WARNING',
  'POLICY_ESCALATION',
  'PLAN_PERSISTED',
  'PLAN_AWAITING_APPROVAL',
  'PLAN_EXECUTION_STARTED',
  'PLAN_EXECUTION_PAUSED',
  'PLAN_EXECUTION_RESUMED',
  'STEP_AWAITING_APPROVAL',
  'STEP_APPROVED',
  'STEP_REJECTED',
  'STEP_STARTED',
  'STEP_CHECKPOINTED',
  'STEP_COMPLETED',
  'STEP_FAILED',
  'STEP_RESULT_PENDING',
  'STEP_RESULT_ACCEPTED',
  'STEP_RESULT_REJECTED',
  'STEP_RERUN_REQUESTED',
  'INDEX_QUEUED',
  'INDEX_STARTED',
  'INDEX_PROGRESS',
  'INDEX_COMPLETED',
  'INDEX_FAILED',
  'INDEX_FILE_PROCESSED',
  'INDEXER_STARTED',
  'INDEXER_STOPPED',
  'INDEXER_PAUSED',
  'TELEMETRY_TICK',
  'TELEMETRY_SNAPSHOT',
];

// === API Version ===

export const API_VERSION = '1.0.0';
