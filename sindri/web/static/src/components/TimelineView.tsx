/**
 * TimelineView - Horizontal timeline visualization of session execution
 * Shows parallel execution, tool calls, and allows filtering by type/agent
 */

import { useState, useMemo } from 'react'
import type { Turn, FileChange } from '../types/api'

// Timeline event types for visualization
interface TimelineEvent {
  id: string
  type: 'turn' | 'tool' | 'file_op'
  category: 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'file_read' | 'file_write' | 'file_edit'
  name: string
  content: string
  timestamp: Date
  duration?: number // in ms
  success?: boolean
  turnIndex: number
  toolIndex?: number
}

interface TimelineViewProps {
  turns: Turn[]
  fileChanges: FileChange[] | null
  sessionStart: Date
  sessionEnd: Date | null
}

// Color mapping for event categories
const categoryColors: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  user: { bg: 'bg-blue-900/30', border: 'border-blue-700', text: 'text-blue-400', dot: 'bg-blue-500' },
  assistant: { bg: 'bg-purple-900/30', border: 'border-purple-700', text: 'text-purple-400', dot: 'bg-purple-500' },
  tool_call: { bg: 'bg-yellow-900/30', border: 'border-yellow-700', text: 'text-yellow-400', dot: 'bg-yellow-500' },
  tool_result: { bg: 'bg-green-900/30', border: 'border-green-700', text: 'text-green-400', dot: 'bg-green-500' },
  file_read: { bg: 'bg-cyan-900/30', border: 'border-cyan-700', text: 'text-cyan-400', dot: 'bg-cyan-500' },
  file_write: { bg: 'bg-orange-900/30', border: 'border-orange-700', text: 'text-orange-400', dot: 'bg-orange-500' },
  file_edit: { bg: 'bg-pink-900/30', border: 'border-pink-700', text: 'text-pink-400', dot: 'bg-pink-500' },
}

// Category labels for display
const categoryLabels: Record<string, string> = {
  user: 'User Input',
  assistant: 'Assistant',
  tool_call: 'Tool Call',
  tool_result: 'Tool Result',
  file_read: 'File Read',
  file_write: 'File Write',
  file_edit: 'File Edit',
}

