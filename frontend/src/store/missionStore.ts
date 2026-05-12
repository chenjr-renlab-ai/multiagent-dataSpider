import { create } from 'zustand'
import type { Mission } from '../types'

interface MissionStore {
  missions: Mission[]
  currentMissionId: string | null
  setMissions: (missions: Mission[]) => void
  upsertMission: (mission: Mission) => void
  setCurrentMission: (id: string | null) => void
  updateMissionFromEvent: (missionId: string, event: string) => void
}

export const useMissionStore = create<MissionStore>((set) => ({
  missions: [],
  currentMissionId: null,

  setMissions: (missions: Mission[]) => set({ missions }),

  upsertMission: (mission: Mission) =>
    set((state) => {
      const idx = state.missions.findIndex((m) => m.id === mission.id)
      if (idx === -1) {
        return { missions: [mission, ...state.missions] }
      }
      const next = [...state.missions]
      next[idx] = mission
      return { missions: next }
    }),

  setCurrentMission: (id: string | null) => set({ currentMissionId: id }),

  updateMissionFromEvent: (missionId: string, event: string) =>
    set((state) => {
      const idx = state.missions.findIndex((m) => m.id === missionId)
      if (idx === -1) return state
      const mission = { ...state.missions[idx] }
      if (event === 'started') {
        mission.status = 'running'
      } else if (event === 'completed') {
        mission.status = 'completed'
        mission.completed_at = new Date().toISOString()
      } else if (event === 'failed') {
        mission.status = 'failed'
      } else if (event === 'job_done') {
        mission.job_done = (mission.job_done || 0) + 1
      }
      const next = [...state.missions]
      next[idx] = mission
      return { missions: next }
    }),
}))
