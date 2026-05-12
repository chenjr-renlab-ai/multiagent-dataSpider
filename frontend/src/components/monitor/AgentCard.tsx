import { clsx } from 'clsx'
import { formatRelativeTime, truncateUrl, formatRate } from '../../utils/format'
import type { Agent, AgentStatus } from '../../types'

interface AgentCardProps {
  agent: Agent
}

const statusBorder: Record<AgentStatus, string> = {
  IDLE: 'border-zinc-700',
  PROCESSING: 'border-t-blue-500 border-zinc-700',
  FAILED: 'border-t-red-500 border-zinc-700',
  DEAD: 'border-zinc-700 opacity-50',
}

const statusDot: Record<AgentStatus, string> = {
  IDLE: 'bg-zinc-500',
  PROCESSING: 'bg-blue-400 animate-pulse',
  FAILED: 'bg-red-500',
  DEAD: 'bg-zinc-600',
}

const statusLabel: Record<AgentStatus, string> = {
  IDLE: 'IDLE',
  PROCESSING: 'PROCESSING',
  FAILED: 'FAILED',
  DEAD: 'DEAD',
}

const statusLabelClass: Record<AgentStatus, string> = {
  IDLE: 'text-zinc-500',
  PROCESSING: 'text-blue-300',
  FAILED: 'text-red-400',
  DEAD: 'text-zinc-600',
}

export function AgentCard({ agent }: AgentCardProps) {
  const isProcessing = agent.status === 'PROCESSING'
  const hasBorderTop =
    agent.status === 'PROCESSING' || agent.status === 'FAILED'

  return (
    <div
      className={clsx(
        'rounded bg-zinc-800 border flex flex-col gap-1.5 p-2.5 text-xs',
        hasBorderTop ? 'border-t-2' : '',
        statusBorder[agent.status]
      )}
    >
      {/* Top row: id + status */}
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          {isProcessing && (
            <svg
              className="h-3 w-3 animate-spin text-blue-400 flex-shrink-0"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          )}
          {!isProcessing && (
            <span className={clsx('h-1.5 w-1.5 flex-shrink-0 rounded-full', statusDot[agent.status])} />
          )}
          <span className="font-mono text-zinc-300 truncate">{agent.agent_id}</span>
        </div>
        <span className={clsx('flex-shrink-0 font-medium', statusLabelClass[agent.status])}>
          {statusLabel[agent.status]}
        </span>
      </div>

      {/* Current URL */}
      {agent.current_url && (
        <div className="text-zinc-500 font-mono truncate" title={agent.current_url}>
          {truncateUrl(agent.current_url, 38)}
        </div>
      )}

      {/* Progress bar */}
      {agent.job_progress !== undefined && agent.job_progress !== null && isProcessing && (
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1 rounded-full bg-zinc-700 overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-300"
              style={{ width: `${Math.min(agent.job_progress * 100, 100)}%` }}
            />
          </div>
          <span className="text-zinc-500 tabular-nums">
            {Math.round(agent.job_progress * 100)}%
          </span>
        </div>
      )}

      {/* Footer stats */}
      <div className="flex items-center justify-between text-zinc-600">
        <span title="Last heartbeat">{formatRelativeTime(agent.last_heartbeat)}</span>
        <div className="flex items-center gap-2">
          {agent.request_rate !== undefined && (
            <span className="text-zinc-500">{formatRate(agent.request_rate)}</span>
          )}
          {agent.error_count > 0 && (
            <span className="text-red-500 font-medium">err:{agent.error_count}</span>
          )}
        </div>
      </div>
    </div>
  )
}
