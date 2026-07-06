import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { describeCron } from '../lib/cron'
import { Automation } from '../pages/Automation'

const JOB = {
  id: 'ae1df3bdd2c5',
  name: 'App Store Market Scout',
  prompt: 'Scout the app store',
  schedule: { kind: 'cron', expr: '*/30 * * * *', display: '*/30 * * * *' },
  enabled: false,
  state: 'paused',
  last_status: 'error',
  last_error: 'RuntimeError: HTTP 429: The usage limit has been reached',
  next_run_at: '2026-07-01T03:30:00+00:00',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

describe('describeCron', () => {
  it('humanizes common expressions', () => {
    expect(describeCron('*/30 * * * *')).toBe('every 30 min')
    expect(describeCron('0 * * * *')).toBe('hourly')
    expect(describeCron('15 9 * * *')).toBe('daily at 09:15')
    expect(describeCron('whatever weird')).toBe('whatever weird')
  })
})

describe('Automation page', () => {
  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/hermes/cron')) return jsonResponse([JOB])
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows workflows empty state and cron job rows', async () => {
    render(<Automation />)
    expect(
      screen.getByText(/No workflows yet — coming in Phase 6/),
    ).toBeInTheDocument()

    expect(await screen.findByText('App Store Market Scout')).toBeInTheDocument()
    expect(screen.getByText('every 30 min')).toBeInTheDocument()
    const badge = screen.getByTestId('job-state-ae1df3bdd2c5')
    expect(badge).toHaveTextContent('paused')
    expect(badge).toHaveAttribute('title', expect.stringContaining('429'))
    expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run now/i })).toBeInTheDocument()
  })

  it('resume button posts to the resume endpoint', async () => {
    const user = userEvent.setup()
    render(<Automation />)
    await user.click(await screen.findByRole('button', { name: /resume/i }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).endsWith('/api/hermes/cron/ae1df3bdd2c5/resume'),
      )
      expect(call).toBeDefined()
    })
  })

  it('edit opens a modal with live cron validation', async () => {
    const user = userEvent.setup()
    render(<Automation />)
    await user.click(await screen.findByRole('button', { name: /edit/i }))

    const dialog = await screen.findByRole('dialog')
    const exprInput = within(dialog).getByLabelText(/cron expression/i)
    expect(exprInput).toHaveValue('*/30 * * * *')
    expect(within(dialog).getByText('every 30 min')).toBeInTheDocument()

    await user.clear(exprInput)
    await user.type(exprInput, 'nope')
    expect(within(dialog).getByText(/invalid cron/i)).toBeInTheDocument()
  })
})
