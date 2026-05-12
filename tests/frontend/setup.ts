import '@testing-library/jest-dom'

// Mock WebSocket globally
global.WebSocket = class MockWebSocket {
  onopen: (() => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((e: Event) => void) | null = null
  send = vi.fn()
  close = vi.fn()
  constructor(public url: string) {
    setTimeout(() => this.onopen?.(), 0)
  }
} as unknown as typeof WebSocket
