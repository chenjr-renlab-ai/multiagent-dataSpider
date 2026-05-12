import { useState } from 'react'
import { clsx } from 'clsx'
import { Button } from '../ui/Button'
import type { Target, ExtractConfig } from '../../types'

interface TargetEditorProps {
  targets: Target[]
  onChange: (targets: Target[]) => void
}

const DEFAULT_TARGET: Target = {
  url: '',
  type: 'html',
  extract: { type: 'css', rules: {} },
}

function RuleEditor({
  rules,
  onChange,
}: {
  rules: Record<string, string>
  onChange: (r: Record<string, string>) => void
}) {
  const entries = Object.entries(rules)
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')

  const addRule = () => {
    if (!newKey.trim()) return
    onChange({ ...rules, [newKey.trim()]: newVal.trim() })
    setNewKey('')
    setNewVal('')
  }

  const removeRule = (k: string) => {
    const next = { ...rules }
    delete next[k]
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-zinc-500 uppercase tracking-wide">提取规则</span>
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center gap-1">
          <span className="flex-1 truncate rounded bg-zinc-900 px-2 py-1 text-xs text-zinc-300 font-mono">
            {k} = {v}
          </span>
          <button
            type="button"
            onClick={() => removeRule(k)}
            className="text-zinc-600 hover:text-red-400 text-xs px-1"
            aria-label="Remove rule"
          >
            ×
          </button>
        </div>
      ))}
      <div className="flex gap-1 mt-0.5">
        <input
          type="text"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder="字段名"
          className="w-24 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-white placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <input
          type="text"
          value={newVal}
          onChange={(e) => setNewVal(e.target.value)}
          placeholder="$.path 或 .css"
          onKeyDown={(e) => e.key === 'Enter' && addRule()}
          className="flex-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-white placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          type="button"
          onClick={addRule}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
        >
          +
        </button>
      </div>
    </div>
  )
}

const typeLabels: Record<Target['type'], string> = {
  api: 'API',
  html: 'HTML',
  browser: '浏览器',
}

const extractTypeLabels: Record<ExtractConfig['type'], string> = {
  json_path: 'JSONPath',
  css: 'CSS',
  xpath: 'XPath',
}

export function TargetEditor({ targets, onChange }: TargetEditorProps) {
  const addTarget = () => onChange([...targets, { ...DEFAULT_TARGET }])

  const updateTarget = (idx: number, patch: Partial<Target>) => {
    const next = [...targets]
    next[idx] = { ...next[idx], ...patch }
    onChange(next)
  }

  const removeTarget = (idx: number) => {
    onChange(targets.filter((_, i) => i !== idx))
  }

  return (
    <div className="flex flex-col gap-2">
      {targets.map((target, idx) => (
        <div key={idx} className="rounded border border-zinc-700 bg-zinc-900 p-3 flex flex-col gap-2.5">
          {/* Header */}
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-400">目标 #{idx + 1}</span>
            <button
              type="button"
              onClick={() => removeTarget(idx)}
              className="text-xs text-zinc-600 hover:text-red-400"
              aria-label="Remove target"
            >
              移除
            </button>
          </div>

          {/* URL */}
          <input
            type="url"
            value={target.url}
            onChange={(e) => updateTarget(idx, { url: e.target.value })}
            placeholder="https://example.com/api/data"
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-white placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />

          {/* Type toggles */}
          <div className="flex gap-1">
            {(['api', 'html', 'browser'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => updateTarget(idx, { type: t })}
                className={clsx(
                  'flex-1 rounded px-2 py-1 text-xs font-medium border transition-colors',
                  target.type === t
                    ? 'bg-blue-700 border-blue-600 text-white'
                    : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700'
                )}
              >
                {typeLabels[t]}
              </button>
            ))}
          </div>

          {/* Extract type */}
          <div className="flex gap-1 items-center">
            <span className="text-xs text-zinc-500 w-12">解析:</span>
            <div className="flex gap-1">
              {(['json_path', 'css', 'xpath'] as const).map((et) => (
                <button
                  key={et}
                  type="button"
                  onClick={() =>
                    updateTarget(idx, {
                      extract: { ...target.extract, type: et },
                    })
                  }
                  className={clsx(
                    'rounded px-2 py-0.5 text-xs border transition-colors',
                    target.extract.type === et
                      ? 'bg-zinc-600 border-zinc-500 text-white'
                      : 'bg-zinc-800 border-zinc-700 text-zinc-500 hover:bg-zinc-700'
                  )}
                >
                  {extractTypeLabels[et]}
                </button>
              ))}
            </div>
          </div>

          {/* Rules */}
          <RuleEditor
            rules={target.extract.rules}
            onChange={(rules) =>
              updateTarget(idx, { extract: { ...target.extract, rules } })
            }
          />
        </div>
      ))}

      <Button type="button" variant="ghost" size="sm" onClick={addTarget} className="justify-center">
        + 添加抓取目标
      </Button>
    </div>
  )
}
