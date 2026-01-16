/**
 * AgentGraph - Interactive D3.js visualization of agent hierarchy and delegation flow
 *
 * Features:
 * - Force-directed graph layout showing agent relationships
 * - Real-time animation of active delegations
 * - Click nodes to view agent details
 * - Color-coded by role with VRAM indicators
 */

import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { Agent, WebSocketEvent } from '../types/api'

interface AgentGraphProps {
  agents: Agent[]
  events?: WebSocketEvent[]
  onAgentClick?: (agent: Agent) => void
  width?: number
  height?: number
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string
  agent: Agent
  fx?: number | null
  fy?: number | null
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: GraphNode | string
  target: GraphNode | string
  active?: boolean
}

interface ActiveDelegation {
  from: string
  to: string
  taskId: string
  startTime: number
}

// Role colors matching the AgentCard component
const roleColors: Record<string, string> = {
  Orchestrator: '#a855f7', // purple-500
  Coder: '#3b82f6', // blue-500
  Reviewer: '#eab308', // yellow-500
  Tester: '#22c55e', // green-500
  'SQL Specialist': '#06b6d4', // cyan-500
  Planner: '#f97316', // orange-500
  Executor: '#ec4899', // pink-500
}

// Role emojis
const roleEmoji: Record<string, string> = {
  Orchestrator: '👑',
  Coder: '💻',
  Reviewer: '🔍',
  Tester: '🧪',
  'SQL Specialist': '🗃️',
  Planner: '📋',
  Executor: '⚡',
}

