/**
 * Interaction tests for the MissionForm component.
 *
 * Network calls are intercepted by mocking global.fetch so no real HTTP
 * requests are made.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MissionForm } from '@/components/MissionForm'

// ---------------------------------------------------------------------------
// fetch mock
// ---------------------------------------------------------------------------

const mockFetch = vi.fn()

beforeEach(() => {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ id: 'mission-1', name: 'Test Mission' }),
  })
  global.fetch = mockFetch
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setup() {
  const user = userEvent.setup()
  const utils = render(<MissionForm />)
  return { user, ...utils }
}

// Selectors – use accessible queries where possible, fall back to placeholders / labels.
function getNameInput() {
  return (
    screen.queryByRole('textbox', { name: /name/i }) ??
    screen.queryByPlaceholderText(/name/i) ??
    screen.getByTestId('mission-name')
  )
}

function getUrlInput() {
  return (
    screen.queryByRole('textbox', { name: /url|target/i }) ??
    screen.queryByPlaceholderText(/url|target/i) ??
    screen.getByTestId('target-url')
  )
}

function getSubmitButton() {
  return (
    screen.queryByRole('button', { name: /submit|create|start/i }) ??
    screen.getByTestId('submit-button')
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MissionForm – initial state', () => {
  it('renders the name input field', () => {
    setup()
    expect(getNameInput()).toBeInTheDocument()
  })

  it('renders the target URL input field', () => {
    setup()
    expect(getUrlInput()).toBeInTheDocument()
  })

  it('submit button is disabled when name is empty', () => {
    setup()
    expect(getSubmitButton()).toBeDisabled()
  })
})

describe('MissionForm – enabling the submit button', () => {
  it('enables the submit button after typing a name', async () => {
    const { user } = setup()

    await user.type(getNameInput(), 'My Crawl Mission')

    expect(getSubmitButton()).not.toBeDisabled()
  })

  it('disables the submit button again when the name is cleared', async () => {
    const { user } = setup()

    const nameInput = getNameInput()
    await user.type(nameInput, 'Temporary')
    expect(getSubmitButton()).not.toBeDisabled()

    await user.clear(nameInput)
    expect(getSubmitButton()).toBeDisabled()
  })
})

describe('MissionForm – form submission', () => {
  it('calls POST /api/missions with the correct payload on submit', async () => {
    const { user } = setup()

    await user.type(getNameInput(), 'Spider Mission')
    await user.type(getUrlInput(), 'https://target.example.com')
    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledOnce()
    })

    const [url, options] = mockFetch.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/missions/)
    expect(options?.method?.toUpperCase()).toBe('POST')

    const body = JSON.parse(options?.body as string)
    expect(body).toMatchObject({ name: 'Spider Mission' })
  })

  it('resets the form after a successful submission', async () => {
    const { user } = setup()

    const nameInput = getNameInput()
    await user.type(nameInput, 'One-Time Mission')
    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })

    // Name field should be cleared
    expect((nameInput as HTMLInputElement).value).toBe('')
  })

  it('does not submit if fetch rejects (shows no crash)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    const { user } = setup()
    await user.type(getNameInput(), 'Mission')
    await user.click(getSubmitButton())

    // Component should remain in the DOM without throwing
    await waitFor(() => {
      expect(getNameInput()).toBeInTheDocument()
    })
  })
})

describe('MissionForm – multiple targets', () => {
  it('shows an "add target" button', () => {
    setup()
    const addBtn =
      screen.queryByRole('button', { name: /add.*(target|url)|添加目标/i }) ??
      screen.queryByTestId('add-target-button')
    expect(addBtn).not.toBeNull()
  })

  it('adds a new target URL row when the "add target" button is clicked', async () => {
    const { user } = setup()

    const urlInputsBefore = screen.queryAllByPlaceholderText(/url|target/i).length

    const addBtn =
      screen.queryByRole('button', { name: /add.*(target|url)|添加目标/i }) ??
      screen.getByTestId('add-target-button')

    await user.click(addBtn)

    const urlInputsAfter = screen.queryAllByPlaceholderText(/url|target/i).length
    expect(urlInputsAfter).toBeGreaterThan(urlInputsBefore)
  })

  it('can add multiple targets', async () => {
    const { user } = setup()

    const addBtn =
      screen.queryByRole('button', { name: /add.*(target|url)|添加目标/i }) ??
      screen.getByTestId('add-target-button')

    await user.click(addBtn)
    await user.click(addBtn)

    // Should now have at least 3 URL inputs (1 initial + 2 added)
    const urlInputs = screen.queryAllByPlaceholderText(/url|target/i)
    expect(urlInputs.length).toBeGreaterThanOrEqual(3)
  })

  it('includes all target URLs in the POST body', async () => {
    const { user } = setup()

    await user.type(getNameInput(), 'Multi Target Mission')
    await user.type(getUrlInput(), 'https://first.com')

    const addBtn =
      screen.queryByRole('button', { name: /add.*(target|url)|添加目标/i }) ??
      screen.getByTestId('add-target-button')

    await user.click(addBtn)

    const allUrlInputs = screen.queryAllByPlaceholderText(/url|target/i)
    // Type into the second URL field
    if (allUrlInputs[1]) {
      await user.type(allUrlInputs[1], 'https://second.com')
    }

    await user.click(getSubmitButton())

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })

    const [, options] = mockFetch.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(options?.body as string)

    // The body should contain both URLs somewhere (as array or object)
    const bodyStr = JSON.stringify(body)
    expect(bodyStr).toContain('first.com')
    expect(bodyStr).toContain('second.com')
  })
})
