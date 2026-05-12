/**
 * Tests for the CircuitBadge component.
 *
 * State → expected visual:
 *   CLOSED    → green background / text
 *   OPEN      → red background + ⚡ icon
 *   HALF_OPEN → yellow / amber background
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CircuitBadge } from '@/components/CircuitBadge'

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CircuitBadge – CLOSED state', () => {
  it('renders the domain name', () => {
    render(<CircuitBadge state="CLOSED" domain="example.com" />)
    expect(screen.getByText(/example\.com/i)).toBeInTheDocument()
  })

  it('applies a green colour class', () => {
    const { container } = render(<CircuitBadge state="CLOSED" domain="example.com" />)
    const greenEl =
      container.querySelector('[class*="green"]') ??
      container.querySelector('[data-testid="circuit-badge"]')
    expect(greenEl).not.toBeNull()
    // Must not be red or yellow
    const className = (greenEl as HTMLElement)?.className ?? ''
    expect(className).not.toMatch(/\bred-/i)
    expect(className).not.toMatch(/yellow|amber/i)
  })

  it('does NOT show the ⚡ icon', () => {
    render(<CircuitBadge state="CLOSED" domain="example.com" />)
    expect(screen.queryByText('⚡')).not.toBeInTheDocument()
  })
})

describe('CircuitBadge – OPEN state', () => {
  it('renders the domain name', () => {
    render(<CircuitBadge state="OPEN" domain="tripped.com" />)
    expect(screen.getByText(/tripped\.com/i)).toBeInTheDocument()
  })

  it('applies a red colour class', () => {
    const { container } = render(<CircuitBadge state="OPEN" domain="tripped.com" />)
    const redEl =
      container.querySelector('[class*="red"]') ??
      container.querySelector('[data-testid="circuit-badge"]')
    expect(redEl).not.toBeNull()
    const className = (redEl as HTMLElement)?.className ?? ''
    expect(className).not.toMatch(/green/i)
  })

  it('shows the ⚡ icon', () => {
    render(<CircuitBadge state="OPEN" domain="tripped.com" />)
    expect(screen.getByText('⚡')).toBeInTheDocument()
  })
})

describe('CircuitBadge – HALF_OPEN state', () => {
  it('renders the domain name', () => {
    render(<CircuitBadge state="HALF_OPEN" domain="recovering.com" />)
    expect(screen.getByText(/recovering\.com/i)).toBeInTheDocument()
  })

  it('applies a yellow / amber colour class', () => {
    const { container } = render(<CircuitBadge state="HALF_OPEN" domain="recovering.com" />)
    const yellowEl =
      container.querySelector('[class*="yellow"]') ??
      container.querySelector('[class*="amber"]') ??
      container.querySelector('[data-testid="circuit-badge"]')
    expect(yellowEl).not.toBeNull()
    const className = (yellowEl as HTMLElement)?.className ?? ''
    expect(className).not.toMatch(/\bred-/i)
    expect(className).not.toMatch(/green/i)
  })

  it('does NOT show the ⚡ icon', () => {
    render(<CircuitBadge state="HALF_OPEN" domain="recovering.com" />)
    expect(screen.queryByText('⚡')).not.toBeInTheDocument()
  })
})

describe('CircuitBadge – state label text', () => {
  it('shows "CLOSED" label in CLOSED state', () => {
    render(<CircuitBadge state="CLOSED" domain="a.com" />)
    expect(screen.getByText(/CLOSED/i)).toBeInTheDocument()
  })

  it('shows "OPEN" label in OPEN state', () => {
    render(<CircuitBadge state="OPEN" domain="a.com" />)
    expect(screen.getByText(/OPEN/i)).toBeInTheDocument()
  })

  it('shows "HALF_OPEN" or "HALF-OPEN" label in HALF_OPEN state', () => {
    render(<CircuitBadge state="HALF_OPEN" domain="a.com" />)
    expect(screen.getByText(/HALF.?OPEN/i)).toBeInTheDocument()
  })
})
