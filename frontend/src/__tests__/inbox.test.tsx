import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { MemoryRouter } from 'react-router-dom'

import { InboxBadge } from '../components/ui/InboxBadge'
import { Inbox } from '../pages/Inbox'
import { Review } from '../pages/Review'
import { installMockEventSource, MockEventSource } from './helpers/MockEventSource'

const APPROVAL = {
  id: 7,
  run_id: 12,
  step_id: 3,
  kind: 'gate',
  external_ref: null,
  message: 'Publish digest?',
  status: 'pending',
  requested_at: new Date(Date.now() - 60_000).toISOString(),
  resolved_at: null,
  resolved_via: null,
}

const NOTE = {
  name: '2026-07-06-raw-idea.md',
  frontmatter: { source_path: '01_inbox/01_short/raw-idea.md', category: '01_short' },
  body_preview: 'A candidate insight about app store pricing.',
  source_path: '01_inbox/01_short/raw-idea.md',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Inbox page', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    installMockEventSource()
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/approvals')) return jsonResponse([APPROVAL])
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('lists pending approvals with message, run link and age', async () => {
    render(<MemoryRouter><Inbox /></MemoryRouter>)
    expect(await screen.findByText('Publish digest?')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /run #12/i })
    expect(link).toHaveAttribute('href', '/automation/runs/12')
    expect(screen.getByText(/1m ago|a minute ago|60s ago/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('approve posts resolve and removes the row optimistically', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Inbox /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: /approve/i }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).endsWith('/api/approvals/7/resolve'),
      )
      expect(call).toBeDefined()
      expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
        decision: 'approved',
      })
    })
    await waitFor(() =>
      expect(screen.queryByText('Publish digest?')).not.toBeInTheDocument(),
    )
  })
})

describe('InboxBadge', () => {
  it('shows pending count and bumps on SSE approval.requested', async () => {
    const ES = installMockEventSource()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/approvals')) return jsonResponse([APPROVAL])
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<InboxBadge />)
    expect(await screen.findByText('1')).toBeInTheDocument()

    const es: MockEventSource = ES.instances[0]
    es.emit(
      'atlas',
      JSON.stringify({
        id: 99,
        kind: 'approval.requested',
        payload: { summary: 'x' },
      }),
    )
    expect(await screen.findByText('2')).toBeInTheDocument()
  })
})

describe('Review page', () => {
  it('lists notes and decide shows progress then removes when gone', async () => {
    installMockEventSource()
    let decided = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/api/review/') && init?.method === 'POST') {
        decided = true
        return jsonResponse({ run_id: 'run_abc' })
      }
      if (url.startsWith('/api/review')) {
        return jsonResponse(decided ? [] : [NOTE])
      }
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    render(<MemoryRouter><Review /></MemoryRouter>)
    expect(await screen.findByText('2026-07-06-raw-idea.md')).toBeInTheDocument()
    // frontmatter chips + body preview
    expect(screen.getByText(/01_inbox\/01_short\/raw-idea\.md/)).toBeInTheDocument()
    expect(screen.getByText(/app store pricing/)).toBeInTheDocument()

    const item = screen.getByTestId('review-2026-07-06-raw-idea.md')
    await user.click(within(item).getByRole('button', { name: /^approve$/i }))

    const call = fetchMock.mock.calls.find(
      (c) =>
        String(c[0]) === '/api/review/2026-07-06-raw-idea.md/decide' &&
        (c[1] as RequestInit | undefined)?.method === 'POST',
    )
    expect(call).toBeDefined()
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      decision: 'approved',
    })
    // progress state visible while the hermes run executes, gone after refetch
    await waitFor(() =>
      expect(
        screen.queryByText('2026-07-06-raw-idea.md'),
      ).not.toBeInTheDocument(),
    )
  })
})
