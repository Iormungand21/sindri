/**
 * SessionReplay - Step-by-step replay of past sessions
 * Educational/debugging tool for understanding agent execution flow
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { Turn, ToolCall } from '../types/api'

interface SessionReplayProps {
  turns: Turn[]
  sessionStart: Date
  sessionEnd: Date | null
}

// Playback speeds
const SPEEDS = [0.5, 1, 2, 4] as const
type Speed = (typeof SPEEDS)[number]

// Calculate delay for auto-play based on turn type
function getStepDelay(turn: Turn, speed: Speed): number {
  const baseDelay = turn.role === 'user' ? 1500 : turn.tool_calls?.length ? 2500 : 2000
  return baseDelay / speed
}

export function SessionReplay({ turns, sessionStart, sessionEnd }: SessionReplayProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState<Speed>(1)
  const [expandedToolCalls, setExpandedToolCalls] = useState<Set<string>>(new Set())
  const playIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Total steps = number of turns
  const totalSteps = turns.length

  // Current turn being displayed
  const currentTurn = useMemo(() => turns[currentStep] || null, [turns, currentStep])

  // Turns visible up to current step
  const visibleTurns = useMemo(() => turns.slice(0, currentStep + 1), [turns, currentStep])

  // Progress percentage
  const progress = totalSteps > 0 ? ((currentStep + 1) / totalSteps) * 100 : 0

  // Auto-scroll to current turn
  useEffect(() => {
    if (containerRef.current) {
      const turnElement = containerRef.current.querySelector(`[data-step="${currentStep}"]`)
      if (turnElement && typeof turnElement.scrollIntoView === 'function') {
        turnElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }
  }, [currentStep])

  // Handle auto-play
  useEffect(() => {
    if (isPlaying && currentStep < totalSteps - 1) {
      const delay = getStepDelay(turns[currentStep], speed)
      playIntervalRef.current = setTimeout(() => {
        setCurrentStep((prev) => prev + 1)
      }, delay)
    } else if (isPlaying && currentStep >= totalSteps - 1) {
      // Reached the end
      setIsPlaying(false)
    }

    return () => {
      if (playIntervalRef.current) {
        clearTimeout(playIntervalRef.current)
      }
    }
  }, [isPlaying, currentStep, totalSteps, turns, speed])

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }

      switch (e.key) {
        case ' ':
          e.preventDefault()
          togglePlay()
          break
        case 'ArrowLeft':
          e.preventDefault()
          stepBackward()
          break
        case 'ArrowRight':
          e.preventDefault()
          stepForward()
          break
        case 'Home':
          e.preventDefault()
          jumpToStart()
          break
        case 'End':
          e.preventDefault()
          jumpToEnd()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Playback controls
  const togglePlay = useCallback(() => {
    if (currentStep >= totalSteps - 1 && !isPlaying) {
      // If at end, restart from beginning
      setCurrentStep(0)
    }
    setIsPlaying((prev) => !prev)
  }, [currentStep, totalSteps, isPlaying])

  const stepForward = useCallback(() => {
    setIsPlaying(false)
    setCurrentStep((prev) => Math.min(prev + 1, totalSteps - 1))
  }, [totalSteps])

  const stepBackward = useCallback(() => {
    setIsPlaying(false)
    setCurrentStep((prev) => Math.max(prev - 1, 0))
  }, [])

  const jumpToStart = useCallback(() => {
    setIsPlaying(false)
    setCurrentStep(0)
  }, [])

  const jumpToEnd = useCallback(() => {
    setIsPlaying(false)
    setCurrentStep(totalSteps - 1)
  }, [totalSteps])

  const jumpToStep = useCallback(
    (step: number) => {
      setIsPlaying(false)
      setCurrentStep(Math.max(0, Math.min(step, totalSteps - 1)))
    },
    [totalSteps]
  )

  // Handle progress bar click
  const handleProgressClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect()
      const x = e.clientX - rect.left
      const percentage = x / rect.width
      const step = Math.round(percentage * (totalSteps - 1))
      jumpToStep(step)
    },
    [totalSteps, jumpToStep]
  )

  // Toggle tool call expansion
  const toggleToolCall = useCallback((id: string) => {
    setExpandedToolCalls((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  // Format timestamp relative to session start
  const formatRelativeTime = useCallback(
    (timestamp: string): string => {
      const time = new Date(timestamp)
      const diff = time.getTime() - sessionStart.getTime()
      const seconds = Math.floor(diff / 1000)
      const minutes = Math.floor(seconds / 60)
      const remainingSeconds = seconds % 60
      if (minutes > 0) {
        return `+${minutes}m ${remainingSeconds}s`
      }
      return `+${seconds}s`
    },
    [sessionStart]
  )

  if (turns.length === 0) {
    return (
      <div className="text-center py-8 text-sindri-500">
        No turns to replay in this session
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Playback Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-sindri-800 rounded-lg p-4 border border-sindri-700">
        <div className="flex items-center gap-2">
          {/* Skip to start */}
          <button
            onClick={jumpToStart}
            disabled={currentStep === 0}
            className="btn btn-ghost p-2"
            title="Jump to start (Home)"
            aria-label="Jump to start"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 6h2v12H6V6zm3.5 6l8.5 6V6l-8.5 6z" />
            </svg>
          </button>

          {/* Step backward */}
          <button
            onClick={stepBackward}
            disabled={currentStep === 0}
            className="btn btn-ghost p-2"
            title="Step backward (Left Arrow)"
            aria-label="Step backward"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 6h2v12H6V6zm3.5 6l8.5 6V6l-8.5 6z" />
            </svg>
          </button>

          {/* Play/Pause */}
          <button
            onClick={togglePlay}
            className="btn btn-primary p-3 rounded-full"
            title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7L8 5z" />
              </svg>
            )}
          </button>

          {/* Step forward */}
          <button
            onClick={stepForward}
            disabled={currentStep >= totalSteps - 1}
            className="btn btn-ghost p-2"
            title="Step forward (Right Arrow)"
            aria-label="Step forward"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M18 6h-2v12h2V6zM6 18l8.5-6L6 6v12z" />
            </svg>
          </button>

          {/* Skip to end */}
          <button
            onClick={jumpToEnd}
            disabled={currentStep >= totalSteps - 1}
            className="btn btn-ghost p-2"
            title="Jump to end (End)"
            aria-label="Jump to end"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M18 6h-2v12h2V6zM6 18l8.5-6L6 6v12z" />
            </svg>
          </button>
        </div>

        {/* Speed control */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-sindri-400">Speed:</span>
          <div className="flex rounded-lg border border-sindri-700 overflow-hidden">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`px-3 py-1.5 text-sm transition-colors ${
                  speed === s
                    ? 'bg-forge-600 text-white'
                    : 'bg-sindri-800 text-sindri-300 hover:bg-sindri-700'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>

        {/* Step counter */}
        <div className="text-sm text-sindri-300">
          <span className="font-mono">
            {currentStep + 1} / {totalSteps}
          </span>
          <span className="text-sindri-500 ml-2">
            ({Math.round(progress)}%)
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div
        className="h-3 bg-sindri-800 rounded-full cursor-pointer border border-sindri-700 overflow-hidden"
        onClick={handleProgressClick}
        role="slider"
        aria-valuenow={currentStep + 1}
        aria-valuemin={1}
        aria-valuemax={totalSteps}
        aria-label="Replay progress"
      >
        <div
          className="h-full bg-gradient-to-r from-forge-600 to-forge-500 transition-all duration-300 rounded-full"
          style={{ width: `${progress}%` }}
        />
        {/* Step markers */}
        <div className="relative -mt-3 h-3">
          {turns.map((_, idx) => (
            <div
              key={idx}
              className={`absolute w-1 h-full transition-colors ${
                idx <= currentStep ? 'bg-forge-400/50' : 'bg-sindri-600/30'
              }`}
              style={{ left: `${((idx + 0.5) / totalSteps) * 100}%` }}
            />
          ))}
        </div>
      </div>

      {/* Timeline strip */}
      <div className="flex gap-1 py-2 overflow-x-auto">
        {turns.map((turn, idx) => (
          <button
            key={idx}
            onClick={() => jumpToStep(idx)}
            className={`
              flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium
              transition-all duration-200
              ${
                idx === currentStep
                  ? 'bg-forge-500 text-white ring-2 ring-forge-400 ring-offset-2 ring-offset-sindri-900'
                  : idx < currentStep
                    ? 'bg-forge-900/50 text-forge-400 hover:bg-forge-800/50'
                    : 'bg-sindri-800 text-sindri-500 hover:bg-sindri-700'
              }
            `}
            title={`Step ${idx + 1}: ${turn.role}`}
          >
            {turn.role === 'user' ? 'U' : turn.role === 'assistant' ? 'A' : 'T'}
          </button>
        ))}
      </div>

      {/* Keyboard shortcuts hint */}
      <div className="flex flex-wrap gap-4 text-xs text-sindri-500 justify-center">
        <span>
          <kbd className="px-1.5 py-0.5 bg-sindri-800 rounded">Space</kbd> Play/Pause
        </span>
        <span>
          <kbd className="px-1.5 py-0.5 bg-sindri-800 rounded">&larr;</kbd>
          <kbd className="px-1.5 py-0.5 bg-sindri-800 rounded ml-1">&rarr;</kbd> Step
        </span>
        <span>
          <kbd className="px-1.5 py-0.5 bg-sindri-800 rounded">Home</kbd>
          <kbd className="px-1.5 py-0.5 bg-sindri-800 rounded ml-1">End</kbd> Jump
        </span>
      </div>

      {/* Turn display area */}
      <div ref={containerRef} className="space-y-4 max-h-[60vh] overflow-y-auto">
        {visibleTurns.map((turn, idx) => (
          <ReplayTurnDisplay
            key={idx}
            turn={turn}
            stepIndex={idx}
            isCurrentStep={idx === currentStep}
            isExpanded={idx === currentStep || idx === currentStep - 1}
            relativeTime={formatRelativeTime(turn.timestamp)}
            expandedToolCalls={expandedToolCalls}
            onToggleToolCall={toggleToolCall}
          />
        ))}

        {/* "More steps coming" indicator when not at end */}
        {currentStep < totalSteps - 1 && (
          <div className="flex items-center justify-center gap-2 py-4 text-sindri-500">
            <div className="w-2 h-2 bg-sindri-600 rounded-full animate-pulse" />
            <span className="text-sm">{totalSteps - currentStep - 1} more step(s)...</span>
          </div>
        )}
      </div>
    </div>
  )
}

interface ReplayTurnDisplayProps {
  turn: Turn
  stepIndex: number
  isCurrentStep: boolean
  isExpanded: boolean
  relativeTime: string
  expandedToolCalls: Set<string>
  onToggleToolCall: (id: string) => void
}

function ReplayTurnDisplay({
  turn,
  stepIndex,
  isCurrentStep,
  isExpanded,
  relativeTime,
  expandedToolCalls,
  onToggleToolCall,
}: ReplayTurnDisplayProps) {
  const roleStyles = {
    user: {
      bg: 'bg-blue-900/20',
      border: 'border-blue-800',
      label: 'User',
      labelColor: 'text-blue-400',
      icon: '👤',
    },
    assistant: {
      bg: 'bg-purple-900/20',
      border: 'border-purple-800',
      label: 'Assistant',
      labelColor: 'text-purple-400',
      icon: '🤖',
    },
    tool: {
      bg: 'bg-yellow-900/20',
      border: 'border-yellow-800',
      label: 'Tool Result',
      labelColor: 'text-yellow-400',
      icon: '🔧',
    },
  }

  const style = roleStyles[turn.role] || roleStyles.assistant

  return (
    <div
      data-step={stepIndex}
      className={`
        relative rounded-lg border-2 transition-all duration-300
        ${style.bg}
        ${isCurrentStep ? `${style.border} ring-2 ring-offset-2 ring-offset-sindri-900 ring-forge-500` : 'border-sindri-700/50'}
        ${isCurrentStep ? 'scale-[1.01]' : 'scale-100 opacity-75'}
      `}
    >
      {/* Step indicator badge */}
      <div className="absolute -top-3 -left-3 w-8 h-8 rounded-full bg-sindri-900 border-2 border-sindri-700 flex items-center justify-center">
        <span
          className={`text-xs font-bold ${isCurrentStep ? 'text-forge-400' : 'text-sindri-500'}`}
        >
          {stepIndex + 1}
        </span>
      </div>

      <div className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{style.icon}</span>
            <span className={`font-medium ${style.labelColor}`}>{style.label}</span>
            {isCurrentStep && (
              <span className="px-2 py-0.5 text-xs bg-forge-600 text-white rounded-full animate-pulse">
                Current
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-sindri-500">
            <span>{relativeTime}</span>
            <span>{new Date(turn.timestamp).toLocaleTimeString()}</span>
          </div>
        </div>

        {/* Content */}
        <div
          className={`
            text-sindri-200 text-sm whitespace-pre-wrap transition-all duration-300
            ${isExpanded ? 'max-h-none' : 'max-h-32 overflow-hidden'}
          `}
        >
          {turn.content}
          {!isExpanded && turn.content.length > 200 && (
            <span className="text-sindri-500">...</span>
          )}
        </div>

        {/* Tool calls */}
        {turn.tool_calls && turn.tool_calls.length > 0 && (
          <div className="mt-4 pt-4 border-t border-sindri-700/50">
            <p className="text-xs text-sindri-500 mb-3 flex items-center gap-2">
              <span>🛠️</span>
              Tool Calls ({turn.tool_calls.length})
            </p>
            <div className="space-y-3">
              {turn.tool_calls.map((call, toolIdx) => {
                const toolId = `${stepIndex}-${toolIdx}`
                const isToolExpanded = expandedToolCalls.has(toolId)
                return (
                  <ToolCallDisplay
                    key={toolIdx}
                    call={call}
                    isExpanded={isToolExpanded}
                    onToggle={() => onToggleToolCall(toolId)}
                    isCurrentStep={isCurrentStep}
                  />
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

interface ToolCallDisplayProps {
  call: ToolCall
  isExpanded: boolean
  onToggle: () => void
  isCurrentStep: boolean
}

function ToolCallDisplay({ call, isExpanded, onToggle, isCurrentStep }: ToolCallDisplayProps) {
  const hasResult = Boolean(call.result)
  const isError = call.result?.toLowerCase().includes('error')

  return (
    <div
      className={`
        bg-sindri-800/50 rounded-lg overflow-hidden transition-all duration-300
        ${isCurrentStep ? 'ring-1 ring-forge-600/30' : ''}
      `}
    >
      {/* Tool header - clickable */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3 hover:bg-sindri-700/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span
            className={`transition-transform ${isExpanded ? 'rotate-90' : ''} text-sindri-500`}
          >
            ▶
          </span>
          <span className="text-forge-400 font-mono text-sm">{call.name}</span>
          {hasResult && (
            <span
              className={`px-1.5 py-0.5 text-xs rounded ${
                isError
                  ? 'bg-red-900/50 text-red-400'
                  : 'bg-green-900/50 text-green-400'
              }`}
            >
              {isError ? 'Error' : 'Success'}
            </span>
          )}
        </div>
        <span className="text-xs text-sindri-500">
          {Object.keys(call.arguments).length} arg(s)
        </span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-3 pb-3 space-y-3">
          {/* Arguments */}
          <div>
            <p className="text-xs text-sindri-500 mb-1">Arguments:</p>
            <pre className="text-xs text-sindri-300 bg-sindri-900/50 rounded p-2 overflow-x-auto max-h-32 overflow-y-auto">
              {JSON.stringify(call.arguments, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {call.result && (
            <div>
              <p className="text-xs text-sindri-500 mb-1">Result:</p>
              <pre
                className={`
                  text-xs rounded p-2 overflow-x-auto max-h-48 overflow-y-auto
                  ${isError ? 'bg-red-900/20 text-red-300' : 'bg-sindri-900/50 text-sindri-300'}
                `}
              >
                {call.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
