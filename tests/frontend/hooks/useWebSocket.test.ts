/**
 * Tests for useWebSocket hook.
 *
 * Strategy:
 * - The global WebSocket is replaced by a controllable fake in setup.ts.
 * - The agentStore is mocked so we can spy on its action methods.
 * - We render a minimal wrapper component to exercise the hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from '@/hooks/useWebSocket'

// ---------------------------------------------------------------------------
// Mock the agentStore actions
// ---------------------------------------------------------------------------

const mockApplySnapshot = vi.fn()
const mockUpdateAgent = vi.fn()
const mockUpdateStreams = vi.fn()
const mockUpdateCircuit = vi.fn()

vi.mock('@/store/agentStore', () => ({
  useAgentStore: (selector?: (s: unknown) => unknown) => {
    const state = {
      applySnapshot: mockApplySnapshot,
      updateAgent: mockUpdateAgent,
      updateStreams: mockUpdateStreams,
      updateCircuit: mockUpdateCircuit,
    }
    return selector ? selector(state) : state
  },
}))

// ---------------------------------------------------------------------------
// Helpers – give tests direct access to the latest MockWebSocket instance
// ---------------------------------------------------------------------------

let latestSocket: InstanceType<typeof WebSocket> & {
  triggerMessage: (data: unknown) => void
  triggerClose: () => void
}

// Wrap the global mock to capture the instance and expose helper methods.
const OriginalMockWS = global.WebSocket
class SpyWebSocket extends OriginalMockWS {
  constructor(url: string) {
    super(url)
    // Expose helpers so tests can simulate incoming messages / disconnects.
    ;(this as unknown as { triggerMessage: (d: unknown) => void }).triggerMessage = (data: unknown) => {
      this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
    }
    ;(this as unknown as { triggerClose: () => void }).triggerClose = () => {
      this.onclose?.()
    }
    latestSocket = this as typeof latestSocket
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  global.WebSocket = SpyWebSocket as unknown as typeof WebSocket
  mockApplySnapshot.mockClear()
  mockUpdateAgent.mockClear()
  mockUpdateStreams.mockClear()
  mockUpdateCircuit.mockClear()
})

afterEach(() => {
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useWebSocket', () => {
  it('calls store.applySnapshot when the "snapshot" message is received', async () => {
    renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    // Let the constructor's setTimeout fire so onopen is called.
    await act(async () => {
      vi.runAllTimers()
    })

    const snapshotData = {
      type: 'snapshot',
      agents: [],
      streams: [],
      circuits: [],
    }

    act(() => {
      latestSocket.triggerMessage(snapshotData)
    })

    expect(mockApplySnapshot).toHaveBeenCalledOnce()
    expect(mockApplySnapshot).toHaveBeenCalledWith(
      expect.objectContaining({ agents: [], streams: [], circuits: [] }),
    )
  })

  it('calls store.updateAgent when an "agent_update" message is received', async () => {
    renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    await act(async () => {
      vi.runAllTimers()
    })

    const agentPayload = {
      type: 'agent_update',
      agent: {
        agent_id: 'a1',
        tier: 1,
        status: 'PROCESSING',
        current_url: 'https://example.com',
        error_count: 0,
        last_heartbeat: Date.now(),
      },
    }

    act(() => {
      latestSocket.triggerMessage(agentPayload)
    })

    expect(mockUpdateAgent).toHaveBeenCalledOnce()
    expect(mockUpdateAgent).toHaveBeenCalledWith(
      expect.objectContaining({ agent_id: 'a1', status: 'PROCESSING' }),
    )
  })

  it('calls store.updateStreams when a "stream_update" message is received', async () => {
    renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    await act(async () => {
      vi.runAllTimers()
    })

    const streamPayload = {
      type: 'stream_update',
      streams: [{ name: 'frontier', depth: 300, capacity: 1000 }],
    }

    act(() => {
      latestSocket.triggerMessage(streamPayload)
    })

    expect(mockUpdateStreams).toHaveBeenCalledOnce()
    expect(mockUpdateStreams).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ name: 'frontier', depth: 300 })]),
    )
  })

  it('calls store.updateCircuit when a "circuit_update" message is received', async () => {
    renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    await act(async () => {
      vi.runAllTimers()
    })

    const circuitPayload = {
      type: 'circuit_update',
      circuit: { domain: 'example.com', state: 'OPEN', failure_count: 3 },
    }

    act(() => {
      latestSocket.triggerMessage(circuitPayload)
    })

    expect(mockUpdateCircuit).toHaveBeenCalledOnce()
    expect(mockUpdateCircuit).toHaveBeenCalledWith(
      expect.objectContaining({ domain: 'example.com', state: 'OPEN' }),
    )
  })

  it('schedules a reconnect via setTimeout after the WebSocket closes', async () => {
    const setTimeoutSpy = vi.spyOn(global, 'setTimeout')

    renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    // Let onopen fire.
    await act(async () => {
      vi.runAllTimers()
    })

    const callsBefore = setTimeoutSpy.mock.calls.length

    act(() => {
      latestSocket.triggerClose()
    })

    // At least one new setTimeout call should have been made for reconnection.
    expect(setTimeoutSpy.mock.calls.length).toBeGreaterThan(callsBefore)
  })
})
