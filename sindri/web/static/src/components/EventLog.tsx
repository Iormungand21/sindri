/**
 * EventLog - Real-time event display
 */

import type { WebSocketEvent } from '../types/api'

interface EventLogProps {
  events: WebSocketEvent[]
  expanded?: boolean
}

export function EventLog({ events, expanded = false }: EventLogProps) {
  const displayEvents = expanded ? events : events.slice(-5)

  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-sindri-500">
        <p>Waiting for events...</p>
        <p className="text-sm mt-1">Events will appear here when tasks run</p>
      </div>
    )
  }

  return (
    <div
      className={`space-y-2 overflow-y-auto scrollbar-thin ${
        expanded ? 'max-h-96' : 'max-h-48'
      }`}
    >
      {displayEvents.map((event, index) => (
        <EventRow key={`${event.timestamp}-${index}`} event={event} />
      ))}
    </div>
  )
}

interface EventRowProps {
  event: WebSocketEvent
}

function EventRow({ event }: EventRowProps) {
  const eventStyles: Record<string, { bg: string; icon: string; label: string }> = {
    TASK_START: { bg: 'bg-blue-900/30', icon: '🚀', label: 'Task Started' },
    TASK_COMPLETE: { bg: 'bg-green-900/30', icon: '✅', label: 'Task Complete' },
    TASK_FAILED: { bg: 'bg-red-900/30', icon: '❌', label: 'Task Failed' },
    AGENT_START: { bg: 'bg-purple-900/30', icon: '🤖', label: 'Agent Started' },
    AGENT_OUTPUT: { bg: 'bg-sindri-800', icon: '💬', label: 'Agent Output' },
    AGENT_COMPLETE: { bg: 'bg-purple-900/30', icon: '✨', label: 'Agent Complete' },
    TOOL_START: { bg: 'bg-yellow-900/30', icon: '🔧', label: 'Tool Started' },
    TOOL_RESULT: { bg: 'bg-yellow-900/30', icon: '📋', label: 'Tool Result' },
    DELEGATION_START: { bg: 'bg-indigo-900/30', icon: '📤', label: 'Delegating' },
    DELEGATION_COMPLETE: { bg: 'bg-indigo-900/30', icon: '📥', label: 'Delegation Done' },
    MODEL_LOADING: { bg: 'bg-orange-900/30', icon: '⏳', label: 'Loading Model' },
    MODEL_LOADED: { bg: 'bg-orange-900/30', icon: '✓', label: 'Model Loaded' },
    MODEL_UNLOADED: { bg: 'bg-orange-900/30', icon: '🗑️', label: 'Model Unloaded' },
    STREAMING_TOKEN: { bg: 'bg-sindri-800', icon: '▸', label: 'Token' },
    PLAN_PROPOSED: { bg: 'bg-cyan-900/30', icon: '📝', label: 'Plan Proposed' },
    PATTERN_LEARNED: { bg: 'bg-emerald-900/30', icon: '🧠', label: 'Pattern Learned' },
  }

  const style = eventStyles[event.type] || {
    bg: 'bg-sindri-800',
    icon: '•',
    label: event.type,
  }

  const time = new Date(event.timestamp).toLocaleTimeString()
  const summary = getEventSummary(event)

  return (
    <div className={`p-2 rounded ${style.bg} text-xs`}>
      <div className="flex items-center gap-2">
        <span>{style.icon}</span>
        <span className="font-medium text-sindri-200">{style.label}</span>
        <span className="text-sindri-500 ml-auto">{time}</span>
      </div>
      {summary && (
        <p className="mt-1 text-sindri-400 truncate pl-6">{summary}</p>
      )}
    </div>
  )
}

function getEventSummary(event: WebSocketEvent): string | null {
  const { data } = event

  switch (event.type) {
    case 'TASK_START':
      return data.task as string
    case 'AGENT_START':
      return `${data.agent} using ${data.model}`
    case 'TOOL_START':
      return data.tool as string
    case 'TOOL_RESULT':
      return data.success ? 'Success' : 'Failed'
    case 'DELEGATION_START':
      return `${data.from_agent} → ${data.to_agent}: ${data.task}`
    case 'MODEL_LOADING':
    case 'MODEL_LOADED':
      return data.model as string
    case 'AGENT_OUTPUT':
      const content = data.content as string
      return content?.slice(0, 100) + (content?.length > 100 ? '...' : '')
    case 'PLAN_PROPOSED':
      return `${data.step_count} steps, ${(data.agents as string[])?.join(', ')}`
    default:
      return null
  }
}
