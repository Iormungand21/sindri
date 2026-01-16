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

export { ApiError }
