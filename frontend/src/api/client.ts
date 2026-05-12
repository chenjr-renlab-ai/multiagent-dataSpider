import type { Mission, CreateMissionRequest, ScrapedRecord, PagedResponse } from '../types'

const BASE = import.meta.env.DEV ? 'http://localhost:8080' : ''

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  createMission: (data: CreateMissionRequest): Promise<Mission> =>
    request<Mission>('/api/missions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getMissions: (): Promise<Mission[]> =>
    request<Mission[]>('/api/missions'),

  getMission: (id: string): Promise<Mission> =>
    request<Mission>(`/api/missions/${id}`),

  cancelMission: (id: string): Promise<{ ok: boolean }> =>
    request<{ ok: boolean }>(`/api/missions/${id}/cancel`, { method: 'POST' }),

  getData: (missionId: string, page = 1, pageSize = 20): Promise<PagedResponse<ScrapedRecord>> =>
    request<PagedResponse<ScrapedRecord>>(
      `/api/missions/${missionId}/data?page=${page}&page_size=${pageSize}`
    ),
}

export function getWsUrl(): string {
  if (import.meta.env.DEV) {
    return 'ws://localhost:8080/ws/console'
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/ws/console`
}
