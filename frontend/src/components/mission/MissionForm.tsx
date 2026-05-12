import { useState } from 'react'
import { clsx } from 'clsx'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { TargetEditor } from './TargetEditor'
import { MissionProgress } from './MissionProgress'
import { api } from '../../api/client'
import { useMissionStore } from '../../store/missionStore'
import type { Target, Schedule } from '../../types'

type ProgressPhase = 'planning' | 'launching' | 'running'

export function MissionForm() {
  const upsertMission = useMissionStore((s) => s.upsertMission)

  const [name, setName] = useState('')
  const [targets, setTargets] = useState<Target[]>([])
  const [scheduleType, setScheduleType] = useState<Schedule['type']>('once')
  const [intervalSec, setIntervalSec] = useState(300)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progressPhase, setProgressPhase] = useState<ProgressPhase | null>(null)

  const canSubmit = name.trim().length > 0 && targets.length > 0 && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setError(null)
    setSubmitting(true)
    setProgressPhase('planning')

    try {
      // Phase 1: planning
      await new Promise((r) => setTimeout(r, 600))
      setProgressPhase('launching')

      // Phase 2: API call
      const schedule: Schedule =
        scheduleType === 'interval'
          ? { type: 'interval', interval_seconds: intervalSec }
          : { type: 'once' }

      const mission = await api.createMission({
        name: name.trim(),
        config: { targets, schedule },
      })

      upsertMission(mission)
      setProgressPhase('running')

      await new Promise((r) => setTimeout(r, 800))

      // Reset form
      setName('')
      setTargets([])
      setScheduleType('once')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setSubmitting(false)
      setProgressPhase(null)
    }
  }

  return (
    <div className="p-4 flex flex-col gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">New Mission</h2>

      {progressPhase && <MissionProgress phase={progressPhase} />}

      {/* Name */}
      <Input
        label="任务名称"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="例：商品价格监控"
        disabled={submitting}
      />

      {/* Targets */}
      <TargetEditor targets={targets} onChange={setTargets} />

      {/* Schedule */}
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">调度</span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setScheduleType('once')}
            className={clsx(
              'flex-1 rounded border px-2 py-1.5 text-xs font-medium transition-colors',
              scheduleType === 'once'
                ? 'bg-blue-700 border-blue-600 text-white'
                : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700'
            )}
          >
            立即执行
          </button>
          <button
            type="button"
            onClick={() => setScheduleType('interval')}
            className={clsx(
              'flex-1 rounded border px-2 py-1.5 text-xs font-medium transition-colors',
              scheduleType === 'interval'
                ? 'bg-blue-700 border-blue-600 text-white'
                : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700'
            )}
          >
            定时循环
          </button>
        </div>
        {scheduleType === 'interval' && (
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-zinc-500">每</span>
            <input
              type="number"
              min={10}
              value={intervalSec}
              onChange={(e) => setIntervalSec(Number(e.target.value))}
              className="w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <span className="text-xs text-zinc-500">秒</span>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded border border-red-700 bg-red-950 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Submit */}
      <Button
        variant="primary"
        size="md"
        loading={submitting}
        disabled={!canSubmit}
        onClick={handleSubmit}
        className="w-full justify-center mt-1"
      >
        ▶ 启动任务
      </Button>
    </div>
  )
}
