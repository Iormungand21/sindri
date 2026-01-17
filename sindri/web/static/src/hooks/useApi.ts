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
  coverageSummary: (id: string) => ['sessions', id, 'coverage'] as const,
  coverageDetail: (id: string) => ['sessions', id, 'coverage', 'detail'] as const,
  coverageList: (limit?: number) => ['coverage', { limit }] as const,
  coverageStats: ['coverage', 'stats'] as const,
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

// Coverage hooks
export function useCoverageSummary(sessionId: string) {
  return useQuery({
    queryKey: queryKeys.coverageSummary(sessionId),
    queryFn: () => api.getCoverageSummary(sessionId),
    enabled: !!sessionId,
    staleTime: 1000 * 60 * 5, // 5 minutes - coverage doesn't change
    retry: false, // Don't retry if not found
  })
}

export function useCoverageDetail(sessionId: string) {
  return useQuery({
    queryKey: queryKeys.coverageDetail(sessionId),
    queryFn: () => api.getCoverageDetail(sessionId),
    enabled: !!sessionId,
    staleTime: 1000 * 60 * 5,
    retry: false,
  })
}

export function useCoverageList(limit = 20) {
  return useQuery({
    queryKey: queryKeys.coverageList(limit),
    queryFn: () => api.listCoverageReports(limit),
    staleTime: 1000 * 60, // 1 minute
  })
}

export function useCoverageStats() {
  return useQuery({
    queryKey: queryKeys.coverageStats,
    queryFn: api.getCoverageStats,
    staleTime: 1000 * 60, // 1 minute
  })
}

export function useImportCoverage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, coveragePath }: { sessionId: string; coveragePath: string }) =>
      api.importCoverage(sessionId, coveragePath),
    onSuccess: (_data, variables) => {
      // Invalidate coverage queries for this session
      queryClient.invalidateQueries({ queryKey: ['sessions', variables.sessionId, 'coverage'] })
      queryClient.invalidateQueries({ queryKey: ['coverage'] })
    },
  })
}

export function useDeleteCoverage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sessionId: string) => api.deleteCoverage(sessionId),
    onSuccess: (_data, sessionId) => {
      // Invalidate coverage queries
      queryClient.invalidateQueries({ queryKey: ['sessions', sessionId, 'coverage'] })
      queryClient.invalidateQueries({ queryKey: ['coverage'] })
    },
  })
}
