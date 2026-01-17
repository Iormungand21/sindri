/**
 * SessionDetail - View details of a specific session
 */

import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useSession, useFileChanges } from '../hooks/useApi'
import { CodeDiffViewer } from './CodeDiffViewer'
import type { Turn } from '../types/api'

type TabId = 'conversation' | 'files'

export function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: session, isLoading, error } = useSession(id ?? '')
  const {
    data: fileChanges,
    isLoading: fileChangesLoading,
    error: fileChangesError,
  } = useFileChanges(id ?? '')
  const [activeTab, setActiveTab] = useState<TabId>('conversation')

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-sindri-700 rounded w-1/3 animate-pulse" />
        <div className="card p-4 animate-pulse">
          <div className="h-4 bg-sindri-700 rounded w-3/4 mb-2" />
          <div className="h-4 bg-sindri-700 rounded w-1/2" />
        </div>
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="text-center py-8">
        <p className="text-red-400">Failed to load session</p>
        <p className="text-sm text-sindri-500 mt-1">
          Session may not exist or backend is not running
        </p>
        <Link
          to="/sessions"
          className="text-forge-400 hover:text-forge-300 text-sm mt-4 inline-block"
        >
          ← Back to sessions
        </Link>
      </div>
    )
  }

  const statusStyles = {
    completed: 'bg-green-900/50 text-green-400 border-green-700',
    failed: 'bg-red-900/50 text-red-400 border-red-700',
    active: 'bg-blue-900/50 text-blue-400 border-blue-700',
    cancelled: 'bg-gray-900/50 text-gray-400 border-gray-600',
  }

  const statusStyle = statusStyles[session.status] || statusStyles.cancelled

  const createdAt = new Date(session.created_at)
  const completedAt = session.completed_at
    ? new Date(session.completed_at)
    : null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            to="/sessions"
            className="text-sm text-sindri-400 hover:text-sindri-200 mb-2 inline-block"
          >
            ← Back to sessions
          </Link>
          <h1 className="text-2xl font-bold text-sindri-100">{session.task}</h1>
          <p className="text-sm text-sindri-500 font-mono mt-1">{session.id}</p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded border ${statusStyle}`}
        >
          {session.status}
        </span>
      </div>

      {/* Metadata */}
      <div className="card p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-sindri-500">Model</p>
            <p className="text-sindri-200">{session.model}</p>
          </div>
          <div>
            <p className="text-xs text-sindri-500">Iterations</p>
            <p className="text-sindri-200">{session.iterations}</p>
          </div>
          <div>
            <p className="text-xs text-sindri-500">Created</p>
            <p className="text-sindri-200">{createdAt.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-sindri-500">Completed</p>
            <p className="text-sindri-200">
              {completedAt ? completedAt.toLocaleString() : 'In progress'}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-sindri-700">
        <div className="flex gap-4">
          <button
            onClick={() => setActiveTab('conversation')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'conversation'
                ? 'border-forge-500 text-forge-400'
                : 'border-transparent text-sindri-400 hover:text-sindri-200'
            }`}
          >
            💬 Conversation ({session.turns?.length ?? 0})
          </button>
          <button
            onClick={() => setActiveTab('files')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'files'
                ? 'border-forge-500 text-forge-400'
                : 'border-transparent text-sindri-400 hover:text-sindri-200'
            }`}
          >
            📁 File Changes ({fileChanges?.total_changes ?? 0})
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'conversation' ? (
        <div className="card p-4">
          <h2 className="text-lg font-semibold text-sindri-100 mb-4">
            Conversation ({session.turns?.length ?? 0} turns)
          </h2>
          <div className="space-y-4">
            {session.turns?.length === 0 ? (
              <p className="text-sindri-500 text-center py-4">No turns yet</p>
            ) : (
              session.turns?.map((turn, index) => (
                <TurnDisplay key={index} turn={turn} />
              ))
            )}
          </div>
        </div>
      ) : (
        <div className="card p-4">
          <h2 className="text-lg font-semibold text-sindri-100 mb-4">
            File Changes
          </h2>
          <CodeDiffViewer
            fileChanges={fileChanges ?? null}
            isLoading={fileChangesLoading}
            error={fileChangesError}
          />
        </div>
      )}
    </div>
  )
}

interface TurnDisplayProps {
  turn: Turn
}

function TurnDisplay({ turn }: TurnDisplayProps) {
  const roleStyles = {
    user: {
      bg: 'bg-blue-900/20 border-blue-800',
      label: 'User',
      labelColor: 'text-blue-400',
    },
    assistant: {
      bg: 'bg-purple-900/20 border-purple-800',
      label: 'Assistant',
      labelColor: 'text-purple-400',
    },
    tool: {
      bg: 'bg-yellow-900/20 border-yellow-800',
      label: 'Tool',
      labelColor: 'text-yellow-400',
    },
  }

  const style = roleStyles[turn.role] || roleStyles.assistant
  const timestamp = new Date(turn.timestamp).toLocaleTimeString()

  return (
    <div className={`p-4 rounded-lg border ${style.bg}`}>
      <div className="flex items-center justify-between mb-2">
        <span className={`text-sm font-medium ${style.labelColor}`}>
          {style.label}
        </span>
        <span className="text-xs text-sindri-500">{timestamp}</span>
      </div>
      <div className="text-sindri-200 text-sm whitespace-pre-wrap">
        {turn.content}
      </div>
      {turn.tool_calls && turn.tool_calls.length > 0 && (
        <div className="mt-3 pt-3 border-t border-sindri-700">
          <p className="text-xs text-sindri-500 mb-2">Tool Calls:</p>
          <div className="space-y-2">
            {turn.tool_calls.map((call, i) => (
              <div
                key={i}
                className="bg-sindri-800 rounded p-2 text-xs font-mono"
              >
                <span className="text-forge-400">{call.name}</span>
                <pre className="text-sindri-400 mt-1 overflow-x-auto">
                  {JSON.stringify(call.arguments, null, 2)}
                </pre>
                {call.result && (
                  <div className="mt-2 pt-2 border-t border-sindri-700 text-sindri-300">
                    {call.result}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
