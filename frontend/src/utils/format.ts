/** Format unix timestamp seconds to relative string like "2s ago" */
export function formatRelativeTime(unixSec: number): string {
  const diffMs = Date.now() - unixSec * 1000
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 0) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  return `${Math.floor(diffHour / 24)}d ago`
}

/** Format bytes to human-readable string */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/** Format requests per second */
export function formatRate(rps?: number): string {
  if (rps === undefined || rps === null) return '—'
  if (rps < 1) return `${(rps * 60).toFixed(1)} rpm`
  return `${rps.toFixed(1)} req/s`
}

/** Format duration in seconds to h:mm:ss */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Format ISO date string to locale */
export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/** Truncate URL for display */
export function truncateUrl(url: string, maxLen = 40): string {
  if (url.length <= maxLen) return url
  return `${url.slice(0, maxLen - 3)}...`
}
