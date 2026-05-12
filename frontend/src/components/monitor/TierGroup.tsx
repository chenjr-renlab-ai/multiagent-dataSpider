import { useState } from 'react'
import { clsx } from 'clsx'
import { AgentCard } from './AgentCard'
import type { Agent } from '../../types'

const TIER_LABELS: Record<number, string> = {
  0: 'T0 · 规划层',
  1: 'T1 · 协调层',
  2: 'T2 · 采集层',
  3: 'T3 · 处理层',
  4: 'T4 · 验证/存储',
}

interface TierGroupProps {
  tier: number
  agents: Agent[]
  id?: string
}

export function TierGroup({ tier, agents, id }: TierGroupProps) {
  const [collapsed, setCollapsed] = useState(false)

  const processingCount = agents.filter((a) => a.status === 'PROCESSING').length
  const failedCount = agents.filter((a) => a.status === 'FAILED' || a.status === 'DEAD').length

  const label = TIER_LABELS[tier] ?? `T${tier}`

  return (
    <div id={id} className="flex flex-col gap-2">
      {/* Tier header */}
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center gap-2 text-left group"
      >
        <svg
          className={clsx(
            'h-3 w-3 text-zinc-500 transition-transform flex-shrink-0',
            collapsed ? '-rotate-90' : ''
          )}
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M6 8L1 3h10L6 8z" />
        </svg>
        <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">{label}</span>
        <span className="text-xs text-zinc-600">({agents.length})</span>
        {processingCount > 0 && (
          <span className="text-xs text-blue-400 font-medium">{processingCount} active</span>
        )}
        {failedCount > 0 && (
          <span className="text-xs text-red-400 font-medium">{failedCount} failed</span>
        )}
        <div className="flex-1 h-px bg-zinc-800" />
      </button>

      {/* Agent cards grid */}
      {!collapsed && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {agents.length === 0 ? (
            <div className="col-span-full py-3 text-center text-xs text-zinc-600">
              无 Agent 分配到此层
            </div>
          ) : (
            agents.map((agent) => <AgentCard key={agent.agent_id} agent={agent} />)
          )}
        </div>
      )}
    </div>
  )
}
