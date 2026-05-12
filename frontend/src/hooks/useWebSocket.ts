import { useEffect, useRef, useCallback } from 'react'
import { getWsUrl } from '../api/client'
import { useAgentStore } from '../store/agentStore'
import { useMissionStore } from '../store/missionStore'
import type { WSMessage } from '../types'

const MAX_RETRIES = 5
const HEARTBEAT_TIMEOUT_MS = 15_000

export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'failed'

interface UseWebSocketOptions {
  onStatusChange?: (status: WsStatus) => void
}

export function useWebSocket(options?: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const statusRef = useRef<WsStatus>('disconnected')

  const { applySnapshot, updateAgent, updateStreams, updateCircuit } = useAgentStore.getState()
  const { setMissions, updateMissionFromEvent } = useMissionStore.getState()

  const onStatusChange = options?.onStatusChange

  const setStatus = useCallback(
    (s: WsStatus) => {
      statusRef.current = s
      onStatusChange?.(s)
    },
    [onStatusChange]
  )

  const resetHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)
    heartbeatTimerRef.current = setTimeout(() => {
      wsRef.current?.close()
    }, HEARTBEAT_TIMEOUT_MS)
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    setStatus('connecting')
    const url = getWsUrl()
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      retryCountRef.current = 0
      setStatus('connected')
      resetHeartbeat()
    }

    ws.onmessage = (event: MessageEvent) => {
      resetHeartbeat()
      let msg: WSMessage
      try {
        msg = JSON.parse(event.data as string) as WSMessage
      } catch {
        return
      }

      switch (msg.type) {
        case 'snapshot':
          applySnapshot(msg.data)
          setMissions(msg.data.missions)
          break
        case 'agent_update':
          updateAgent(msg.data)
          break
        case 'stream_update':
          updateStreams(msg.data.streams)
          break
        case 'circuit_update':
          updateCircuit(msg.data)
          break
        case 'mission_event': {
          const { mission_id, event } = msg.data
          updateMissionFromEvent(mission_id, event)
          if (event === 'started' || event === 'completed' || event === 'failed') {
            // Trigger a re-fetch if needed — handled by query invalidation elsewhere
          }
          break
        }
      }
    }

    ws.onclose = () => {
      setStatus('disconnected')
      if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)

      if (retryCountRef.current < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** retryCountRef.current, 30_000)
        retryCountRef.current++
        retryTimerRef.current = setTimeout(connect, delay)
      } else {
        setStatus('failed')
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [
    setStatus,
    resetHeartbeat,
    applySnapshot,
    setMissions,
    updateAgent,
    updateStreams,
    updateCircuit,
    updateMissionFromEvent,
  ])

  useEffect(() => {
    connect()
    return () => {
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
      if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}
