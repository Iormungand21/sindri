/**
 * AgentList - Display all available agents with their capabilities
 * Now includes interactive D3.js graph visualization with real-time delegation flow
 */

import { useState } from 'react'
import { useAgents } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'
import { AgentGraph } from './AgentGraph'
import type { Agent } from '../types/api'

export function AgentList() {
  const { data: agents, isLoading, error } = useAgents()
  const { events, isConnected } = useWebSocket()
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [viewMode, setViewMode] = useState<'graph' | 'cards' | 'tree'>('graph')

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-sindri-100">Agents</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="card p-4 animate-pulse">
              <div className="h-6 bg-sindri-700 rounded w-1/3 mb-3" />
              <div className="h-4 bg-sindri-700 rounded w-2/3 mb-2" />
              <div className="h-4 bg-sindri-700 rounded w-1/2" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-red-400">Failed to load agents</p>
        <p className="text-sm text-sindri-500 mt-1">
          Make sure the backend is running
        </p>
      </div>
    )
  }

  const handleAgentClick = (agent: Agent) => {
    setSelectedAgent(agent)
  }

  const closeModal = () => {
    setSelectedAgent(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-sindri-100">Agents</h1>
          <p className="text-sindri-400 text-sm mt-1">
            {agents?.length ?? 0} agents available for orchestration
            {isConnected && (
              <span className="ml-2 text-green-400">● Connected</span>
            )}
          </p>
        </div>

        {/* View Mode Toggle */}
        <div className="flex gap-1 bg-sindri-800 rounded-lg p-1">
          <button
            onClick={() => setViewMode('graph')}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              viewMode === 'graph'
                ? 'bg-forge-500 text-white'
                : 'text-sindri-400 hover:text-sindri-200'
            }`}
          >
            Graph
          </button>
          <button
            onClick={() => setViewMode('tree')}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              viewMode === 'tree'
                ? 'bg-forge-500 text-white'
                : 'text-sindri-400 hover:text-sindri-200'
            }`}
          >
            Tree
          </button>
          <button
            onClick={() => setViewMode('cards')}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              viewMode === 'cards'
                ? 'bg-forge-500 text-white'
                : 'text-sindri-400 hover:text-sindri-200'
            }`}
          >
            Cards
          </button>
        </div>
      </div>

      {/* Interactive Agent Graph */}
      {viewMode === 'graph' && (
        <div className="card p-4">
          <h2 className="text-lg font-semibold text-sindri-100 mb-4">
            Agent Collaboration Graph
          </h2>
          <p className="text-sindri-400 text-sm mb-4">
            Interactive visualization of agent hierarchy and delegation flow.
            Click on an agent to view details.
          </p>
          <AgentGraph
            agents={agents ?? []}
            events={events}
            onAgentClick={handleAgentClick}
            width={800}
            height={500}
          />
        </div>
      )}

      {/* Tree View */}
      {viewMode === 'tree' && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-sindri-100 mb-4">
            Agent Hierarchy
          </h2>
          <AgentHierarchy agents={agents ?? []} onAgentClick={handleAgentClick} />
        </div>
      )}

      {/* Agent Cards */}
      {viewMode === 'cards' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents?.map((agent) => (
            <AgentCard
              key={agent.name}
              agent={agent}
              onClick={() => handleAgentClick(agent)}
            />
          ))}
        </div>
      )}

      {/* Agent Detail Modal */}
      {selectedAgent && (
        <AgentDetailModal agent={selectedAgent} onClose={closeModal} />
      )}
    </div>
  )
}

interface AgentCardProps {
  agent: Agent
  onClick?: () => void
}

function AgentCard({ agent, onClick }: AgentCardProps) {
  const roleColors: Record<string, string> = {
    Orchestrator: 'text-purple-400',
    Coder: 'text-blue-400',
    Reviewer: 'text-yellow-400',
    Tester: 'text-green-400',
    'SQL Specialist': 'text-cyan-400',
    Planner: 'text-orange-400',
    Executor: 'text-pink-400',
  }

  const roleColor = roleColors[agent.role] || 'text-sindri-300'

  return (
    <div
      className="card p-4 hover:border-sindri-500 transition-colors cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-sindri-100 capitalize">
            {agent.name}
          </h3>
          <p className={`text-sm ${roleColor}`}>{agent.role}</p>
        </div>
        {agent.can_delegate && (
          <span className="px-2 py-0.5 text-xs rounded bg-purple-900/50 text-purple-300 border border-purple-700">
            Delegator
          </span>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {/* Model */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-sindri-500">Model:</span>
          <code className="text-sindri-200 bg-sindri-800 px-1.5 py-0.5 rounded text-xs">
            {agent.model}
          </code>
        </div>

        {/* VRAM */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-sindri-500">VRAM:</span>
          <span className="text-sindri-200">{agent.estimated_vram_gb} GB</span>
        </div>

        {/* Max Iterations */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-sindri-500">Max Iterations:</span>
          <span className="text-sindri-200">{agent.max_iterations}</span>
        </div>

        {/* Delegates to */}
        {agent.delegate_to.length > 0 && (
          <div className="text-sm">
            <span className="text-sindri-500">Delegates to:</span>
            <div className="flex flex-wrap gap-1 mt-1">
              {agent.delegate_to.map((name) => (
                <span
                  key={name}
                  className="px-1.5 py-0.5 text-xs rounded bg-sindri-700 text-sindri-300"
                >
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Tools (truncated) */}
        <div className="text-sm">
          <span className="text-sindri-500">
            Tools ({agent.tools.length}):
          </span>
          <div className="flex flex-wrap gap-1 mt-1 max-h-12 overflow-hidden">
            {agent.tools.slice(0, 5).map((tool) => (
              <span
                key={tool}
                className="px-1.5 py-0.5 text-xs rounded bg-sindri-800 text-sindri-400"
              >
                {tool}
              </span>
            ))}
            {agent.tools.length > 5 && (
              <span className="px-1.5 py-0.5 text-xs rounded bg-sindri-800 text-sindri-400">
                +{agent.tools.length - 5} more
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Fallback info */}
      {agent.fallback_model && (
        <div className="mt-3 pt-3 border-t border-sindri-700 text-xs text-sindri-500">
          Fallback: {agent.fallback_model}
        </div>
      )}
    </div>
  )
}

interface AgentHierarchyProps {
  agents: Agent[]
  onAgentClick?: (agent: Agent) => void
}

function AgentHierarchy({ agents, onAgentClick }: AgentHierarchyProps) {
  // Find the root agent (one with most delegates)
  const agentMap = new Map(agents.map((a) => [a.name.toLowerCase(), a]))
  const rootAgent = agents.find(
    (a) => a.name.toLowerCase() === 'brokkr' || a.delegate_to.length > 2
  )

  if (!rootAgent) {
    return <p className="text-sindri-500">No hierarchy data available</p>
  }

  return (
    <div className="font-mono text-sm text-sindri-300 overflow-x-auto">
      <HierarchyNode
        agent={rootAgent}
        agentMap={agentMap}
        level={0}
        onAgentClick={onAgentClick}
      />
    </div>
  )
}

interface HierarchyNodeProps {
  agent: Agent
  agentMap: Map<string, Agent>
  level: number
  isLast?: boolean
  onAgentClick?: (agent: Agent) => void
}

function HierarchyNode({
  agent,
  agentMap,
  level,
  isLast = true,
  onAgentClick,
}: HierarchyNodeProps) {
  const indent = level > 0 ? '│   '.repeat(level - 1) + (isLast ? '└── ' : '├── ') : ''
  const children = agent.delegate_to
    .map((name) => agentMap.get(name.toLowerCase()))
    .filter((a): a is Agent => a !== undefined)

  const roleEmoji: Record<string, string> = {
    Orchestrator: '👑',
    Coder: '💻',
    Reviewer: '🔍',
    Tester: '🧪',
    'SQL Specialist': '🗃️',
    Planner: '📋',
    Executor: '⚡',
  }

  return (
    <div>
      <div
        className="flex items-center gap-2 py-0.5 hover:bg-sindri-800 rounded px-1 cursor-pointer"
        onClick={() => onAgentClick?.(agent)}
      >
        <span className="text-sindri-600">{indent}</span>
        <span>{roleEmoji[agent.role] || '🤖'}</span>
        <span className="text-sindri-100 font-medium capitalize">
          {agent.name}
        </span>
        <span className="text-sindri-500">({agent.role})</span>
      </div>
      {children.map((child, i) => (
        <HierarchyNode
          key={child.name}
          agent={child}
          agentMap={agentMap}
          level={level + 1}
          isLast={i === children.length - 1}
          onAgentClick={onAgentClick}
        />
      ))}
    </div>
  )
}

interface AgentDetailModalProps {
  agent: Agent
  onClose: () => void
}

function AgentDetailModal({ agent, onClose }: AgentDetailModalProps) {
  const roleColors: Record<string, string> = {
    Orchestrator: 'bg-purple-500',
    Coder: 'bg-blue-500',
    Reviewer: 'bg-yellow-500',
    Tester: 'bg-green-500',
    'SQL Specialist': 'bg-cyan-500',
    Planner: 'bg-orange-500',
    Executor: 'bg-pink-500',
  }

  const roleEmoji: Record<string, string> = {
    Orchestrator: '👑',
    Coder: '💻',
    Reviewer: '🔍',
    Tester: '🧪',
    'SQL Specialist': '🗃️',
    Planner: '📋',
    Executor: '⚡',
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-sindri-800 rounded-lg border border-sindri-700 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-sindri-700">
          <div className="flex items-center gap-4">
            <div
              className={`w-16 h-16 rounded-full ${
                roleColors[agent.role] || 'bg-sindri-600'
              } flex items-center justify-center text-3xl`}
            >
              {roleEmoji[agent.role] || '🤖'}
            </div>
            <div>
              <h2 className="text-2xl font-bold text-sindri-100 capitalize">
                {agent.name}
              </h2>
              <p className="text-sindri-400">{agent.role}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-sindri-400 hover:text-sindri-200 text-2xl"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Stats Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-sindri-900 rounded-lg p-4">
              <div className="text-sindri-500 text-sm">Model</div>
              <code className="text-sindri-100 text-sm">{agent.model}</code>
            </div>
            <div className="bg-sindri-900 rounded-lg p-4">
              <div className="text-sindri-500 text-sm">VRAM Required</div>
              <div className="text-sindri-100 text-lg font-semibold">
                {agent.estimated_vram_gb} GB
              </div>
            </div>
            <div className="bg-sindri-900 rounded-lg p-4">
              <div className="text-sindri-500 text-sm">Max Iterations</div>
              <div className="text-sindri-100 text-lg font-semibold">
                {agent.max_iterations}
              </div>
            </div>
          </div>

          {/* Delegation */}
          {agent.can_delegate && (
            <div>
              <h3 className="text-lg font-semibold text-sindri-100 mb-3">
                Delegation
              </h3>
              <div className="bg-sindri-900 rounded-lg p-4">
                <p className="text-sindri-400 text-sm mb-2">
                  This agent can delegate tasks to:
                </p>
                <div className="flex flex-wrap gap-2">
                  {agent.delegate_to.map((name) => (
                    <span
                      key={name}
                      className="px-3 py-1 rounded-full bg-purple-900/50 text-purple-300 border border-purple-700"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Fallback Model */}
          {agent.fallback_model && (
            <div>
              <h3 className="text-lg font-semibold text-sindri-100 mb-3">
                Fallback Model
              </h3>
              <div className="bg-sindri-900 rounded-lg p-4">
                <p className="text-sindri-400 text-sm mb-2">
                  When VRAM is insufficient, this agent falls back to:
                </p>
                <code className="text-forge-400 bg-sindri-800 px-3 py-1 rounded">
                  {agent.fallback_model}
                </code>
              </div>
            </div>
          )}

          {/* Tools */}
          <div>
            <h3 className="text-lg font-semibold text-sindri-100 mb-3">
              Available Tools ({agent.tools.length})
            </h3>
            <div className="bg-sindri-900 rounded-lg p-4 max-h-48 overflow-y-auto scrollbar-thin">
              <div className="flex flex-wrap gap-2">
                {agent.tools.map((tool) => (
                  <span
                    key={tool}
                    className="px-2 py-1 text-xs rounded bg-sindri-700 text-sindri-300 font-mono"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-sindri-700">
          <button onClick={onClose} className="btn btn-secondary w-full">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
