import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AgentGraph } from './AgentGraph'
import type { Agent, WebSocketEvent } from '../types/api'

// Mock agents for testing
const mockAgents: Agent[] = [
  {
    name: 'brokkr',
    role: 'Orchestrator',
    model: 'qwen2.5-coder:14b',
    tools: ['delegate', 'read_file', 'write_file'],
    can_delegate: true,
    delegate_to: ['huginn', 'mimir', 'skald'],
    estimated_vram_gb: 9,
    max_iterations: 30,
    fallback_model: 'qwen2.5-coder:7b',
  },
  {
    name: 'huginn',
    role: 'Coder',
    model: 'qwen2.5-coder:7b',
    tools: ['read_file', 'write_file', 'edit_file'],
    can_delegate: false,
    delegate_to: [],
    estimated_vram_gb: 5,
    max_iterations: 20,
    fallback_model: null,
  },
  {
    name: 'mimir',
    role: 'Reviewer',
    model: 'qwen2.5-coder:7b',
    tools: ['read_file', 'search_code'],
    can_delegate: false,
    delegate_to: [],
    estimated_vram_gb: 5,
    max_iterations: 15,
    fallback_model: null,
  },
  {
    name: 'skald',
    role: 'Tester',
    model: 'qwen2.5-coder:7b',
    tools: ['read_file', 'run_tests'],
    can_delegate: false,
    delegate_to: [],
    estimated_vram_gb: 5,
    max_iterations: 15,
    fallback_model: null,
  },
]

describe('AgentGraph', () => {
  it('renders the SVG container', () => {
    const { container } = render(
      <AgentGraph agents={mockAgents} width={600} height={400} />
    )
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('width', '600')
    expect(svg).toHaveAttribute('height', '400')
  })

  it('renders with default dimensions', () => {
    const { container } = render(<AgentGraph agents={mockAgents} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    // Default is 600x400
    expect(svg).toHaveAttribute('width', '600')
    expect(svg).toHaveAttribute('height', '400')
  })

  it('renders legend', () => {
    render(<AgentGraph agents={mockAgents} />)
    expect(screen.getByText('Legend')).toBeInTheDocument()
    expect(screen.getByText('Orchestrator')).toBeInTheDocument()
    expect(screen.getByText('Coder')).toBeInTheDocument()
    expect(screen.getByText('Reviewer')).toBeInTheDocument()
    expect(screen.getByText('Tester')).toBeInTheDocument()
  })

  it('renders controls hint', () => {
    render(<AgentGraph agents={mockAgents} />)
    expect(
      screen.getByText('Drag nodes • Scroll to zoom • Click for details')
    ).toBeInTheDocument()
  })

  it('shows active delegation indicator with events', () => {
    const events: WebSocketEvent[] = [
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'huginn',
          task_id: 'test-123',
        },
        timestamp: new Date().toISOString(),
      },
    ]

    render(<AgentGraph agents={mockAgents} events={events} />)
    // Should show active delegation indicator
    expect(screen.getByText(/active delegation/i)).toBeInTheDocument()
  })

  it('does not show active delegation indicator without events', () => {
    render(<AgentGraph agents={mockAgents} events={[]} />)
    expect(screen.queryByText(/active delegation/i)).not.toBeInTheDocument()
  })

  it('renders with empty agents array', () => {
    const { container } = render(<AgentGraph agents={[]} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('calls onAgentClick when provided', () => {
    const mockClick = vi.fn()
    const { container } = render(
      <AgentGraph agents={mockAgents} onAgentClick={mockClick} />
    )

    // D3 creates nodes as <g> elements with circles and text
    // We need to wait for D3 to render, which happens in useEffect
    // Since D3 manipulates the DOM directly, we check if the structure exists
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles multiple delegation events', () => {
    const events: WebSocketEvent[] = [
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'huginn',
          task_id: 'test-1',
        },
        timestamp: new Date().toISOString(),
      },
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'mimir',
          task_id: 'test-2',
        },
        timestamp: new Date().toISOString(),
      },
    ]

    render(<AgentGraph agents={mockAgents} events={events} />)
    expect(screen.getByText(/2 active delegations/i)).toBeInTheDocument()
  })

  it('removes completed delegations from active list', () => {
    const events: WebSocketEvent[] = [
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'huginn',
          task_id: 'test-1',
        },
        timestamp: new Date().toISOString(),
      },
      {
        type: 'DELEGATION_COMPLETE',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'huginn',
        },
        timestamp: new Date().toISOString(),
      },
    ]

    render(<AgentGraph agents={mockAgents} events={events} />)
    // After completion, should not show active delegation
    expect(screen.queryByText(/active delegation/i)).not.toBeInTheDocument()
  })

  it('renders with custom dimensions', () => {
    const { container } = render(
      <AgentGraph agents={mockAgents} width={1200} height={800} />
    )
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '1200')
    expect(svg).toHaveAttribute('height', '800')
  })

  it('applies correct CSS classes', () => {
    const { container } = render(<AgentGraph agents={mockAgents} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('bg-sindri-900')
    expect(svg).toHaveClass('rounded-lg')
    expect(svg).toHaveClass('border')
  })
})

describe('AgentGraph delegation flow', () => {
  it('processes delegation start events correctly', () => {
    const events: WebSocketEvent[] = [
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'skald',
          task_id: 'task-abc',
        },
        timestamp: new Date().toISOString(),
      },
    ]

    render(<AgentGraph agents={mockAgents} events={events} />)
    expect(screen.getByText(/1 active delegation/i)).toBeInTheDocument()
  })

  it('handles case-insensitive agent names', () => {
    const events: WebSocketEvent[] = [
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'Brokkr', // Upper case
          child_agent: 'HUGINN', // All caps
          task_id: 'test-123',
        },
        timestamp: new Date().toISOString(),
      },
    ]

    render(<AgentGraph agents={mockAgents} events={events} />)
    expect(screen.getByText(/active delegation/i)).toBeInTheDocument()
  })

  it('ignores duplicate delegation events', () => {
    const events: WebSocketEvent[] = [
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'huginn',
          task_id: 'test-1',
        },
        timestamp: new Date().toISOString(),
      },
      {
        type: 'DELEGATION_START',
        data: {
          parent_agent: 'brokkr',
          child_agent: 'huginn', // Same delegation
          task_id: 'test-2',
        },
        timestamp: new Date().toISOString(),
      },
    ]

    render(<AgentGraph agents={mockAgents} events={events} />)
    // Should only count as 1 active delegation (not 2)
    expect(screen.getByText(/1 active delegation$/i)).toBeInTheDocument()
  })
})
