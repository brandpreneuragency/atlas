import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Files } from '../pages/Files'

type TreeEntry = { name: string; is_dir: boolean; size: number; mtime: number }

const rootEntries: TreeEntry[] = [
  { name: '01_inbox', is_dir: true, size: 0, mtime: 1783300000 },
  { name: 'readme.md', is_dir: false, size: 20, mtime: 1783300000 },
]
const inboxEntries: TreeEntry[] = [
  { name: 'a.md', is_dir: false, size: 9, mtime: 1783300100 },
  { name: 'b.md', is_dir: false, size: 9, mtime: 1783300100 },
]

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

function installFetch(overrides?: (url: string, init?: RequestInit) => Response | null) {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (overrides) {
      const hit = overrides(url, init)
      if (hit) return hit
    }
    if (url.startsWith('/api/files/tree')) {
      const path = new URL(url, 'http://t').searchParams.get('path') ?? ''
      if (path === '') return jsonResponse({ entries: rootEntries })
      if (path === '01_inbox') return jsonResponse({ entries: inboxEntries })
      return jsonResponse({ entries: [] })
    }
    if (url.startsWith('/api/files/read')) {
      return jsonResponse({ content: '# Hello\n\nworld', mtime: 1783300100, truncated: false })
    }
    return jsonResponse({}, 204)
  })
  vi.stubGlobal('fetch', fetchMock)
}

describe('Files page', () => {
  beforeEach(() => installFetch())

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders root entries and lazily expands a directory on click', async () => {
    const user = userEvent.setup()
    render(<Files />)

    expect(await screen.findByText('01_inbox')).toBeInTheDocument()
    expect(screen.getByText('readme.md')).toBeInTheDocument()
    expect(screen.queryByText('a.md')).not.toBeInTheDocument()

    await user.click(screen.getByText('01_inbox'))
    expect(await screen.findByText('a.md')).toBeInTheDocument()
    expect(screen.getByText('b.md')).toBeInTheDocument()

    const treeCalls = fetchMock.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.startsWith('/api/files/tree'))
    expect(treeCalls.some((u) => u.includes('01_inbox'))).toBe(true)
  })

  it('shows rendered markdown with an Edit toggle when selecting a .md file', async () => {
    const user = userEvent.setup()
    render(<Files />)

    await user.click(await screen.findByText('readme.md'))

    // react-markdown renders "# Hello" as a heading
    expect(await screen.findByRole('heading', { name: 'Hello' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument()
  })

  it('save sends expected_mtime and 409 shows conflict banner with actions', async () => {
    installFetch((url, init) => {
      if (url.startsWith('/api/files/write') && init?.method === 'PUT') {
        return jsonResponse({ detail: 'file changed on disk (mtime mismatch)' }, 409)
      }
      return null
    })
    const user = userEvent.setup()
    render(<Files />)

    await user.click(await screen.findByText('readme.md'))
    await user.click(await screen.findByRole('button', { name: /edit/i }))
    await user.click(await screen.findByRole('button', { name: /^save$/i }))

    expect(await screen.findByTestId('conflict-banner')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /overwrite anyway/i })).toBeInTheDocument()

    const writeCall = fetchMock.mock.calls.find(
      (c) => String(c[0]).startsWith('/api/files/write'),
    )
    expect(writeCall).toBeDefined()
    const body = JSON.parse(String((writeCall![1] as RequestInit).body))
    expect(body.expected_mtime).toBe(1783300100)
    expect(body.path).toBe('readme.md')
  })

  it('delete shows a ConfirmDialog listing affected paths', async () => {
    const user = userEvent.setup()
    render(<Files />)

    await user.click(await screen.findByLabelText('select readme.md'))
    await user.click(screen.getByRole('button', { name: /delete/i }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('readme.md')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: /confirm/i }))
    await waitFor(() => {
      const del = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith('/api/files/delete'),
      )
      expect(del).toBeDefined()
      const body = JSON.parse(String((del![1] as RequestInit).body))
      expect(body.paths).toEqual(['readme.md'])
    })
  })

  it('multi-select enables bulk move and delete in the toolbar', async () => {
    const user = userEvent.setup()
    render(<Files />)

    await screen.findByText('01_inbox')
    const moveButton = screen.getByRole('button', { name: /move/i })
    const deleteButton = screen.getByRole('button', { name: /delete/i })
    expect(moveButton).toBeDisabled()
    expect(deleteButton).toBeDisabled()

    await user.click(screen.getByLabelText('select readme.md'))
    await user.click(screen.getByLabelText('select 01_inbox'))
    expect(moveButton).toBeEnabled()
    expect(deleteButton).toBeEnabled()

    await user.click(moveButton)
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/destination/i), '02_processed')
    await user.click(within(dialog).getByRole('button', { name: /confirm/i }))

    await waitFor(() => {
      const move = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith('/api/files/move'),
      )
      expect(move).toBeDefined()
      const body = JSON.parse(String((move![1] as RequestInit).body))
      expect(body.paths).toEqual(['01_inbox', 'readme.md'])
      expect(body.dest).toBe('02_processed')
    })
  })
})
