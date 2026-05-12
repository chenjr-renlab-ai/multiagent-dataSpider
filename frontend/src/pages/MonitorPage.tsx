import { useState } from 'react'
import { Sidebar } from '../components/layout/Sidebar'
import { Header } from '../components/layout/Header'
import { AgentMonitor } from '../components/monitor/AgentMonitor'
import { useWebSocket } from '../hooks/useWebSocket'
import type { WsStatus } from '../hooks/useWebSocket'

const PAGE_LOAD_TIME = Date.now()

export function MonitorPage() {
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting')

  useWebSocket({ onStatusChange: setWsStatus })

  return (
    <div className="flex h-screen flex-col bg-zinc-950 overflow-hidden">
      <Header wsStatus={wsStatus} startTime={PAGE_LOAD_TIME} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <AgentMonitor />
        </main>
      </div>
    </div>
  )
}
