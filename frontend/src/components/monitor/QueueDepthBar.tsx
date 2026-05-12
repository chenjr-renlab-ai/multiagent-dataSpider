import { clsx } from 'clsx'
import type { StreamInfo } from '../../types'

interface QueueDepthBarProps {
  stream: StreamInfo
}

export function QueueDepthBar({ stream }: QueueDepthBarProps) {
  const pct = stream.capacity > 0 ? (stream.depth / stream.capacity) * 100 : 0
  const clamped = Math.min(pct, 100)

  const barClass =
    pct > 80
      ? 'bg-red-500'
      : pct > 50
      ? 'bg-yellow-500'
      : 'bg-green-500'

  const textClass =
    pct > 80 ? 'text-red-400' : pct > 50 ? 'text-yellow-400' : 'text-green-400'

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-zinc-400 truncate max-w-[120px]" title={stream.name}>
          {stream.name}
        </span>
        <div className="flex items-center gap-1">
          {pct > 80 && <span className="text-yellow-400 text-xs">⚠</span>}
          <span className={clsx('text-xs font-mono', textClass)}>
            {stream.depth.toLocaleString()} / {stream.capacity.toLocaleString()}
          </span>
        </div>
      </div>
      <div className="h-1.5 w-full rounded-full bg-zinc-700 overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all duration-300', barClass)}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}
