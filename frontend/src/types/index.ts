export type AgentStatus = 'IDLE' | 'PROCESSING' | 'FAILED' | 'DEAD'
export type MissionStatus = 'pending' | 'planning' | 'running' | 'completed' | 'failed' | 'cancelled'
export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN'

export interface Agent {
  agent_id: string
  tier: number
  agent_type: string
  status: AgentStatus
  current_url?: string
  current_job_id?: string
  job_progress?: number
  error_count: number
  last_heartbeat: number // unix timestamp seconds
  request_rate?: number
}

export interface StreamInfo {
  name: string
  depth: number
  capacity: number
}

export interface Circuit {
  domain: string
  state: CircuitState
  failure_count: number
  retry_after_sec?: number
  last_error?: string
}

export interface Mission {
  id: string
  name: string
  description?: string
  status: MissionStatus
  created_at: string
  completed_at?: string
  job_total: number
  job_done: number
  job_failed: number
  config: MissionConfig
}

export interface MissionConfig {
  targets: Target[]
  schedule: Schedule
}

export interface Target {
  url: string
  type: 'api' | 'html' | 'browser'
  method?: string
  headers?: Record<string, string>
  extract: ExtractConfig
}

export interface ExtractConfig {
  type: 'json_path' | 'css' | 'xpath'
  rules: Record<string, string>
}

export interface Schedule {
  type: 'once' | 'interval'
  interval_seconds?: number
}

// WebSocket messages
export type WSMessage =
  | { type: 'snapshot'; ts: number; data: SnapshotData }
  | { type: 'agent_update'; ts: number; data: Agent }
  | { type: 'stream_update'; ts: number; data: { streams: StreamInfo[] } }
  | { type: 'circuit_update'; ts: number; data: Circuit }
  | { type: 'mission_event'; ts: number; data: MissionEvent }

export interface SnapshotData {
  agents: Agent[]
  streams: StreamInfo[]
  circuits: Circuit[]
  missions: Mission[]
}

export interface MissionEvent {
  mission_id: string
  event: 'started' | 'completed' | 'failed' | 'job_done'
  detail?: Record<string, unknown>
}

// API types
export interface CreateMissionRequest {
  name: string
  description?: string
  config: MissionConfig
}

export interface ScrapedRecord {
  id: string
  mission_id: string
  url: string
  fields: Record<string, unknown>
  confidence?: number
  scraped_at: string
}

export interface PagedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
