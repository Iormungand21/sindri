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
  | 'METRICS_UPDATED';

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
  | { type: 'METRICS_UPDATED'; data: METRICS_UPDATEDData; timestamp: number; task_id?: string | null };

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
];

// === API Version ===

export const API_VERSION = '1.0.0';
