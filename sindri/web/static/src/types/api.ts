/**
 * TypeScript types for Sindri API
 */

export interface Agent {
  name: string
  role: string
  model: string
  tools: string[]
  can_delegate: boolean
  delegate_to: string[]
  estimated_vram_gb: number
  max_iterations: number
  fallback_model: string | null
}

export interface Session {
  id: string
  task: string
  model: string
  status: 'active' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  completed_at: string | null
  iterations: number
}

export interface SessionDetail extends Session {
  turns: Turn[]
}

export interface Turn {
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: string
  tool_calls?: ToolCall[]
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result?: string
}

export interface TaskCreateRequest {
  description: string
  agent?: string
  max_iterations?: number
  work_dir?: string
  enable_memory?: boolean
}

export interface TaskResponse {
  task_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  message: string
}

export interface TaskStatus {
  task_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  result: string | null
  error: string | null
  subtasks: number
}

export interface Metrics {
  total_sessions: number
  completed_sessions: number
  failed_sessions: number
  active_sessions: number
  stale_sessions: number  // Sessions marked active but likely abandoned (>1hr old)
  total_iterations: number
  vram_used_gb: number
  vram_total_gb: number
  loaded_models: string[]
}

export interface WebSocketEvent {
  type: string
  data: Record<string, unknown>
  timestamp: string
}

// Event types from the EventBus
export type EventType =
  | 'TASK_START'
  | 'TASK_COMPLETE'
  | 'TASK_FAILED'
  | 'AGENT_START'
  | 'AGENT_OUTPUT'
  | 'AGENT_COMPLETE'
  | 'TOOL_START'
  | 'TOOL_RESULT'
  | 'DELEGATION_START'
  | 'DELEGATION_COMPLETE'
  | 'MODEL_LOADING'
  | 'MODEL_LOADED'
  | 'MODEL_UNLOADED'
  | 'MODEL_DEGRADED'
  | 'ITERATION_WARNING'
  | 'STREAMING_START'
  | 'STREAMING_TOKEN'
  | 'STREAMING_END'
  | 'PLAN_PROPOSED'
  | 'PATTERN_LEARNED'
  | 'PARALLEL_BATCH_START'
  | 'PARALLEL_BATCH_END'
