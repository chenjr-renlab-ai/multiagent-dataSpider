import { useState, useEffect } from 'react'
import { useAgentStore } from '../../store/agentStore'
import { formatDuration } from '../../utils/format'
import type { WsStatus } from '../../hooks/useWebSocket'

interface HeaderProps {
  wsStatus: WsStatus
  startTime: number
}

export function Header({ wsStatus, startTime }: HeaderProps) {
  const agents = useAgentStore((s) => s.agents)
  const [uptime, setUptime] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setUptime(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [startTime])

  const agentList = Array.from(agents.values())
  const processingCount = agentList.filter((a) => a.status === 'PROCESSING').length
  const failedCount = agentList.filter((a) => a.status === 'FAILED' || a.status === 'DEAD').length
  const systemOk = wsStatus === 'connected' && failedCount === 0

  return (
    <header className="flex h-12 items-center justify-between border-b border-zinc-800 bg-zinc-950 px-4">
      {/* Left: Logo + Title */}
      <div className="flex items-center gap-2.5">
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          className="text-blue-400"
          aria-hidden="true"
        >
          <path
            d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"
            fill="currentColor"
            opacity="0.3"
          />
          <circle cx="12" cy="12" r="3" fill="currentColor" />
          <path
            d="M12 2v3M12 19v3M2 12h3M19 12h3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        <span className="text-base font-bold tracking-tight text-white">DataSpider</span>
        <span className="text-xs text-zinc-500 uppercase tracking-widest ml-1">Console</span>
      </div>

      {/* Right: Status indicators */}
      <div className="flex items-center gap-6 text-sm">
        {/* System status */}
        <div className="flex items-center gap-1.5">
          {wsStatus === 'connecting' ? (
            <>
              <span className="h-2 w-2 rounded-full bg-yellow-400 animate-pulse" />
              <span className="text-yellow-400 text-xs font-medium">CONNECTING</span>
            </>
          ) : wsStatus === 'failed' ? (
            <>
              <span className="h-2 w-2 rounded-full bg-red-500" />
              <span className="text-red-400 text-xs font-medium">DISCONNECTED</span>
            </>
          ) : systemOk ? (
            <>
              <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-green-400 text-xs font-medium">RUNNING</span>
            </>
          ) : (
            <>
              <span className="h-2 w-2 rounded-full bg-red-500" />
              <span className="text-red-400 text-xs font-medium">ERROR</span>
            </>
          )}
        </div>

        {/* Agent counts */}
        <div className="flex items-center gap-1 text-zinc-400">
          <span className="text-zinc-500 text-xs">Agents:</span>
          <span className="text-white font-medium">{agentList.length}</span>
          {processingCount > 0 && (
            <span className="text-blue-400 text-xs ml-1">({processingCount} active)</span>
          )}
        </div>

        {/* Uptime */}
        <div className="flex items-center gap-1 text-zinc-400">
          <span className="text-zinc-500 text-xs">Up:</span>
          <span className="font-mono text-xs text-zinc-300">{formatDuration(uptime)}</span>
        </div>
      </div>
    </header>
  )
}
