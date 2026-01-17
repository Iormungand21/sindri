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

// File change types for diff viewer
export interface FileChange {
  file_path: string
  operation: 'read' | 'write' | 'edit'
  turn_index: number
  timestamp: string
  success: boolean
  new_content?: string
  content_size?: number
  old_text?: string
  new_text?: string
  read_content?: string
}

export interface FileChanges {
  session_id: string
  file_changes: FileChange[]
  files_modified: string[]
  total_changes: number
}

// Coverage types
export interface FileCoverage {
  filename: string
  lines_valid: number
  lines_covered: number
  line_rate: number
  line_percentage: number
  branches_valid: number
  branches_covered: number
  branch_rate: number
  covered_lines: number[]
  uncovered_lines: number[]
}

export interface PackageCoverage {
  name: string
  line_rate: number
  branch_rate: number
  lines_valid: number
  lines_covered: number
  files: FileCoverage[]
}

export interface CoverageSummary {
  session_id: string | null
  source: string
  timestamp: string
  line_rate: number
  line_percentage: number
  lines_valid: number
  lines_covered: number
  branch_rate: number
  branch_percentage: number
  branches_valid: number
  branches_covered: number
  files_count: number
  packages_count: number
}

export interface CoverageDetail extends CoverageSummary {
  packages: PackageCoverage[]
}

export interface CoverageStats {
  total_reports: number
  avg_line_rate: number
  avg_line_percentage: number
  max_line_rate: number
  min_line_rate: number
  total_files: number
  total_lines: number
  total_covered: number
}

export interface CoverageListItem {
  session_id: string
  line_rate: number
  line_percentage: number
  branch_rate: number
  files_covered: number
  lines_valid: number
  lines_covered: number
  created_at: string
  task: string
  status: string
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
