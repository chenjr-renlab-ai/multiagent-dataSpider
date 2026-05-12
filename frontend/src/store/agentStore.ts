import { create } from 'zustand'
import type { Agent, StreamInfo, Circuit, SnapshotData } from '../types'

interface AgentStore {
  agents: Map<string, Agent>
  streams: StreamInfo[]
  circuits: Circuit[]
  applySnapshot: (data: SnapshotData) => void
  updateAgent: (agent: Agent) => void
  updateStreams: (streams: StreamInfo[]) => void
  updateCircuit: (circuit: Circuit) => void
}

export const useAgentStore = create<AgentStore>((set) => ({
  agents: new Map(),
  streams: [],
  circuits: [],

  applySnapshot: (data: SnapshotData) =>
    set(() => {
      const agentMap = new Map<string, Agent>()
      for (const a of data.agents) {
        agentMap.set(a.agent_id, a)
      }
      return {
        agents: agentMap,
        streams: data.streams,
        circuits: data.circuits,
      }
    }),

  updateAgent: (agent: Agent) =>
    set((state) => {
      const next = new Map(state.agents)
      next.set(agent.agent_id, agent)
      return { agents: next }
    }),

  updateStreams: (streams: StreamInfo[]) =>
    set(() => ({ streams })),

  updateCircuit: (circuit: Circuit) =>
    set((state) => {
      const idx = state.circuits.findIndex((c) => c.domain === circuit.domain)
      if (idx === -1) {
        return { circuits: [...state.circuits, circuit] }
      }
      const next = [...state.circuits]
      next[idx] = circuit
      return { circuits: next }
    }),
}))
