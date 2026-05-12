import { useAgentStore } from '../../store/agentStore'

const TIER_LABELS = ['规划', '协调', '采集', '处理', '验证']
const TIER_COUNT = 5

interface TopologySVGProps {
  onTierClick?: (tier: number) => void
}

function getTierColor(failRatio: number): string {
  if (failRatio === 0) return '#22c55e' // green-500
  if (failRatio < 0.3) return '#eab308' // yellow-500
  return '#ef4444' // red-500
}

function getTierFill(failRatio: number): string {
  if (failRatio === 0) return '#14532d' // green-950
  if (failRatio < 0.3) return '#422006' // yellow-950
  return '#450a0a' // red-950
}

export function TopologySVG({ onTierClick }: TopologySVGProps) {
  const agents = useAgentStore((s) => s.agents)
  const agentList = Array.from(agents.values())

  const WIDTH = 100
  const HEIGHT = 260
  const CX = WIDTH / 2
  const R = 18
  const STEP = (HEIGHT - R * 2 - 20) / (TIER_COUNT - 1)

  const tiers = Array.from({ length: TIER_COUNT }, (_, i) => {
    const tierAgents = agentList.filter((a) => a.tier === i)
    const failCount = tierAgents.filter(
      (a) => a.status === 'FAILED' || a.status === 'DEAD'
    ).length
    const ratio = tierAgents.length > 0 ? failCount / tierAgents.length : 0
    const cy = R + 10 + i * STEP
    return { tier: i, cy, ratio, count: tierAgents.length }
  })

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width={WIDTH}
      height={HEIGHT}
      aria-label="Agent topology diagram"
    >
      {/* Connecting lines */}
      {tiers.slice(0, -1).map((t, i) => (
        <line
          key={`line-${i}`}
          x1={CX}
          y1={t.cy + R}
          x2={CX}
          y2={tiers[i + 1].cy - R}
          stroke="#3f3f46"
          strokeWidth="1.5"
          strokeDasharray="3 2"
        />
      ))}

      {/* Tier nodes */}
      {tiers.map((t) => (
        <g
          key={t.tier}
          onClick={() => onTierClick?.(t.tier)}
          style={{ cursor: onTierClick ? 'pointer' : 'default' }}
        >
          {/* Outer ring */}
          <circle
            cx={CX}
            cy={t.cy}
            r={R + 2}
            fill="none"
            stroke={getTierColor(t.ratio)}
            strokeWidth="1"
            opacity="0.4"
          />
          {/* Fill circle */}
          <circle cx={CX} cy={t.cy} r={R} fill={getTierFill(t.ratio)} />
          {/* Border */}
          <circle
            cx={CX}
            cy={t.cy}
            r={R}
            fill="none"
            stroke={getTierColor(t.ratio)}
            strokeWidth="1.5"
          />
          {/* Tier label */}
          <text
            x={CX}
            y={t.cy - 4}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="8"
            fill="#a1a1aa"
            fontFamily="monospace"
          >
            T{t.tier}
          </text>
          {/* Chinese label */}
          <text
            x={CX}
            y={t.cy + 5}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="7"
            fill={getTierColor(t.ratio)}
          >
            {TIER_LABELS[t.tier]}
          </text>
          {/* Count badge */}
          {t.count > 0 && (
            <>
              <circle cx={CX + R - 4} cy={t.cy - R + 4} r={7} fill="#18181b" stroke="#3f3f46" strokeWidth="0.5" />
              <text
                x={CX + R - 4}
                y={t.cy - R + 4}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="6"
                fill="#a1a1aa"
                fontFamily="monospace"
              >
                {t.count}
              </text>
            </>
          )}
        </g>
      ))}
    </svg>
  )
}
