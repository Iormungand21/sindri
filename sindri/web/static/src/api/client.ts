/**
 * Sindri API Client
 */

import type {
  Agent,
  Session,
  SessionDetail,
  TaskCreateRequest,
  TaskResponse,
  TaskStatus,
  Metrics,
  FileChanges,
  CoverageSummary,
  CoverageDetail,
  CoverageStats,
  CoverageListItem,
} from '../types/api'

const API_BASE = '/api'

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    let errorData: unknown
    try {
      errorData = await response.json()
    } catch {
      errorData = await response.text()
    }
    throw new ApiError(
      `API error: ${response.statusText}`,
      response.status,
      errorData
    )
  }

  return response.json()
}

// Agent endpoints
export async function getAgents(): Promise<Agent[]> {
  return fetchApi<Agent[]>('/agents')
}

export async function getAgent(name: string): Promise<Agent> {
  return fetchApi<Agent>(`/agents/${encodeURIComponent(name)}`)
}

// Session endpoints
export async function getSessions(options?: {
  status?: string
  limit?: number
}): Promise<Session[]> {
  const params = new URLSearchParams()
  if (options?.status) params.set('status', options.status)
  if (options?.limit) params.set('limit', String(options.limit))

  const query = params.toString()
  return fetchApi<Session[]>(`/sessions${query ? `?${query}` : ''}`)
}

export async function getSession(id: string): Promise<SessionDetail> {
  return fetchApi<SessionDetail>(`/sessions/${encodeURIComponent(id)}`)
}

export async function getFileChanges(
  sessionId: string,
  includeContent = true
): Promise<FileChanges> {
  const params = new URLSearchParams()
  params.set('include_content', String(includeContent))
  return fetchApi<FileChanges>(
    `/sessions/${encodeURIComponent(sessionId)}/file-changes?${params.toString()}`
  )
}

// Task endpoints
export async function createTask(
  request: TaskCreateRequest
): Promise<TaskResponse> {
  return fetchApi<TaskResponse>('/tasks', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  return fetchApi<TaskStatus>(`/tasks/${encodeURIComponent(taskId)}`)
}

// Metrics endpoint
export async function getMetrics(): Promise<Metrics> {
  return fetchApi<Metrics>('/metrics')
}

// Health check
export async function checkHealth(): Promise<{ status: string }> {
  return fetchApi<{ status: string }>('/health')
}

// Coverage endpoints
export async function getCoverageSummary(
  sessionId: string
): Promise<CoverageSummary> {
  return fetchApi<CoverageSummary>(
    `/sessions/${encodeURIComponent(sessionId)}/coverage`
  )
}

export async function getCoverageDetail(
  sessionId: string
): Promise<CoverageDetail> {
  return fetchApi<CoverageDetail>(
    `/sessions/${encodeURIComponent(sessionId)}/coverage/detail`
  )
}

export async function importCoverage(
  sessionId: string,
  coveragePath: string
): Promise<CoverageSummary> {
  return fetchApi<CoverageSummary>(
    `/sessions/${encodeURIComponent(sessionId)}/coverage`,
    {
      method: 'POST',
      body: JSON.stringify({ coverage_path: coveragePath }),
    }
  )
}

export async function deleteCoverage(
  sessionId: string
): Promise<{ message: string }> {
  return fetchApi<{ message: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/coverage`,
    { method: 'DELETE' }
  )
}

export async function listCoverageReports(
  limit = 20
): Promise<CoverageListItem[]> {
  return fetchApi<CoverageListItem[]>(`/coverage?limit=${limit}`)
}

export async function getCoverageStats(): Promise<CoverageStats> {
  return fetchApi<CoverageStats>('/coverage/stats')
}

export { ApiError }
