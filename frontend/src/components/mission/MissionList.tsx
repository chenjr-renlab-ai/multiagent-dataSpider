import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { api } from '../../api/client'
import { useMissionStore } from '../../store/missionStore'
import { formatDateTime } from '../../utils/format'
import { Spinner } from '../ui/Spinner'
import type { Mission, MissionStatus } from '../../types'

const statusConfig: Record<
  MissionStatus,
  { label: string; dotClass: string; badgeClass: string }
> = {
  pending: {
    label: 'pending',
    dotClass: 'bg-zinc-400',
    badgeClass: 'text-zinc-400',
  },
  planning: {
    label: 'planning',
    dotClass: 'bg-yellow-400 animate-pulse',
    badgeClass: 'text-yellow-300',
  },
  running: {
    label: 'running',
    dotClass: 'bg-blue-400 animate-pulse',
    badgeClass: 'text-blue-300',
  },
  completed: {
    label: 'completed',
    dotClass: 'bg-green-400',
    badgeClass: 'text-green-300',
  },
  failed: {
    label: 'failed',
    dotClass: 'bg-red-500',
    badgeClass: 'text-red-400',
  },
  cancelled: {
    label: 'cancelled',
    dotClass: 'bg-zinc-600',
    badgeClass: 'text-zinc-500',
  },
}

function MissionItem({
  mission,
  selected,
  onSelect,
}: {
  mission: Mission
  selected: boolean
  onSelect: () => void
}) {
  const cfg = statusConfig[mission.status]
  const progress =
    mission.job_total > 0 ? Math.round((mission.job_done / mission.job_total) * 100) : 0

  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        'w-full text-left rounded-md border px-3 py-2.5 transition-colors flex flex-col gap-1',
        selected
          ? 'border-blue-600 bg-blue-950'
          : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700 hover:bg-zinc-800'
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={clsx('h-2 w-2 flex-shrink-0 rounded-full', cfg.dotClass)} />
          <span className="truncate text-sm font-medium text-white">{mission.name}</span>
        </div>
        <span className={clsx('text-xs flex-shrink-0 font-medium', cfg.badgeClass)}>
          {cfg.label}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span>{formatDateTime(mission.created_at)}</span>
        {mission.job_total > 0 && (
          <span>
            {mission.job_done}/{mission.job_total} 条
          </span>
        )}
      </div>

      {mission.status === 'running' && mission.job_total > 0 && (
        <div className="h-1 w-full rounded-full bg-zinc-700 overflow-hidden">
          <div
            className="h-full rounded-full bg-blue-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </button>
  )
}

export function MissionList() {
  const storeMissions = useMissionStore((s) => s.missions)
  const currentMissionId = useMissionStore((s) => s.currentMissionId)
  const setCurrentMission = useMissionStore((s) => s.setCurrentMission)
  const setMissions = useMissionStore((s) => s.setMissions)

  const { isLoading, isError, error } = useQuery({
    queryKey: ['missions'],
    queryFn: async () => {
      const data = await api.getMissions()
      setMissions(data)
      return data
    },
    refetchInterval: 10_000,
    staleTime: 5_000,
  })

  const missions = storeMissions

  return (
    <div className="flex flex-col gap-2 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">历史任务</h3>

      {isLoading && missions.length === 0 && (
        <div className="flex justify-center py-6">
          <Spinner size="md" />
        </div>
      )}

      {isError && (
        <div className="rounded border border-red-800 bg-red-950 px-3 py-2 text-xs text-red-400">
          加载失败: {error instanceof Error ? error.message : '未知错误'}
        </div>
      )}

      {!isLoading && missions.length === 0 && (
        <div className="py-8 text-center text-xs text-zinc-600">
          暂无任务，创建第一个任务开始爬取
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        {missions.map((m: Mission) => (
          <MissionItem
            key={m.id}
            mission={m}
            selected={currentMissionId === m.id}
            onSelect={() => setCurrentMission(m.id)}
          />
        ))}
      </div>
    </div>
  )
}
