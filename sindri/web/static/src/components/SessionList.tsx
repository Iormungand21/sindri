/**
 * SessionList - Display all sessions with filtering
 */

import { useState } from 'react'
import { useSessions } from '../hooks/useApi'
import type { Session } from '../types/api'

export function SessionList() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const { data: sessions, isLoading, error } = useSessions({
    status: statusFilter || undefined,
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-sindri-100">Sessions</h1>
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="card p-4 animate-pulse">
              <div className="h-5 bg-sindri-700 rounded w-3/4 mb-2" />
              <div className="h-4 bg-sindri-700 rounded w-1/2" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-red-400">Failed to load sessions</p>
        <p className="text-sm text-sindri-500 mt-1">
          Make sure the backend is running
        </p>
      </div>
    )
  }

  const statusOptions = [
    { value: '', label: 'All' },
    { value: 'completed', label: 'Completed' },
    { value: 'failed', label: 'Failed' },
    { value: 'active', label: 'Active' },
    { value: 'cancelled', label: 'Cancelled' },
  ]

  // Stats
  const stats = {
    total: sessions?.length ?? 0,
    completed: sessions?.filter((s) => s.status === 'completed').length ?? 0,
    failed: sessions?.filter((s) => s.status === 'failed').length ?? 0,
    active: sessions?.filter((s) => s.status === 'active').length ?? 0,
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-sindri-100">Sessions</h1>
          <p className="text-sindri-400 text-sm mt-1">
            {stats.total} total • {stats.completed} completed • {stats.failed}{' '}
            failed • {stats.active} active
          </p>
        </div>
        <div className="flex items-center gap-2">
          {statusOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => setStatusFilter(option.value)}
              className={`btn text-sm ${
                statusFilter === option.value
                  ? 'btn-primary'
                  : 'btn-secondary'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {sessions?.length === 0 ? (
        <div className="text-center py-8 card">
          <p className="text-sindri-400">No sessions found</p>
          {statusFilter && (
            <button
              onClick={() => setStatusFilter('')}
              className="text-forge-400 hover:text-forge-300 text-sm mt-2"
            >
              Clear filter
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {sessions?.map((session) => (
            <SessionCard key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  )
}

interface SessionCardProps {
  session: Session
}

function SessionCard({ session }: SessionCardProps) {
  const statusStyles = {
    completed: {
      bg: 'bg-green-900/30 border-green-800',
      badge: 'bg-green-900/50 text-green-400 border-green-700',
      icon: '✓',
    },
    failed: {
      bg: 'bg-red-900/30 border-red-800',
      badge: 'bg-red-900/50 text-red-400 border-red-700',
      icon: '✗',
    },
    active: {
      bg: 'bg-blue-900/30 border-blue-800',
      badge: 'bg-blue-900/50 text-blue-400 border-blue-700',
      icon: '●',
    },
    cancelled: {
      bg: 'bg-gray-900/30 border-gray-700',
      badge: 'bg-gray-900/50 text-gray-400 border-gray-600',
      icon: '○',
    },
  }

  const style = statusStyles[session.status] || statusStyles.cancelled

  const createdAt = new Date(session.created_at)
  const completedAt = session.completed_at
    ? new Date(session.completed_at)
    : null
  const duration = completedAt
    ? formatDuration(completedAt.getTime() - createdAt.getTime())
    : 'In progress'

  return (
    <a
      href={`/sessions/${session.id}`}
      className={`block card p-4 hover:border-sindri-500 transition-colors ${style.bg}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-sindri-100 font-medium truncate">
            {session.task}
          </h3>
          <div className="flex items-center gap-4 mt-2 text-sm text-sindri-400">
            <span className="flex items-center gap-1">
              <code className="text-xs bg-sindri-800 px-1 rounded">
                {session.model}
              </code>
            </span>
            <span>{session.iterations} iterations</span>
            <span>{duration}</span>
            <span>{createdAt.toLocaleDateString()}</span>
          </div>
        </div>
        <span
          className={`flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-sm border ${style.badge}`}
        >
          <span>{style.icon}</span>
          {session.status}
        </span>
      </div>
      <div className="mt-3 pt-3 border-t border-sindri-700/50">
        <code className="text-xs text-sindri-500 font-mono">
          {session.id.slice(0, 8)}...
        </code>
      </div>
    </a>
  )
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  }
  return `${seconds}s`
}
