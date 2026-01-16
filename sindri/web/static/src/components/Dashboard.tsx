/**
 * Dashboard - Main page with metrics, task input, and recent activity
 */

import { useState } from 'react'
import { useMetrics, useCreateTask, useSessions } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import { TaskInput } from './TaskInput'
import { VramGauge } from './VramGauge'
import { RecentTasks } from './RecentTasks'
import { EventLog } from './EventLog'

export function Dashboard() {
  const { data: metrics, isLoading: metricsLoading } = useMetrics()
  const { data: sessions } = useSessions({ limit: 5 })
  const createTask = useCreateTask()
  const { events, isConnected, clearEvents } = useWebSocket()

  const [showEventLog, setShowEventLog] = useState(false)

  const handleSubmitTask = async (description: string) => {
    try {
      await createTask.mutateAsync({ description })
    } catch (error) {
      console.error('Failed to create task:', error)
      throw error
    }
  }

  return (
    <div className="space-y-6">
      {/* Header with status */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-sindri-100">Dashboard</h1>
          <p className="text-sindri-400 text-sm mt-1">
            Monitor and control your LLM orchestration
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm ${
              isConnected
                ? 'bg-green-900/50 text-green-400'
                : 'bg-red-900/50 text-red-400'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'
              }`}
            />
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Metrics cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Sessions"
          value={metrics?.total_sessions ?? 0}
          loading={metricsLoading}
        />
        <MetricCard
          label="Completed"
          value={metrics?.completed_sessions ?? 0}
          loading={metricsLoading}
          variant="success"
        />
        <MetricCard
          label="Failed"
          value={metrics?.failed_sessions ?? 0}
          loading={metricsLoading}
          variant="error"
        />
        <MetricCard
          label="Active"
          value={metrics?.active_sessions ?? 0}
          loading={metricsLoading}
          variant="warning"
        />
      </div>

      {/* VRAM and Task Input row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* VRAM Gauge */}
        <div className="card p-4">
          <h2 className="text-lg font-semibold text-sindri-100 mb-4">
            GPU Memory
          </h2>
          <VramGauge
            used={metrics?.vram_used_gb ?? 0}
            total={metrics?.vram_total_gb ?? 16}
            models={metrics?.loaded_models ?? []}
          />
        </div>

        {/* Task Input */}
        <div className="lg:col-span-2 card p-4">
          <h2 className="text-lg font-semibold text-sindri-100 mb-4">
            New Task
          </h2>
          <TaskInput
            onSubmit={handleSubmitTask}
            isLoading={createTask.isPending}
          />
          {createTask.error && (
            <p className="mt-2 text-sm text-red-400">
              Failed to create task. Please try again.
            </p>
          )}
          {createTask.isSuccess && (
            <p className="mt-2 text-sm text-green-400">
              Task created successfully!
            </p>
          )}
        </div>
      </div>

      {/* Recent Tasks and Event Log */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Tasks */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-sindri-100">
              Recent Tasks
            </h2>
            <a
              href="/sessions"
              className="text-sm text-forge-400 hover:text-forge-300"
            >
              View all
            </a>
          </div>
          <RecentTasks sessions={sessions ?? []} />
        </div>

        {/* Event Log */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-sindri-100">
              Live Events
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={clearEvents}
                className="btn btn-ghost text-sm"
              >
                Clear
              </button>
              <button
                onClick={() => setShowEventLog(!showEventLog)}
                className="btn btn-ghost text-sm"
              >
                {showEventLog ? 'Collapse' : 'Expand'}
              </button>
            </div>
          </div>
          <EventLog events={events} expanded={showEventLog} />
        </div>
      </div>
    </div>
  )
}

interface MetricCardProps {
  label: string
  value: number
  loading?: boolean
  variant?: 'default' | 'success' | 'error' | 'warning'
}

function MetricCard({
  label,
  value,
  loading,
  variant = 'default',
}: MetricCardProps) {
  const colors = {
    default: 'text-sindri-100',
    success: 'text-green-400',
    error: 'text-red-400',
    warning: 'text-yellow-400',
  }

  return (
    <div className="card p-4">
      <p className="text-sm text-sindri-400">{label}</p>
      {loading ? (
        <div className="h-8 w-16 bg-sindri-700 animate-pulse rounded mt-1" />
      ) : (
        <p className={`text-3xl font-bold ${colors[variant]}`}>{value}</p>
      )}
    </div>
  )
}