export function TimelineView({ turns, fileChanges, sessionStart, sessionEnd }: TimelineViewProps) {
  const [filterCategory, setFilterCategory] = useState<string | null>(null)
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set())
  const [viewMode, setViewMode] = useState<'timeline' | 'list'>('timeline')

  // Build timeline events from turns and file changes
  const events = useMemo(() => {
    const result: TimelineEvent[] = []

    // Process turns
    turns.forEach((turn, turnIndex) => {
      const timestamp = new Date(turn.timestamp)

      // Add the turn itself
      if (turn.role === 'user') {
        result.push({
          id: `turn-${turnIndex}-user`,
          type: 'turn',
          category: 'user',
          name: 'User Input',
          content: turn.content,
          timestamp,
          turnIndex,
        })
      } else if (turn.role === 'assistant') {
        result.push({
          id: `turn-${turnIndex}-assistant`,
          type: 'turn',
          category: 'assistant',
          name: 'Assistant Response',
          content: turn.content,
          timestamp,
          turnIndex,
        })

        // Add tool calls from assistant turns
        if (turn.tool_calls && turn.tool_calls.length > 0) {
          turn.tool_calls.forEach((call, toolIndex) => {
            result.push({
              id: `turn-${turnIndex}-tool-${toolIndex}`,
              type: 'tool',
              category: 'tool_call',
              name: call.name,
              content: JSON.stringify(call.arguments, null, 2),
              timestamp: new Date(timestamp.getTime() + toolIndex * 100), // Slightly offset
              turnIndex,
              toolIndex,
            })

            if (call.result) {
              result.push({
                id: `turn-${turnIndex}-result-${toolIndex}`,
                type: 'tool',
                category: 'tool_result',
                name: `${call.name} result`,
                content: call.result,
                timestamp: new Date(timestamp.getTime() + toolIndex * 100 + 50),
                success: !call.result.toLowerCase().includes('error'),
                turnIndex,
                toolIndex,
              })
            }
          })
        }
      } else if (turn.role === 'tool') {
        result.push({
          id: `turn-${turnIndex}-tool-response`,
          type: 'turn',
          category: 'tool_result',
          name: 'Tool Response',
          content: turn.content,
          timestamp,
          turnIndex,
        })
      }
    })

    // Process file changes
    if (fileChanges) {
      fileChanges.forEach((change, idx) => {
        const category = change.operation === 'read' ? 'file_read'
          : change.operation === 'write' ? 'file_write'
          : 'file_edit'

        result.push({
          id: `file-${idx}`,
          type: 'file_op',
          category,
          name: change.file_path.split('/').pop() || change.file_path,
          content: change.file_path,
          timestamp: new Date(change.timestamp),
          success: change.success,
          turnIndex: change.turn_index,
        })
      })
    }

    // Sort by timestamp
    result.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())

    return result
  }, [turns, fileChanges])

  // Filter events
  const filteredEvents = useMemo(() => {
    if (!filterCategory) return events
    return events.filter(e => e.category === filterCategory)
  }, [events, filterCategory])

  // Calculate timeline dimensions
  const timeRange = useMemo(() => {
    if (events.length === 0) return { start: sessionStart, end: sessionEnd || new Date(), duration: 0 }
    const start = sessionStart
    const end = sessionEnd || new Date()
    const duration = end.getTime() - start.getTime()
    return { start, end, duration: Math.max(duration, 1000) } // Minimum 1 second
  }, [events, sessionStart, sessionEnd])

  // Get unique categories for filter
  const categories = useMemo(() => {
    const cats = new Set(events.map(e => e.category))
    return Array.from(cats)
  }, [events])

  const toggleExpanded = (id: string) => {
    setExpandedEvents(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const expandAll = () => {
    setExpandedEvents(new Set(filteredEvents.map(e => e.id)))
  }

  const collapseAll = () => {
    setExpandedEvents(new Set())
  }

  // Calculate position on timeline (0-100%)
  const getTimelinePosition = (timestamp: Date): number => {
    const offset = timestamp.getTime() - timeRange.start.getTime()
    return Math.min(100, Math.max(0, (offset / timeRange.duration) * 100))
  }

  // Format duration
  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}m`
  }

  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-sindri-500">
        No events to display in timeline
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* View Mode Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-sindri-400">View:</span>
          <div className="flex rounded-lg border border-sindri-700 overflow-hidden">
            <button
              onClick={() => setViewMode('timeline')}
              className={`px-3 py-1.5 text-sm transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-forge-600 text-white'
                  : 'bg-sindri-800 text-sindri-300 hover:bg-sindri-700'
              }`}
            >
              Timeline
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`px-3 py-1.5 text-sm transition-colors ${
                viewMode === 'list'
                  ? 'bg-forge-600 text-white'
                  : 'bg-sindri-800 text-sindri-300 hover:bg-sindri-700'
              }`}
            >
              List
            </button>
          </div>
        </div>

        {/* Filter by Category */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-sindri-400">Filter:</span>
          <select
            value={filterCategory || ''}
            onChange={(e) => setFilterCategory(e.target.value || null)}
            className="input text-sm py-1.5 min-w-[140px]"
          >
            <option value="">All Events ({events.length})</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>
                {categoryLabels[cat]} ({events.filter(e => e.category === cat).length})
              </option>
            ))}
          </select>
        </div>

        {/* Expand/Collapse */}
        <div className="flex items-center gap-2">
          <button
            onClick={expandAll}
            className="btn btn-ghost text-sm py-1"
          >
            Expand All
          </button>
          <button
            onClick={collapseAll}
            className="btn btn-ghost text-sm py-1"
          >
            Collapse All
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="flex flex-wrap gap-4 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-sindri-500">Duration:</span>
          <span className="text-sindri-200">{formatDuration(timeRange.duration)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sindri-500">Events:</span>
          <span className="text-sindri-200">{filteredEvents.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sindri-500">Tool Calls:</span>
          <span className="text-sindri-200">{events.filter(e => e.category === 'tool_call').length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sindri-500">File Operations:</span>
          <span className="text-sindri-200">{events.filter(e => e.type === 'file_op').length}</span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        {categories.map(cat => {
          const colors = categoryColors[cat]
          return (
            <button
              key={cat}
              onClick={() => setFilterCategory(filterCategory === cat ? null : cat)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded transition-opacity ${
                filterCategory && filterCategory !== cat ? 'opacity-50' : ''
              }`}
            >
              <span className={`w-2.5 h-2.5 rounded-full ${colors.dot}`} />
              <span className={colors.text}>{categoryLabels[cat]}</span>
            </button>
          )
        })}
      </div>

      {viewMode === 'timeline' ? (
        /* Timeline View */
        <div className="relative">
          {/* Time axis */}
          <div className="h-8 border-b border-sindri-700 relative mb-4">
            <div className="absolute left-0 text-xs text-sindri-500">
              {timeRange.start.toLocaleTimeString()}
            </div>
            <div className="absolute right-0 text-xs text-sindri-500">
              {timeRange.end.toLocaleTimeString()}
            </div>
            {/* Time markers */}
            {[25, 50, 75].map(pct => (
              <div
                key={pct}
                className="absolute top-0 bottom-0 border-l border-sindri-800"
                style={{ left: `${pct}%` }}
              >
                <span className="absolute -bottom-5 -translate-x-1/2 text-xs text-sindri-600">
                  {new Date(timeRange.start.getTime() + (timeRange.duration * pct / 100)).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>

          {/* Events on timeline */}
          <div className="relative min-h-[200px] pt-4">
            {/* Vertical gridlines */}
            {[0, 25, 50, 75, 100].map(pct => (
              <div
                key={pct}
                className="absolute top-0 bottom-0 border-l border-sindri-800/50"
                style={{ left: `${pct}%` }}
              />
            ))}

            {/* Event dots and cards */}
            {filteredEvents.map((event) => {
              const pos = getTimelinePosition(event.timestamp)
              const colors = categoryColors[event.category]
              const isExpanded = expandedEvents.has(event.id)

              return (
                <div
                  key={event.id}
                  className="mb-2 relative"
                  style={{ paddingLeft: `${pos}%` }}
                >
                  <button
                    onClick={() => toggleExpanded(event.id)}
                    className={`
                      flex items-start gap-2 p-2 rounded-lg border transition-all
                      ${colors.bg} ${colors.border}
                      hover:ring-1 hover:ring-sindri-500
                      ${isExpanded ? 'w-full max-w-xl' : 'max-w-xs'}
                    `}
                  >
                    {/* Dot indicator */}
                    <span className={`w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0 ${colors.dot}`} />

                    <div className="flex-1 min-w-0 text-left">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium ${colors.text}`}>
                          {event.name}
                        </span>
                        {event.success === false && (
                          <span className="text-xs px-1.5 py-0.5 bg-red-900/50 text-red-400 rounded">
                            Failed
                          </span>
                        )}
                        <span className="text-xs text-sindri-500">
                          {event.timestamp.toLocaleTimeString()}
                        </span>
                      </div>

                      {isExpanded && (
                        <pre className="mt-2 text-xs text-sindri-300 whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto">
                          {event.content.slice(0, 1000)}
                          {event.content.length > 1000 && '...'}
                        </pre>
                      )}
                    </div>
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        /* List View */
        <div className="space-y-2">
          {filteredEvents.map((event) => {
            const colors = categoryColors[event.category]
            const isExpanded = expandedEvents.has(event.id)

            return (
              <div
                key={event.id}
                className={`rounded-lg border ${colors.bg} ${colors.border}`}
              >
                <button
                  onClick={() => toggleExpanded(event.id)}
                  className="w-full flex items-center gap-3 p-3 text-left"
                >
                  {/* Expand indicator */}
                  <span className={`text-sindri-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
                    ▶
                  </span>

                  {/* Dot */}
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${colors.dot}`} />

                  {/* Time */}
                  <span className="text-xs text-sindri-500 font-mono w-20 flex-shrink-0">
                    {event.timestamp.toLocaleTimeString()}
                  </span>

                  {/* Category badge */}
                  <span className={`text-xs px-2 py-0.5 rounded ${colors.bg} ${colors.text} border ${colors.border}`}>
                    {categoryLabels[event.category]}
                  </span>

                  {/* Name */}
                  <span className="text-sm text-sindri-200 flex-1 truncate">
                    {event.name}
                  </span>

                  {/* Status */}
                  {event.success === false && (
                    <span className="text-xs px-1.5 py-0.5 bg-red-900/50 text-red-400 rounded">
                      Failed
                    </span>
                  )}
                </button>

                {isExpanded && (
                  <div className="px-3 pb-3 border-t border-sindri-700/50">
                    <pre className="mt-2 text-xs text-sindri-300 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto bg-sindri-900/50 rounded p-2">
                      {event.content}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
