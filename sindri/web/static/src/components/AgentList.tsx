/**
 * AgentList - Display all available agents with their capabilities
 */

import { useAgents } from '../hooks/useApi'
import type { Agent } from '../types/api'

export function AgentList() {
  const { data: agents, isLoading, error } = useAgents()

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-sindri-100">Agents</h1>
        <p className="text-sindri-400 text-sm mt-1">
          {agents?.length ?? 0} agents available for orchestration
        </p>
      </div>

      {/* Agent Hierarchy Diagram */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-sindri-100 mb-4">
          Agent Hierarchy
        </h2>
        <AgentHierarchy agents={agents ?? []} />
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents?.map((agent) => (
          <AgentCard key={agent.name} agent={agent} />
        ))}
      </div>
    </div>
  )
}

interface AgentCardProps {
  agent: Agent
}

function AgentCard({ agent }: AgentCardProps) {
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
    <div className="card p-4 hover:border-sindri-500 transition-colors">
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

        {/* Tools */}
        <div className="text-sm">
          <span className="text-sindri-500">
            Tools ({agent.tools.length}):
          </span>
          <div className="flex flex-wrap gap-1 mt-1 max-h-24 overflow-y-auto scrollbar-thin">
            {agent.tools.map((tool) => (
              <span
                key={tool}
                className="px-1.5 py-0.5 text-xs rounded bg-sindri-800 text-sindri-400"
              >
                {tool}
              </span>
            ))}
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
}

function AgentHierarchy({ agents }: AgentHierarchyProps) {
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
      <HierarchyNode agent={rootAgent} agentMap={agentMap} level={0} />
    </div>
  )
}

interface HierarchyNodeProps {
  agent: Agent
  agentMap: Map<string, Agent>
  level: number
  isLast?: boolean
}

function HierarchyNode({
  agent,
  agentMap,
  level,
  isLast = true,
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
      <div className="flex items-center gap-2 py-0.5">
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
        />
      ))}
    </div>
  )
}
