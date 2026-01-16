/**
 * RecentTasks - List of recent sessions/tasks
 */

import type { Session } from '../types/api'

interface RecentTasksProps {
  sessions: Session[]
}

export function RecentTasks({ sessions }: RecentTasksProps) {
  if (sessions.length === 0) {
    return (
      <div className="text-center py-8 text-sindri-500">
        <p>No tasks yet</p>
        <p className="text-sm mt-1">Submit a task to get started</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {sessions.map((session) => (
        <SessionRow key={session.id} session={session} />
      ))}
    </div>
  )
}

interface SessionRowProps {
  session: Session
}

function SessionRow({ session }: SessionRowProps) {
  const statusColors = {
    completed: 'bg-green-900/50 text-green-400 border-green-700',
    failed: 'bg-red-900/50 text-red-400 border-red-700',
    active: 'bg-blue-900/50 text-blue-400 border-blue-700',
    cancelled: 'bg-gray-900/50 text-gray-400 border-gray-700',
  }

  const statusIcons = {
    completed: '✓',
    failed: '✗',
    active: '●',
    cancelled: '○',
  }

  const statusColor = statusColors[session.status] || statusColors.cancelled
  const statusIcon = statusIcons[session.status] || '?'

  const createdAt = new Date(session.created_at)
  const timeAgo = formatTimeAgo(createdAt)

  return (
    <a
      href={`/sessions/${session.id}`}
      className="block p-3 rounded-lg bg-sindri-800/50 hover:bg-sindri-800 transition-colors border border-transparent hover:border-sindri-600"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-sindri-100 truncate">{session.task}</p>
          <div className="flex items-center gap-3 mt-1 text-xs text-sindri-400">
            <span>{session.model}</span>
            <span>•</span>
            <span>{session.iterations} iterations</span>
            <span>•</span>
            <span>{timeAgo}</span>
          </div>
        </div>
        <span
          className={`flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${statusColor}`}
        >
          <span>{statusIcon}</span>
          {session.status}
        </span>
      </div>
    </a>
  )
}

function formatTimeAgo(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`
  return date.toLocaleDateString()
}
