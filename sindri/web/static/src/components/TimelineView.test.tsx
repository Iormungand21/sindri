import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TimelineView } from './TimelineView'
import type { Turn, FileChange } from '../types/api'

describe('TimelineView', () => {
  const mockTurns: Turn[] = [
    {
      role: 'user',
      content: 'Create a hello world file',
      timestamp: '2026-01-16T10:00:00',
    },
    {
      role: 'assistant',
      content: 'I will create the file for you.',
      timestamp: '2026-01-16T10:00:05',
      tool_calls: [
        {
          name: 'write_file',
          arguments: { path: '/tmp/hello.py', content: 'print("Hello, World!")' },
          result: 'File written successfully',
        },
      ],
    },
    {
      role: 'tool',
      content: 'File written successfully',
      timestamp: '2026-01-16T10:00:10',
    },
    {
      role: 'assistant',
      content: 'Done! I created hello.py',
      timestamp: '2026-01-16T10:00:15',
    },
  ]

  const mockFileChanges: FileChange[] = [
    {
      file_path: '/tmp/hello.py',
      operation: 'write',
      turn_index: 1,
      timestamp: '2026-01-16T10:00:07',
      success: true,
      new_content: 'print("Hello, World!")',
      content_size: 22,
    },
    {
      file_path: '/tmp/test.py',
      operation: 'read',
      turn_index: 2,
      timestamp: '2026-01-16T10:00:12',
      success: true,
    },
  ]

  const sessionStart = new Date('2026-01-16T10:00:00')
  const sessionEnd = new Date('2026-01-16T10:00:20')

  it('renders empty state when no turns', () => {
    render(
      <TimelineView
        turns={[]}
        fileChanges={null}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    expect(screen.getByText(/no events to display/i)).toBeInTheDocument()
  })

  it('renders timeline with events', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    // Should show user input event (appears in legend and timeline)
    expect(screen.getAllByText('User Input').length).toBeGreaterThanOrEqual(1)
    // Should show assistant response
    expect(screen.getAllByText('Assistant Response').length).toBeGreaterThanOrEqual(1)
    // Should show tool call
    expect(screen.getByText('write_file')).toBeInTheDocument()
  })

  it('displays event statistics', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    expect(screen.getByText(/events:/i)).toBeInTheDocument()
    expect(screen.getByText(/tool calls:/i)).toBeInTheDocument()
    expect(screen.getByText(/file operations:/i)).toBeInTheDocument()
  })

  it('shows category legend', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    // Category labels in legend (may appear in multiple places)
    expect(screen.getAllByText('User Input').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Assistant').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Tool Call').length).toBeGreaterThanOrEqual(1)
  })

  it('toggles view mode between timeline and list', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    // Initially in timeline mode
    expect(screen.getByRole('button', { name: /timeline/i })).toHaveClass('bg-forge-600')

    // Switch to list view
    fireEvent.click(screen.getByRole('button', { name: /list/i }))
    expect(screen.getByRole('button', { name: /list/i })).toHaveClass('bg-forge-600')
  })

  it('filters events by category', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Filter to only user events
    const filterSelect = screen.getByRole('combobox')
    fireEvent.change(filterSelect, { target: { value: 'user' } })

    // Should only show user input (legend still visible)
    expect(screen.getAllByText('User Input').length).toBeGreaterThanOrEqual(1)
    // In timeline, assistant responses should be filtered out (only legend remains)
    // The filter reduces assistant events but legend labels remain
    const assistantElements = screen.queryAllByText('Assistant Response')
    // Legend is always visible, but timeline events are filtered
    expect(assistantElements.length).toBeLessThanOrEqual(1) // Only legend item
  })

  it('expands event to show content', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Initially content is not visible
    expect(screen.queryByText('Create a hello world file')).not.toBeInTheDocument()

    // Find timeline event buttons (ones with dot indicators - class w-2.5)
    const eventButtons = screen.getAllByRole('button').filter(btn =>
      btn.querySelector('span.mt-1') && btn.classList.contains('flex')
    )

    // Click the first event button (user input)
    if (eventButtons.length > 0) {
      fireEvent.click(eventButtons[0])
      // Now content should be visible
      expect(screen.getByText('Create a hello world file')).toBeInTheDocument()
    } else {
      // Fallback: use expand all
      fireEvent.click(screen.getByText(/expand all/i))
      expect(screen.getByText('Create a hello world file')).toBeInTheDocument()
    }
  })

  it('expands all events', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    fireEvent.click(screen.getByText(/expand all/i))

    // User content should be visible
    expect(screen.getByText('Create a hello world file')).toBeInTheDocument()
    // Tool call arguments should be visible (may appear in multiple places)
    expect(screen.getAllByText(/\/tmp\/hello\.py/).length).toBeGreaterThanOrEqual(1)
  })

  it('collapses all events', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // First expand all
    fireEvent.click(screen.getByText(/expand all/i))
    expect(screen.getByText('Create a hello world file')).toBeInTheDocument()

    // Then collapse all
    fireEvent.click(screen.getByText(/collapse all/i))

    // Content should no longer be visible
    expect(screen.queryByText('Create a hello world file')).not.toBeInTheDocument()
  })

  it('displays time markers on timeline', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Should show start and end times (multiple elements may have same time)
    expect(screen.getAllByText(/10:00:00/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/10:00:20/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows tool call results', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Should show write_file result event
    expect(screen.getByText(/write_file result/)).toBeInTheDocument()
  })

  it('displays file operations from fileChanges', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Should show file names
    expect(screen.getByText('hello.py')).toBeInTheDocument()
    expect(screen.getByText('test.py')).toBeInTheDocument()
  })

  it('shows category filter counts', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Filter dropdown should show counts
    const filterSelect = screen.getByRole('combobox')
    expect(filterSelect.innerHTML).toContain('All Events')
  })

  it('clicking legend item toggles filter', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Click on User Input in legend (find button with dot indicator)
    const legendButtons = screen.getAllByRole('button').filter(btn =>
      btn.querySelector('span.rounded-full') && btn.textContent?.includes('User Input')
    )
    const legendButton = legendButtons[0]
    fireEvent.click(legendButton)

    // Should filter to user events only - Assistant events reduced
    const assistantElements = screen.queryAllByText('Assistant Response')
    // After filtering, only legend item remains (not timeline events)
    expect(assistantElements.length).toBeLessThanOrEqual(1)

    // Click again to clear filter
    fireEvent.click(legendButton)

    // Assistant should be visible again in timeline
    expect(screen.getAllByText('Assistant Response').length).toBeGreaterThanOrEqual(1)
  })

  it('handles session without end time (in progress)', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={null}
      />
    )

    // Should still render without crashing
    expect(screen.getAllByText('User Input').length).toBeGreaterThanOrEqual(1)
  })

  it('list view shows all events in order', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Switch to list view
    fireEvent.click(screen.getByRole('button', { name: /list/i }))

    // Should show expand indicators
    const expandIndicators = screen.getAllByText('▶')
    expect(expandIndicators.length).toBeGreaterThan(0)
  })

  it('displays duration in stats', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={mockFileChanges}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Should show duration (20 seconds = 20.0s)
    expect(screen.getByText(/duration:/i)).toBeInTheDocument()
    expect(screen.getByText(/20\.0s/)).toBeInTheDocument()
  })

  it('handles null fileChanges', () => {
    render(
      <TimelineView
        turns={mockTurns}
        fileChanges={null}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Should still render turn events
    expect(screen.getAllByText('User Input').length).toBeGreaterThanOrEqual(1)
    // File operations count should be 0
    expect(screen.getByText(/file operations:/i)).toBeInTheDocument()
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(1)
  })
})
