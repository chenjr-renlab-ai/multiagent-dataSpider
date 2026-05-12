import { clsx } from 'clsx'

type Phase = 'planning' | 'launching' | 'running'

interface MissionProgressProps {
  phase: Phase
}

const phases: { key: Phase; label: string }[] = [
  { key: 'planning', label: '规划' },
  { key: 'launching', label: '启动' },
  { key: 'running', label: '运行' },
]

const phaseIndex: Record<Phase, number> = {
  planning: 0,
  launching: 1,
  running: 2,
}

export function MissionProgress({ phase }: MissionProgressProps) {
  const current = phaseIndex[phase]

  return (
    <div className="rounded border border-zinc-700 bg-zinc-900 p-3">
      <p className="text-xs text-zinc-400 mb-2.5">正在启动任务...</p>
      <div className="flex items-center gap-0">
        {phases.map((p, idx) => {
          const done = idx < current
          const active = idx === current
          const last = idx === phases.length - 1

          return (
            <div key={p.key} className="flex items-center flex-1">
              {/* Step circle */}
              <div className="flex flex-col items-center flex-shrink-0">
                <div
                  className={clsx(
                    'h-5 w-5 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all',
                    done
                      ? 'bg-green-600 border-green-500 text-white'
                      : active
                      ? 'border-blue-500 bg-blue-900 text-blue-300 animate-pulse'
                      : 'border-zinc-600 bg-zinc-800 text-zinc-500'
                  )}
                >
                  {done ? '✓' : idx + 1}
                </div>
                <span
                  className={clsx(
                    'mt-1 text-xs whitespace-nowrap',
                    done ? 'text-green-400' : active ? 'text-blue-300' : 'text-zinc-600'
                  )}
                >
                  {p.label}
                </span>
              </div>

              {/* Connector line */}
              {!last && (
                <div
                  className={clsx(
                    'flex-1 h-0.5 mx-1 rounded transition-colors',
                    done ? 'bg-green-600' : 'bg-zinc-700'
                  )}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
