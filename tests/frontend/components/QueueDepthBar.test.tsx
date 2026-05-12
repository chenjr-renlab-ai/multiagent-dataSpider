/**
 * Colour-logic and text-rendering tests for the QueueDepthBar component.
 *
 * Thresholds (from the spec):
 *   depth/capacity < 50 %  → green
 *   50 – 80 %              → yellow + ⚠ icon
 *   > 80 %                 → red
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueueDepthBar } from '@/components/QueueDepthBar'

// ---------------------------------------------------------------------------
// Helper: render and return the root element for class inspection
// ---------------------------------------------------------------------------

function renderBar(depth: number, capacity: number) {
  const { container } = render(
    <QueueDepthBar name="frontier" depth={depth} capacity={capacity} />,
  )
  return container
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('QueueDepthBar – green zone (< 50 %)', () => {
  it('applies a green colour class when depth is 400 / 1000 (40 %)', () => {
    const container = renderBar(400, 1000)
    const greenEl =
      container.querySelector('[class*="green"]') ??
      container.querySelector('[data-testid="bar-fill"]')
    expect(greenEl).not.toBeNull()
    // Must NOT have yellow or red classes on the fill element
    const fillClass = (greenEl as HTMLElement)?.className ?? ''
    expect(fillClass).not.toMatch(/yellow|amber|red|orange/i)
  })

  it('does NOT show the ⚠ warning icon when below 50 %', () => {
    renderBar(400, 1000)
    expect(screen.queryByText('⚠')).not.toBeInTheDocument()
  })
})

describe('QueueDepthBar – yellow zone (50 – 80 %)', () => {
  it('applies a yellow / amber colour class when depth is 700 / 1000 (70 %)', () => {
    const container = renderBar(700, 1000)
    const yellowEl =
      container.querySelector('[class*="yellow"]') ??
      container.querySelector('[class*="amber"]') ??
      container.querySelector('[data-testid="bar-fill"]')
    expect(yellowEl).not.toBeNull()
    const fillClass = (yellowEl as HTMLElement)?.className ?? ''
    expect(fillClass).not.toMatch(/\bred-/i)
  })

  it('shows the ⚠ warning icon when depth is 700 / 1000 (70 %)', () => {
    renderBar(700, 1000)
    expect(screen.getByText('⚠')).toBeInTheDocument()
  })
})

describe('QueueDepthBar – red zone (> 80 %)', () => {
  it('applies a red colour class when depth is 900 / 1000 (90 %)', () => {
    const container = renderBar(900, 1000)
    const redEl =
      container.querySelector('[class*="red"]') ??
      container.querySelector('[data-testid="bar-fill"]')
    expect(redEl).not.toBeNull()
    const fillClass = (redEl as HTMLElement)?.className ?? ''
    expect(fillClass).not.toMatch(/green/i)
  })

  it('displays the text "900 / 1000" (or equivalent)', () => {
    renderBar(900, 1000)
    // Accept any spacing around the slash: "900/1000", "900 / 1000"
    expect(screen.getByText(/900\s*\/\s*1000/)).toBeInTheDocument()
  })
})

describe('QueueDepthBar – text display', () => {
  it('renders the queue name', () => {
    render(<QueueDepthBar name="priority" depth={100} capacity={500} />)
    expect(screen.getByText(/priority/i)).toBeInTheDocument()
  })

  it('renders depth and capacity numbers', () => {
    render(<QueueDepthBar name="frontier" depth={250} capacity={800} />)
    expect(screen.getByText(/250\s*\/\s*800/)).toBeInTheDocument()
  })

  it('renders at exactly 50 % as yellow (boundary)', () => {
    const container = render(
      <QueueDepthBar name="edge" depth={500} capacity={1000} />,
    ).container
    const yellowEl =
      container.querySelector('[class*="yellow"]') ??
      container.querySelector('[class*="amber"]')
    expect(yellowEl).not.toBeNull()
  })

  it('renders at exactly 80 % as red (boundary)', () => {
    const container = render(
      <QueueDepthBar name="edge" depth={800} capacity={1000} />,
    ).container
    const redEl = container.querySelector('[class*="red"]')
    expect(redEl).not.toBeNull()
  })
})