export function AgentGraph({
  agents,
  events = [],
  onAgentClick,
  width = 600,
  height = 400,
}: AgentGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [activeDelegations, setActiveDelegations] = useState<ActiveDelegation[]>([])
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphLink> | null>(null)

  // Track active delegations from WebSocket events
  useEffect(() => {
    const recentEvents = events.slice(-50) // Only consider last 50 events

    for (const event of recentEvents) {
      if (event.type === 'DELEGATION_START') {
        const data = event.data as { parent_agent?: string; child_agent?: string; task_id?: string }
        if (data.parent_agent && data.child_agent) {
          setActiveDelegations((prev) => {
            // Check if already exists
            if (prev.some((d) => d.from === data.parent_agent && d.to === data.child_agent)) {
              return prev
            }
            return [
              ...prev,
              {
                from: data.parent_agent!.toLowerCase(),
                to: data.child_agent!.toLowerCase(),
                taskId: data.task_id || '',
                startTime: Date.now(),
              },
            ]
          })
        }
      } else if (event.type === 'DELEGATION_COMPLETE') {
        const data = event.data as { parent_agent?: string; child_agent?: string }
        if (data.parent_agent && data.child_agent) {
          setActiveDelegations((prev) =>
            prev.filter(
              (d) =>
                !(
                  d.from === data.parent_agent!.toLowerCase() &&
                  d.to === data.child_agent!.toLowerCase()
                )
            )
          )
        }
      }
    }
  }, [events])

  // Clean up old delegations after 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now()
      setActiveDelegations((prev) =>
        prev.filter((d) => now - d.startTime < 30000)
      )
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  // Build and render the D3 graph
  useEffect(() => {
    if (!svgRef.current || agents.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Create nodes from agents
    const nodes: GraphNode[] = agents.map((agent) => ({
      id: agent.name.toLowerCase(),
      agent,
    }))

    // Create links from delegation relationships
    const nodeMap = new Map(nodes.map((n) => [n.id, n]))
    const links: GraphLink[] = []

    for (const agent of agents) {
      for (const target of agent.delegate_to) {
        const targetId = target.toLowerCase()
        if (nodeMap.has(targetId)) {
          links.push({
            source: agent.name.toLowerCase(),
            target: targetId,
            active: activeDelegations.some(
              (d) => d.from === agent.name.toLowerCase() && d.to === targetId
            ),
          })
        }
      }
    }

    // Set up the force simulation
    const simulation = d3
      .forceSimulation(nodes)
      .force(
        'link',
        d3
          .forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.id)
          .distance(100)
      )
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(45))

    simulationRef.current = simulation

    // Create container groups
    const g = svg.append('g')

    // Zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 2])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    svg.call(zoom)

    // Arrow marker for links
    svg
      .append('defs')
      .append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', '#4b5563')

    // Arrow marker for active links
    svg
      .select('defs')
      .append('marker')
      .attr('id', 'arrowhead-active')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', '#22c55e')

    // Create link elements
    const link = g
      .append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (d) => (d.active ? '#22c55e' : '#4b5563'))
      .attr('stroke-width', (d) => (d.active ? 3 : 2))
      .attr('stroke-opacity', (d) => (d.active ? 1 : 0.6))
      .attr('marker-end', (d) => (d.active ? 'url(#arrowhead-active)' : 'url(#arrowhead)'))

    // Create drag behavior
    const drag = d3
      .drag<SVGGElement, GraphNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })

    // Create node groups
    const node = g
      .append('g')
      .attr('class', 'nodes')
      .selectAll<SVGGElement, GraphNode>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(drag)

    // Node circles
    node
      .append('circle')
      .attr('r', 30)
      .attr('fill', (d) => {
        const color = roleColors[d.agent.role] || '#6b7280'
        return color
      })
      .attr('stroke', '#1f2937')
      .attr('stroke-width', 3)
      .attr('opacity', 0.9)

    // VRAM indicator ring
    node
      .append('circle')
      .attr('r', 35)
      .attr('fill', 'none')
      .attr('stroke', (d) => {
        const vram = d.agent.estimated_vram_gb
        if (vram > 8) return '#ef4444' // red for high VRAM
        if (vram > 5) return '#eab308' // yellow for medium
        return '#22c55e' // green for low
      })
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '5,5')
      .attr('opacity', 0.6)

    // Role emoji
    node
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', '20px')
      .text((d) => roleEmoji[d.agent.role] || '🤖')

    // Agent name label
    node
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('y', 50)
      .attr('fill', '#e5e7eb')
      .attr('font-size', '12px')
      .attr('font-weight', 'bold')
      .text((d) => d.agent.name)

    // VRAM label
    node
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('y', 65)
      .attr('fill', '#9ca3af')
      .attr('font-size', '10px')
      .text((d) => `${d.agent.estimated_vram_gb}GB`)

    // Click handler
    node.on('click', (_event, d) => {
      if (onAgentClick) {
        onAgentClick(d.agent)
      }
    })

    // Hover effects
    node
      .on('mouseenter', function () {
        d3.select(this).select('circle').attr('opacity', 1)
        d3.select(this).select('circle:first-child').attr('r', 35)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle').attr('opacity', 0.9)
        d3.select(this).select('circle:first-child').attr('r', 30)
      })

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as GraphNode).x ?? 0)
        .attr('y1', (d) => (d.source as GraphNode).y ?? 0)
        .attr('x2', (d) => (d.target as GraphNode).x ?? 0)
        .attr('y2', (d) => (d.target as GraphNode).y ?? 0)

      node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    // Cleanup
    return () => {
      simulation.stop()
    }
  }, [agents, activeDelegations, width, height, onAgentClick])

  // Update link styles when active delegations change
  useEffect(() => {
    if (!svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('.links line').each(function () {
      const line = d3.select(this)
      const sourceId = (line.datum() as GraphLink).source
      const targetId = (line.datum() as GraphLink).target

      const sourceNode = typeof sourceId === 'string' ? sourceId : (sourceId as GraphNode).id
      const targetNode = typeof targetId === 'string' ? targetId : (targetId as GraphNode).id

      const isActive = activeDelegations.some(
        (d) => d.from === sourceNode && d.to === targetNode
      )

      line
        .attr('stroke', isActive ? '#22c55e' : '#4b5563')
        .attr('stroke-width', isActive ? 3 : 2)
        .attr('stroke-opacity', isActive ? 1 : 0.6)
        .attr('marker-end', isActive ? 'url(#arrowhead-active)' : 'url(#arrowhead)')
    })
  }, [activeDelegations])

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        className="bg-sindri-900 rounded-lg border border-sindri-700"
      />

      {/* Legend */}
      <div className="absolute top-2 left-2 bg-sindri-800/90 rounded p-2 text-xs">
        <div className="text-sindri-300 font-semibold mb-1">Legend</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-purple-500" />
            <span className="text-sindri-400">Orchestrator</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-blue-500" />
            <span className="text-sindri-400">Coder</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-yellow-500" />
            <span className="text-sindri-400">Reviewer</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-green-500" />
            <span className="text-sindri-400">Tester</span>
          </div>
        </div>
        <div className="mt-2 pt-2 border-t border-sindri-700">
          <div className="flex items-center gap-2">
            <div className="w-6 h-0.5 bg-green-500" />
            <span className="text-sindri-400">Active</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-6 h-0.5 bg-gray-500" />
            <span className="text-sindri-400">Can delegate</span>
          </div>
        </div>
      </div>

      {/* Active delegations indicator */}
      {activeDelegations.length > 0 && (
        <div className="absolute top-2 right-2 bg-green-900/90 rounded px-2 py-1 text-xs text-green-300 flex items-center gap-2">
          <span className="animate-pulse">●</span>
          {activeDelegations.length} active delegation{activeDelegations.length !== 1 ? 's' : ''}
        </div>
      )}

      {/* Controls hint */}
      <div className="absolute bottom-2 right-2 text-xs text-sindri-500">
        Drag nodes • Scroll to zoom • Click for details
      </div>
    </div>
  )
}

export default AgentGraph
