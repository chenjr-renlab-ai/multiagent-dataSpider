/**
 * Zustand mock: replaces the real `create` with a version that uses
 * React.useState under the hood so tests can use the store without a provider.
 * Follows the pattern recommended in the Zustand docs for testing.
 */
import { act } from '@testing-library/react'
import { vi } from 'vitest'

// Store a reference to every created store's setState so tests can reset state.
const storeResetFns = new Set<() => void>()

const createActual = await vi.importActual<typeof import('zustand')>('zustand')

// Re-export everything from the real module, only override `create`.
export * from 'zustand'

// Override `create` so each store registers a reset function.
export const create = vi.fn((stateCreator: Parameters<typeof createActual.create>[0]) => {
  const store = createActual.create(stateCreator)
  const initialState = store.getState()
  storeResetFns.add(() => store.setState(initialState, true))
  return store
})

// Utility used in afterEach to wipe all stores back to initial state.
export const resetAllStores = () => act(() => storeResetFns.forEach((fn) => fn()))
