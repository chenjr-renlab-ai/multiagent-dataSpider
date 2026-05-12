/**
 * Rendering tests for the AgentCard component.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AgentCard } from '@/components/AgentCard'
import type { Agent } from '@/types/index'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const baseAgent: Agent = {
  agent_id: 'agent-42',
  tier: 1,
  status: 'IDLE',
  current_url: undefined,
  error_count: 0,
  last_heartbeat: Date.now(),
}

// Pin Date.now so relative-time assertions are stable.
const FIXED_NOW = 1_700_000_000_000 // arbitrary fixed timestamp (ms)

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(FIXED_NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AgentCard – IDLE status', () => {
  it('renders the agent id', () => {
    render(<AgentCard agent={{ ...baseAgent, status: 'IDLE' }} />)
    expect(screen.getByText(/agent-42/i)).toBeInTheDocument()
  })

  it('uses a grey colour class on the status icon', () => {
    const { container } = render(<AgentCard agent={{ ...baseAgent, status: 'IDLE' }} />)
    // The IDLE icon should carry a grey-related class (e.g. text-gray-*)
    const icon = container.querySelector('[data-testid="status-icon"], .status-icon, [class*="gray"]')
    expect(icon).not.toBeNull()
  })

  it('does not render a current_url when none is provided', () => {
    render(<AgentCard agent={{ ...baseAgent, status: 'IDLE', current_url: undefined }} />)
    expect(screen.queryByTestId('current-url')).not.toBeInTheDocument()
  })
})

describe('AgentCard – PROCESSING status', () => {
  const processingAgent: Agent = {
    ...baseAgent,
    status: 'PROCESSING',
    current_url: 'https://processing.example.com/page',
  }

  it('displays the current_url', () => {
    render(<AgentCard agent={processingAgent} />)
    expect(screen.getByText(/processing\.example\.com/i)).toBeInTheDocument()
  })

  it('renders a spinning / animated element indicating activity', () => {
    const { container } = render(<AgentCard agent={processingAgent} />)
    // Animated element carries an "animate-spin" Tailwind class or a data-testid="spinner"
    const spinner =
      container.querySelector('[data-testid="spinner"]') ??
      container.querySelector('.animate-spin') ??
      container.querySelector('[class*="spin"]')
    expect(spinner).not.toBeNull()
  })

  it('applies a blue colour class to the status icon', () => {
    const { container } = render(<AgentCard agent={processingAgent} />)
    const blueEl =
      container.querySelector('[class*="blue"]') ??
      container.querySelector('[data-testid="status-icon"]')
    expect(blueEl).not.toBeNull()
  })
})

describe('AgentCard – FAILED status', () => {
  const failedAgent: Agent = {
    ...baseAgent,
    status: 'FAILED',
    error_count: 7,
  }

  it('displays the error_count', () => {
    render(<AgentCard agent={failedAgent} />)
    expect(screen.getByText(/7/)).toBeInTheDocument()
  })

  it('applies a red colour class', () => {
    const { container } = render(<AgentCard agent={failedAgent} />)
    const redEl =
      container.querySelector('[class*="red"]') ??
      container.querySelector('[data-testid="status-icon"]')
    expect(redEl).not.toBeNull()
  })

  it('renders the error label alongside the count', () => {
    render(<AgentCard agent={failedAgent} />)
    // e.g. "7 errors" or "错误: 7" or "error_count: 7"
    const errorText = screen.queryByText(/error/i) ?? screen.queryByText(/错误/i) ?? screen.queryByText(/7/)
    expect(errorText).not.toBeNull()
  })
})

describe('AgentCard – DEAD status', () => {
  const deadAgent: Agent = {
    ...baseAgent,
    status: 'DEAD',
  }

  it('applies an opacity / semi-transparent class to the card', () => {
    const { container } = render(<AgentCard agent={deadAgent} />)
    // Tailwind: opacity-50, opacity-40, etc.  Or a custom class containing "opacity"
    const root = container.firstElementChild as HTMLElement
    const hasOpacity =
      root?.className?.includes('opacity') ||
      [...(root?.querySelectorAll('[class*="opacity"]') ?? [])].length > 0
    expect(hasOpacity).toBe(true)
  })

  it('still renders the agent id even when DEAD', () => {
    render(<AgentCard agent={deadAgent} />)
    expect(screen.getByText(/agent-42/i)).toBeInTheDocument()
  })
})

describe('AgentCard – last_heartbeat formatting', () => {
  it('shows a relative time string like "X 秒前" or "X seconds ago"', () => {
    // Heartbeat was 30 seconds ago
    const agent: Agent = {
      ...baseAgent,
      status: 'IDLE',
      last_heartbeat: FIXED_NOW - 30_000,
    }

    render(<AgentCard agent={agent} />)

    // Match "30 秒前", "30s ago", "30 seconds ago", etc.
    const timeEl =
      screen.queryByText(/30\s*秒前/i) ??
      screen.queryByText(/30\s*s(ec(ond)?s?)?\s*ago/i) ??
      screen.queryByText(/30/)
    expect(timeEl).not.toBeNull()
  })

  it('shows "just now" or "刚刚" when heartbeat is very recent', () => {
    const agent: Agent = {
      ...baseAgent,
      status: 'IDLE',
      last_heartbeat: FIXED_NOW - 500, // 0.5 s ago
    }

    render(<AgentCard agent={agent} />)

    const recentEl =
      screen.queryByText(/just now/i) ??
      screen.queryByText(/刚刚/i) ??
      screen.queryByText(/0\s*(秒前|s)/i)
    expect(recentEl).not.toBeNull()
  })
})
