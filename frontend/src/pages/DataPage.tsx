import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { api } from '../api/client'
import { useMissionStore } from '../store/missionStore'
import { formatDateTime } from '../utils/format'
import { Spinner } from '../components/ui/Spinner'
import { Button } from '../components/ui/Button'
import type { ScrapedRecord, Mission } from '../types'

function JsonCell({ value }: { value: unknown }) {
  const [expanded, setExpanded] = useState(false)
  const str = JSON.stringify(value, null, 2)
  const short = str.length > 60 ? str.slice(0, 60) + '…' : str
  const isExpandable = str.length > 60

  if (!isExpandable) {
    return <span className="font-mono text-xs text-zinc-300">{str}</span>
  }

  return (
    <div>
      {expanded ? (
        <pre className="font-mono text-xs text-zinc-300 whitespace-pre-wrap break-all max-h-40 overflow-y-auto rounded bg-zinc-900 p-1.5">
          {str}
        </pre>
      ) : (
        <span className="font-mono text-xs text-zinc-400">{short}</span>
      )}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="text-xs text-blue-400 hover:text-blue-300 ml-1.5"
      >
        {expanded ? '折叠' : '展开'}
      </button>
    </div>
  )
}

function DataTable({
  missionId,
}: {
  missionId: string
}) {
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 20

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['mission-data', missionId, page],
    queryFn: () => api.getData(missionId, page, PAGE_SIZE),
    placeholderData: (prev) => prev,
  })

  if (isLoading && !data) {
    return (
      <div className="flex justify-center items-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded border border-red-800 bg-red-950 px-4 py-3 text-sm text-red-400">
        加载失败: {error instanceof Error ? error.message : '未知错误'}
      </div>
    )
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-zinc-600">
        <svg
          className="h-12 w-12 mb-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
        </svg>
        <p className="text-sm">暂无已采集数据</p>
      </div>
    )
  }

  const totalPages = Math.ceil(data.total / PAGE_SIZE)

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-zinc-500">
        共 {data.total.toLocaleString()} 条记录，第 {page} / {totalPages} 页
      </div>

      <div className="overflow-x-auto rounded border border-zinc-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900">
              <th className="px-3 py-2 text-left font-semibold text-zinc-400 uppercase tracking-wide w-64">
                URL
              </th>
              <th className="px-3 py-2 text-left font-semibold text-zinc-400 uppercase tracking-wide">
                字段摘要
              </th>
              <th className="px-3 py-2 text-left font-semibold text-zinc-400 uppercase tracking-wide w-20">
                置信度
              </th>
              <th className="px-3 py-2 text-left font-semibold text-zinc-400 uppercase tracking-wide w-36">
                采集时间
              </th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((record: ScrapedRecord, idx: number) => (
              <tr
                key={record.id}
                className={clsx(
                  'border-b border-zinc-800 hover:bg-zinc-800 transition-colors',
                  idx % 2 === 0 ? 'bg-zinc-950' : 'bg-zinc-900'
                )}
              >
                <td className="px-3 py-2 font-mono text-zinc-400 max-w-xs">
                  <a
                    href={record.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncate block hover:text-blue-400 transition-colors"
                    title={record.url}
                  >
                    {record.url.length > 50 ? record.url.slice(0, 50) + '…' : record.url}
                  </a>
                </td>
                <td className="px-3 py-2 max-w-sm">
                  <JsonCell value={record.fields} />
                </td>
                <td className="px-3 py-2 text-center">
                  {record.confidence !== undefined ? (
                    <span
                      className={clsx(
                        'font-mono font-medium',
                        record.confidence >= 0.8
                          ? 'text-green-400'
                          : record.confidence >= 0.5
                          ? 'text-yellow-400'
                          : 'text-red-400'
                      )}
                    >
                      {(record.confidence * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <span className="text-zinc-600">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-zinc-500 whitespace-nowrap">
                  {formatDateTime(record.scraped_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
        >
          上一页
        </Button>
        <span className="text-xs text-zinc-500 px-2">
          {page} / {totalPages}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}

export function DataPage() {
  const missions = useMissionStore((s) => s.missions)
  const currentMissionId = useMissionStore((s) => s.currentMissionId)
  const setCurrentMission = useMissionStore((s) => s.setCurrentMission)

  const selectedMission = missions.find((m) => m.id === currentMissionId) ?? null

  return (
    <div className="flex h-screen flex-col bg-zinc-950 overflow-hidden">
      {/* Page header */}
      <div className="flex h-12 items-center border-b border-zinc-800 px-4 gap-3">
        <svg
          className="h-4 w-4 text-zinc-500"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
        </svg>
        <h1 className="text-sm font-semibold text-white">数据浏览</h1>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Mission list */}
        <aside className="w-64 flex-shrink-0 border-r border-zinc-800 overflow-y-auto p-3 flex flex-col gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">选择任务</h2>
          {missions.length === 0 ? (
            <p className="text-xs text-zinc-600 py-4 text-center">暂无任务</p>
          ) : (
            missions.map((m: Mission) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setCurrentMission(m.id)}
                className={clsx(
                  'w-full text-left rounded border px-3 py-2 text-xs transition-colors',
                  currentMissionId === m.id
                    ? 'border-blue-600 bg-blue-950 text-white'
                    : 'border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-800'
                )}
              >
                <div className="font-medium text-sm truncate">{m.name}</div>
                <div className="mt-0.5 text-zinc-500">{m.status} · {m.job_done} 条</div>
              </button>
            ))
          )}
        </aside>

        {/* Right: Data table */}
        <main className="flex-1 overflow-y-auto p-4">
          {!selectedMission ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
              <svg
                className="h-14 w-14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
              >
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p className="text-sm">请在左侧选择一个任务查看采集数据</p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">{selectedMission.name}</h2>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {selectedMission.status} · {selectedMission.job_done} 条已采集 ·{' '}
                  {selectedMission.job_failed} 条失败
                </p>
              </div>
              <DataTable missionId={selectedMission.id} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
