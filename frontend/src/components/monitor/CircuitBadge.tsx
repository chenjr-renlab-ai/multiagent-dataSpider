import { clsx } from 'clsx'
import type { Circuit, CircuitState } from '../../types'

interface CircuitBadgeProps {
  circuit: Circuit
  compact?: boolean
}

const stateConfig: Record<CircuitState, { label: string; classes: string; dot: string }> = {
  CLOSED: {
    label: 'CLOSED',
    classes: 'border-green-800 bg-green-950 text-green-300',
    dot: 'bg-green-400',
  },
  OPEN: {
    label: 'OPEN',
    classes: 'border-red-700 bg-red-950 text-red-300',
    dot: 'bg-red-500',
  },
  HALF_OPEN: {
    label: 'HALF',
    classes: 'border-yellow-700 bg-yellow-950 text-yellow-300',
    dot: 'bg-yellow-400 animate-pulse',
  },
}

export function CircuitBadge({ circuit, compact = false }: CircuitBadgeProps) {
  const cfg = stateConfig[circuit.state]

  if (compact) {
    return (
      <span
        title={`${circuit.domain}: ${circuit.state}${circuit.last_error ? ` — ${circuit.last_error}` : ''}`}
        className={clsx(
          'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-mono',
          cfg.classes
        )}
      >
        <span className={clsx('h-1.5 w-1.5 rounded-full', cfg.dot)} />
        {cfg.label}
      </span>
    )
  }

  return (
    <div className={clsx('rounded border px-2.5 py-1.5 flex flex-col gap-0.5', cfg.classes)}>
      <div className="flex items-center gap-1.5">
        <span className={clsx('h-2 w-2 rounded-full flex-shrink-0', cfg.dot)} />
        <span className="font-mono text-xs font-medium truncate max-w-[140px]">
          {circuit.domain}
        </span>
        <span className="text-xs opacity-70">{cfg.label}</span>
      </div>
      {circuit.failure_count > 0 && (
        <span className="text-xs opacity-60 ml-3.5">
          failures: {circuit.failure_count}
          {circuit.retry_after_sec !== undefined &&
            ` · retry in ${circuit.retry_after_sec}s`}
        </span>
      )}
      {circuit.last_error && (
        <span className="text-xs opacity-50 ml-3.5 truncate">{circuit.last_error}</span>
      )}
    </div>
  )
}
