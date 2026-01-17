import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { SessionReplay } from './SessionReplay'
import type { Turn } from '../types/api'

describe('SessionReplay', () => {
  // Mock turns for testing
  const mockTurns: Turn[] = [
    {
      role: 'user',
      content: 'Create a hello world file in Python',
      timestamp: '2026-01-16T10:00:00',
    },
    {
      role: 'assistant',
      content: 'I will create a hello world file for you.',
      timestamp: '2026-01-16T10:00:05',
      tool_calls: [
        {
          name: 'write_file',
          arguments: { path: '/tmp/hello.py', content: 'print("Hello, World!")' },
          result: 'File written successfully to /tmp/hello.py',
        },
      ],
    },
    {
      role: 'tool',
      content: 'File written successfully to /tmp/hello.py',
      timestamp: '2026-01-16T10:00:10',
    },
    {
      role: 'assistant',
      content: 'Done! I created hello.py with a simple print statement.',
      timestamp: '2026-01-16T10:00:15',
    },
  ]

  const sessionStart = new Date('2026-01-16T10:00:00')
  const sessionEnd = new Date('2026-01-16T10:00:20')

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders empty state when no turns', () => {
    render(
      <SessionReplay
        turns={[]}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    expect(screen.getByText(/no turns to replay/i)).toBeInTheDocument()
  })

  it('renders playback controls', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    // Play/pause button
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
    // Step buttons
    expect(screen.getByRole('button', { name: /step forward/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /step backward/i })).toBeInTheDocument()
    // Jump buttons
    expect(screen.getByRole('button', { name: /jump to start/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /jump to end/i })).toBeInTheDocument()
  })

  it('displays speed controls', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    expect(screen.getByText('Speed:')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '0.5x' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1x' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '2x' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '4x' })).toBeInTheDocument()
  })

  it('shows step counter', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    // Should show "1 / 4" initially (first step of 4)
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
    expect(screen.getByText('(25%)')).toBeInTheDocument()
  })

  it('displays progress bar', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    const progressBar = screen.getByRole('slider', { name: /replay progress/i })
    expect(progressBar).toBeInTheDocument()
    expect(progressBar).toHaveAttribute('aria-valuenow', '1')
    expect(progressBar).toHaveAttribute('aria-valuemax', '4')
  })

  it('shows timeline strip with step buttons', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    // Should have buttons for each turn type
    const userButtons = screen.getAllByTitle(/step 1: user/i)
    expect(userButtons.length).toBeGreaterThanOrEqual(1)
    const assistantButtons = screen.getAllByTitle(/step 2: assistant/i)
    expect(assistantButtons.length).toBeGreaterThanOrEqual(1)
  })

  it('displays first turn content initially', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    expect(screen.getByText('Create a hello world file in Python')).toBeInTheDocument()
  })

  it('shows current step indicator', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )
    expect(screen.getByText('Current')).toBeInTheDocument()
  })

  it('steps forward when clicking step forward button', async () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Initially at step 1
    expect(screen.getByText('1 / 4')).toBeInTheDocument()

    // Click step forward
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Should now be at step 2
    expect(screen.getByText('2 / 4')).toBeInTheDocument()
    // Should show assistant content
    expect(screen.getByText(/I will create a hello world file/)).toBeInTheDocument()
  })

  it('steps backward when clicking step backward button', async () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Go forward first
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    expect(screen.getByText('2 / 4')).toBeInTheDocument()

    // Then go back
    fireEvent.click(screen.getByRole('button', { name: /step backward/i }))
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
  })

  it('jumps to end when clicking jump to end button', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /jump to end/i }))

    expect(screen.getByText('4 / 4')).toBeInTheDocument()
    expect(screen.getByText('(100%)')).toBeInTheDocument()
  })

  it('jumps to start when clicking jump to start button', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Jump to end first
    fireEvent.click(screen.getByRole('button', { name: /jump to end/i }))
    expect(screen.getByText('4 / 4')).toBeInTheDocument()

    // Then jump to start
    fireEvent.click(screen.getByRole('button', { name: /jump to start/i }))
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
  })

  it('disables step backward at first step', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    const backButton = screen.getByRole('button', { name: /step backward/i })
    expect(backButton).toBeDisabled()
  })

  it('disables step forward at last step', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Jump to end
    fireEvent.click(screen.getByRole('button', { name: /jump to end/i }))

    const forwardButton = screen.getByRole('button', { name: /step forward/i })
    expect(forwardButton).toBeDisabled()
  })

  it('changes speed when clicking speed buttons', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Initially 1x should be active
    expect(screen.getByRole('button', { name: '1x' })).toHaveClass('bg-forge-600')

    // Click 2x
    fireEvent.click(screen.getByRole('button', { name: '2x' }))
    expect(screen.getByRole('button', { name: '2x' })).toHaveClass('bg-forge-600')
    expect(screen.getByRole('button', { name: '1x' })).not.toHaveClass('bg-forge-600')
  })

  it('toggles play/pause when clicking play button', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Initially shows play button
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()

    // Click to play
    fireEvent.click(screen.getByRole('button', { name: /play/i }))

    // Should now show pause button
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()

    // Click to pause
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))

    // Should show play button again
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
  })

  it('auto-advances during playback', async () => {
    vi.useRealTimers() // Use real timers for this test

    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Start playback at 4x speed
    fireEvent.click(screen.getByRole('button', { name: '4x' }))
    fireEvent.click(screen.getByRole('button', { name: /play/i }))
    expect(screen.getByText('1 / 4')).toBeInTheDocument()

    // Wait for auto-advance (base delay is 1500ms / 4 = 375ms for user turn at 4x speed)
    await waitFor(() => {
      expect(screen.getByText('2 / 4')).toBeInTheDocument()
    }, { timeout: 2000 })

    vi.useFakeTimers() // Restore fake timers
  })

  it('stops playback at end', async () => {
    vi.useRealTimers() // Use real timers for this test

    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Jump to near end (step 3)
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    expect(screen.getByText('4 / 4')).toBeInTheDocument()

    // Try to play - should reset since we're at end
    fireEvent.click(screen.getByRole('button', { name: /play/i }))

    // Should be playing from start
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
    }, { timeout: 1000 })

    vi.useFakeTimers() // Restore fake timers
  })

  it('displays tool calls in assistant turns', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Go to step 2 (assistant with tool calls)
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Should show tool calls section
    expect(screen.getByText(/tool calls/i)).toBeInTheDocument()
    expect(screen.getByText('write_file')).toBeInTheDocument()
  })

  it('expands tool call to show arguments and result', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Go to step 2 (assistant with tool calls)
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Click to expand tool call
    fireEvent.click(screen.getByText('write_file'))

    // Should show arguments
    expect(screen.getByText('Arguments:')).toBeInTheDocument()
    // Should find the file path in the arguments JSON
    expect(screen.getAllByText(/\/tmp\/hello\.py/).length).toBeGreaterThanOrEqual(1)

    // Should show result
    expect(screen.getByText('Result:')).toBeInTheDocument()
  })

  it('shows success badge for successful tool calls', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Go to step 2 (assistant with tool calls)
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Should show success badge
    expect(screen.getByText('Success')).toBeInTheDocument()
  })

  it('shows error badge for failed tool calls', () => {
    const turnsWithError: Turn[] = [
      {
        role: 'user',
        content: 'Read a file',
        timestamp: '2026-01-16T10:00:00',
      },
      {
        role: 'assistant',
        content: 'I will read the file.',
        timestamp: '2026-01-16T10:00:05',
        tool_calls: [
          {
            name: 'read_file',
            arguments: { path: '/nonexistent.txt' },
            result: 'Error: File not found',
          },
        ],
      },
    ]

    render(
      <SessionReplay
        turns={turnsWithError}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Go to step 2
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Should show error badge
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('shows relative time for each turn', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // First turn should show +0s
    expect(screen.getByText('+0s')).toBeInTheDocument()

    // Go to second turn
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Should show +5s (5 seconds after start)
    expect(screen.getByText('+5s')).toBeInTheDocument()
  })

  it('shows keyboard shortcuts hint', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Check for keyboard shortcuts hint section
    expect(screen.getByText(/play\/pause/i)).toBeInTheDocument()
    // Check that Space key is mentioned
    const spaceKeyElements = screen.getAllByText('Space')
    expect(spaceKeyElements.length).toBeGreaterThanOrEqual(1)
    // Check that Home/End keys are mentioned
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.getByText('End')).toBeInTheDocument()
  })

  it('responds to keyboard shortcuts', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Press right arrow to step forward
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByText('2 / 4')).toBeInTheDocument()

    // Press left arrow to step backward
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByText('1 / 4')).toBeInTheDocument()

    // Press End to jump to end
    fireEvent.keyDown(window, { key: 'End' })
    expect(screen.getByText('4 / 4')).toBeInTheDocument()

    // Press Home to jump to start
    fireEvent.keyDown(window, { key: 'Home' })
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
  })

  it('toggles play with space key', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Initially paused
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()

    // Press space to play
    fireEvent.keyDown(window, { key: ' ' })
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()

    // Press space to pause
    fireEvent.keyDown(window, { key: ' ' })
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
  })

  it('jumps to step when clicking timeline strip button', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Click on step 3 in timeline strip
    const step3Button = screen.getByTitle('Step 3: tool')
    fireEvent.click(step3Button)

    expect(screen.getByText('3 / 4')).toBeInTheDocument()
  })

  it('shows "more steps coming" indicator when not at end', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // At step 1, should show 3 more steps
    expect(screen.getByText('3 more step(s)...')).toBeInTheDocument()

    // Go to step 2
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    expect(screen.getByText('2 more step(s)...')).toBeInTheDocument()
  })

  it('hides "more steps" indicator at last step', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Jump to end
    fireEvent.click(screen.getByRole('button', { name: /jump to end/i }))

    // Should not show "more steps" indicator
    expect(screen.queryByText(/more step/)).not.toBeInTheDocument()
  })

  it('handles session without end time', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={null}
      />
    )

    // Should render without crashing
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
  })

  it('displays all previous turns up to current step', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // At step 1, only first turn visible
    expect(screen.getByText('Create a hello world file in Python')).toBeInTheDocument()
    expect(screen.queryByText(/I will create a hello world file/)).not.toBeInTheDocument()

    // Go to step 2
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Both turns should be visible
    expect(screen.getByText('Create a hello world file in Python')).toBeInTheDocument()
    expect(screen.getByText(/I will create a hello world file/)).toBeInTheDocument()
  })

  it('highlights current step turn', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // Current step badge should be visible
    expect(screen.getByText('Current')).toBeInTheDocument()

    // Go forward
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))

    // Current badge should still be present (on new step)
    expect(screen.getByText('Current')).toBeInTheDocument()
  })

  it('shows role icons for each turn', () => {
    render(
      <SessionReplay
        turns={mockTurns}
        sessionStart={sessionStart}
        sessionEnd={sessionEnd}
      />
    )

    // User role label
    expect(screen.getByText('User')).toBeInTheDocument()

    // Go to assistant turn
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    expect(screen.getByText('Assistant')).toBeInTheDocument()

    // Go to tool result turn
    fireEvent.click(screen.getByRole('button', { name: /step forward/i }))
    expect(screen.getByText('Tool Result')).toBeInTheDocument()
  })
})
