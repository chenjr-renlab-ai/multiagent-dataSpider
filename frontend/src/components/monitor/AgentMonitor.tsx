import { useRef } from 'react'
import { useAgentStore } from '../../store/agentStore'
import { TierGroup } from './TierGroup'
import { QueueDepthBar } from './QueueDepthBar'
import { CircuitBadge } from './CircuitBadge'
import { TopologySVG } from './TopologySVG'
import { Spinner } from '../ui/Spinner'

const TIER_IDS = [0, 1, 2, 3, 4]

export function AgentMonitor() {
  const agents = useAgentStore((s) => s.agents)
  const streams = useAgentStore((s) => s.streams)
  const circuits = useAgentStore((s) => s.circuits)

  const tierRefs = useRef<Record<number, HTMLDivElement | null>>({})

  const agentList = Array.from(agents.values())

  const handleTierClick = (tier: number) => {
    const el = tierRefs.current[tier]
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const tierGroups = TIER_IDS.map((tier) => ({
    tier,
    agents: agentList.filter((a) => a.tier === tier).sort((a, b) => a.agent_id.localeCompare(b.agent_id)),
  }))

  const openCircuits = circuits.filter((c) => c.state !== 'CLOSED')

  return (
    <div className="flex h-full overflow-hidden">
      {/* Main agent list */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-6">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
          Agent Monitor
        </h2>

        {agentList.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-zinc-600">
            <Spinner size="lg" />
            <span className="text-sm">等待 Agent 数据...</span>
          </div>
        )}

        {tierGroups.map(({ tier, agents: tierAgents }) => (
          <div
            key={tier}
            ref={(el) => {
              tierRefs.current[tier] = el
            }}
          >
            <TierGroup tier={tier} agents={tierAgents} id={`tier-${tier}`} />
          </div>
        ))}
      </div>

      {/* Right panel: Topology + Streams + Circuits */}
      <div className="w-64 flex-shrink-0 border-l border-zinc-800 flex flex-col overflow-y-auto">
        {/* Mini topology */}
        <div className="p-3 border-b border-zinc-800">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-2">
            Topology
          </h3>
          <div className="flex justify-center">
            <TopologySVG onTierClick={handleTierClick} />
          </div>
        </div>

        {/* Queue depths */}
        <div className="p-3 border-b border-zinc-800">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-2">
            Queue Streams
          </h3>
          {streams.length === 0 ? (
            <p className="text-xs text-zinc-600 py-2">暂无 stream 数据</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {streams.map((s) => (
                <QueueDepthBar key={s.name} stream={s} />
              ))}
            </div>
          )}
        </div>

        {/* Circuit breakers */}
        <div className="p-3">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-2">
            Circuit Breakers
            {openCircuits.length > 0 && (
              <span className="ml-1.5 text-red-400">({openCircuits.length} open)</span>
            )}
          </h3>
          {circuits.length === 0 ? (
            <p className="text-xs text-zinc-600 py-2">无熔断器记录</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {circuits.map((c) => (
                <CircuitBadge key={c.domain} circuit={c} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
