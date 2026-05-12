/**
 * Unit tests for the Zustand agentStore.
 *
 * The store is imported directly (not through a hook) so we can call actions
 * and assert on the resulting state without rendering any component.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useAgentStore } from '@/store/agentStore'
import type { Agent, StreamInfo, Circuit } from '@/types/index'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const makeAgent = (overrides: Partial<Agent> = {}): Agent => ({
  agent_id: 'agent-1',
  tier: 1,
  status: 'IDLE',
  current_url: undefined,
  error_count: 0,
  last_heartbeat: Date.now(),
  ...overrides,
})

const makeStream = (overrides: Partial<StreamInfo> = {}): StreamInfo => ({
  name: 'frontier',
  depth: 100,
  capacity: 1000,
  ...overrides,
})

const makeCircuit = (overrides: Partial<Circuit> = {}): Circuit => ({
  domain: 'example.com',
  state: 'CLOSED',
  failure_count: 0,
  ...overrides,
})

// Reset the store before every test so tests are independent.
beforeEach(() => {
  useAgentStore.setState({
    agents: new Map(),
    streams: [],
    circuits: [],
  })
})

// ---------------------------------------------------------------------------
// applySnapshot
// ---------------------------------------------------------------------------

describe('agentStore.applySnapshot', () => {
  it('initialises the agents Map from snapshot data', () => {
    const agent1 = makeAgent({ agent_id: 'a1' })
    const agent2 = makeAgent({ agent_id: 'a2', status: 'PROCESSING' })

    useAgentStore.getState().applySnapshot({
      agents: [agent1, agent2],
      streams: [],
      circuits: [],
    })

    const { agents } = useAgentStore.getState()
    expect(agents.size).toBe(2)
    expect(agents.get('a1')).toEqual(agent1)
    expect(agents.get('a2')).toEqual(agent2)
  })

  it('initialises streams from snapshot data', () => {
    const stream = makeStream({ name: 'priority', depth: 50 })

    useAgentStore.getState().applySnapshot({
      agents: [],
      streams: [stream],
      circuits: [],
    })

    expect(useAgentStore.getState().streams).toEqual([stream])
  })

  it('initialises circuits from snapshot data', () => {
    const circuit = makeCircuit({ domain: 'test.com', state: 'OPEN' })

    useAgentStore.getState().applySnapshot({
      agents: [],
      streams: [],
      circuits: [circuit],
    })

    expect(useAgentStore.getState().circuits).toEqual([circuit])
  })

  it('replaces previously stored data when called a second time', () => {
    const first = makeAgent({ agent_id: 'old' })
    useAgentStore.getState().applySnapshot({ agents: [first], streams: [], circuits: [] })

    const second = makeAgent({ agent_id: 'new' })
    useAgentStore.getState().applySnapshot({ agents: [second], streams: [], circuits: [] })

    const { agents } = useAgentStore.getState()
    expect(agents.has('old')).toBe(false)
    expect(agents.has('new')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// updateAgent
// ---------------------------------------------------------------------------

describe('agentStore.updateAgent', () => {
  it('updates the status of an existing agent', () => {
    const agent = makeAgent({ agent_id: 'a1', status: 'IDLE' })
    useAgentStore.getState().applySnapshot({ agents: [agent], streams: [], circuits: [] })

    useAgentStore.getState().updateAgent({ ...agent, status: 'PROCESSING', current_url: 'https://example.com' })

    const updated = useAgentStore.getState().agents.get('a1')
    expect(updated?.status).toBe('PROCESSING')
    expect(updated?.current_url).toBe('https://example.com')
  })

  it('increments error_count on an existing agent', () => {
    const agent = makeAgent({ agent_id: 'a1', error_count: 2 })
    useAgentStore.getState().applySnapshot({ agents: [agent], streams: [], circuits: [] })

    useAgentStore.getState().updateAgent({ ...agent, error_count: 3, status: 'FAILED' })

    expect(useAgentStore.getState().agents.get('a1')?.error_count).toBe(3)
  })

  it('inserts a brand-new agent that does not yet exist in the Map', () => {
    const newAgent = makeAgent({ agent_id: 'brand-new', status: 'IDLE' })

    useAgentStore.getState().updateAgent(newAgent)

    const { agents } = useAgentStore.getState()
    expect(agents.has('brand-new')).toBe(true)
    expect(agents.get('brand-new')).toEqual(newAgent)
  })

  it('does not affect other agents when one is updated', () => {
    const a1 = makeAgent({ agent_id: 'a1' })
    const a2 = makeAgent({ agent_id: 'a2' })
    useAgentStore.getState().applySnapshot({ agents: [a1, a2], streams: [], circuits: [] })

    useAgentStore.getState().updateAgent({ ...a1, status: 'DEAD' })

    expect(useAgentStore.getState().agents.get('a2')).toEqual(a2)
  })
})

// ---------------------------------------------------------------------------
// updateStreams
// ---------------------------------------------------------------------------

describe('agentStore.updateStreams', () => {
  it('replaces the entire streams array', () => {
    useAgentStore.getState().applySnapshot({
      agents: [],
      streams: [makeStream({ name: 'old' })],
      circuits: [],
    })

    const newStreams: StreamInfo[] = [
      makeStream({ name: 'frontier', depth: 200 }),
      makeStream({ name: 'priority', depth: 50 }),
    ]

    useAgentStore.getState().updateStreams(newStreams)

    expect(useAgentStore.getState().streams).toEqual(newStreams)
  })

  it('replaces streams with an empty array', () => {
    useAgentStore.getState().applySnapshot({
      agents: [],
      streams: [makeStream()],
      circuits: [],
    })

    useAgentStore.getState().updateStreams([])

    expect(useAgentStore.getState().streams).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// updateCircuit
// ---------------------------------------------------------------------------

describe('agentStore.updateCircuit', () => {
  it('updates the state of an existing circuit by domain', () => {
    const circuit = makeCircuit({ domain: 'example.com', state: 'CLOSED' })
    useAgentStore.getState().applySnapshot({ agents: [], streams: [], circuits: [circuit] })

    useAgentStore.getState().updateCircuit({ domain: 'example.com', state: 'OPEN', failure_count: 5 })

    const updated = useAgentStore.getState().circuits.find((c) => c.domain === 'example.com')
    expect(updated?.state).toBe('OPEN')
    expect(updated?.failure_count).toBe(5)
  })

  it('adds a circuit that does not yet exist', () => {
    useAgentStore.getState().applySnapshot({ agents: [], streams: [], circuits: [] })

    useAgentStore.getState().updateCircuit({ domain: 'new.com', state: 'HALF_OPEN', failure_count: 2 })

    const { circuits } = useAgentStore.getState()
    expect(circuits).toHaveLength(1)
    expect(circuits[0].domain).toBe('new.com')
    expect(circuits[0].state).toBe('HALF_OPEN')
  })

  it('does not affect other circuits when one is updated', () => {
    const c1 = makeCircuit({ domain: 'a.com', state: 'CLOSED' })
    const c2 = makeCircuit({ domain: 'b.com', state: 'CLOSED' })
    useAgentStore.getState().applySnapshot({ agents: [], streams: [], circuits: [c1, c2] })

    useAgentStore.getState().updateCircuit({ domain: 'a.com', state: 'OPEN', failure_count: 10 })

    const b = useAgentStore.getState().circuits.find((c) => c.domain === 'b.com')
    expect(b?.state).toBe('CLOSED')
  })
})
