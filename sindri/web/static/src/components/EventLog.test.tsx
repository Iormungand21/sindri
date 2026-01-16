import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EventLog } from './EventLog'
import type { WebSocketEvent } from '../types/api'

describe('EventLog', () => {
  const mockEvents: WebSocketEvent[] = [
    {
      type: 'TASK_START',
      data: { task: 'Test task' },
      timestamp: new Date().toISOString(),
    },
    {
      type: 'AGENT_START',
      data: { agent: 'huginn', model: 'qwen2.5-coder:7b' },
      timestamp: new Date().toISOString(),
    },
    {
      type: 'TOOL_START',
      data: { tool: 'write_file' },
      timestamp: new Date().toISOString(),
    },
  ]

  it('renders empty state when no events', () => {
    render(<EventLog events={[]} />)
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument()
  })

  it('displays event labels', () => {
    render(<EventLog events={mockEvents} />)
    expect(screen.getByText('Task Started')).toBeInTheDocument()
    expect(screen.getByText('Agent Started')).toBeInTheDocument()
    expect(screen.getByText('Tool Started')).toBeInTheDocument()
  })

  it('shows event summaries', () => {
    render(<EventLog events={mockEvents} />)
    expect(screen.getByText('Test task')).toBeInTheDocument()
    expect(screen.getByText(/huginn using qwen/i)).toBeInTheDocument()
    expect(screen.getByText('write_file')).toBeInTheDocument()
  })

  it('shows only last 5 events when not expanded', () => {
    const manyEvents: WebSocketEvent[] = Array.from({ length: 10 }, (_, i) => ({
      type: 'TOOL_START',
      data: { tool: `tool_${i}` },
      timestamp: new Date().toISOString(),
    }))
    render(<EventLog events={manyEvents} expanded={false} />)
    // Only last 5 should be shown
    expect(screen.queryByText('tool_0')).not.toBeInTheDocument()
    expect(screen.getByText('tool_9')).toBeInTheDocument()
  })

  it('shows all events when expanded', () => {
    const manyEvents: WebSocketEvent[] = Array.from({ length: 10 }, (_, i) => ({
      type: 'TOOL_START',
      data: { tool: `tool_${i}` },
      timestamp: new Date().toISOString(),
    }))
    render(<EventLog events={manyEvents} expanded={true} />)
    // All should be shown
    expect(screen.getByText('tool_0')).toBeInTheDocument()
    expect(screen.getByText('tool_9')).toBeInTheDocument()
  })

  it('displays timestamps', () => {
    const event: WebSocketEvent = {
      type: 'TASK_START',
      data: { task: 'Test' },
      timestamp: new Date('2026-01-15T10:30:00').toISOString(),
    }
    render(<EventLog events={[event]} />)
    // Should contain time string (format depends on locale)
    expect(screen.getByText(/10:30/)).toBeInTheDocument()
  })
})
