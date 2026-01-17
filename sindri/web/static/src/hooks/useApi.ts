/**
 * React Query hooks for Sindri API
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/client'
import type { TaskCreateRequest } from '../types/api'

// Query keys
export const queryKeys = {
  agents: ['agents'] as const,
  agent: (name: string) => ['agents', name] as const,
  sessions: (options?: { status?: string; limit?: number }) =>
    ['sessions', options] as const,
  session: (id: string) => ['sessions', id] as const,
  fileChanges: (id: string) => ['sessions', id, 'file-changes'] as const,
  taskStatus: (id: string) => ['tasks', id] as const,
  metrics: ['metrics'] as const,
  health: ['health'] as const,
}

// Agent hooks
export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents,
    queryFn: api.getAgents,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })
}

export function useAgent(name: string) {
  return useQuery({
    queryKey: queryKeys.agent(name),
    queryFn: () => api.getAgent(name),
    enabled: !!name,
    staleTime: 1000 * 60 * 5,
  })
}

// Session hooks
export function useSessions(options?: { status?: string; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.sessions(options),
    queryFn: () => api.getSessions(options),
    refetchInterval: 5000, // Refresh every 5 seconds
  })
}

export function useSession(id: string) {
  return useQuery({
    queryKey: queryKeys.session(id),
    queryFn: () => api.getSession(id),
    enabled: !!id,
  })
}

export function useFileChanges(sessionId: string) {
  return useQuery({
    queryKey: queryKeys.fileChanges(sessionId),
    queryFn: () => api.getFileChanges(sessionId),
    enabled: !!sessionId,
    staleTime: 1000 * 60 * 5, // 5 minutes - file changes don't change
  })
}

// Task hooks
export function useCreateTask() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: TaskCreateRequest) => api.createTask(request),
    onSuccess: () => {
      // Invalidate sessions to show new task
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useTaskStatus(taskId: string) {
  return useQuery({
    queryKey: queryKeys.taskStatus(taskId),
    queryFn: () => api.getTaskStatus(taskId),
    enabled: !!taskId,
    refetchInterval: (query) => {
      // Stop polling when task is complete or failed
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed') {
        return false
      }
      return 1000 // Poll every second while running
    },
  })
}

// Metrics hook
export function useMetrics() {
  return useQuery({
    queryKey: queryKeys.metrics,
    queryFn: api.getMetrics,
    refetchInterval: 5000, // Refresh every 5 seconds
  })
}

// Health hook
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.checkHealth,
    refetchInterval: 10000, // Refresh every 10 seconds
    retry: false,
  })
}
