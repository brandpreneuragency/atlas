import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Settings } from '../pages/Settings'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Settings limits section (Task 8.2)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/settings/limits' && init?.method === 'PUT') {
        return jsonResponse({
          default_max_runs_per_hour: 3,
          default_budget_usd_per_run: 0.5,
          global_concurrency: 2,
        })
      }
      if (url === '/api/settings/limits') {
        return jsonResponse({
          default_max_runs_per_hour: 6,
          default_budget_usd_per_run: null,
          global_concurrency: 2,
        })
      }
      if (url === '/api/killswitch') return jsonResponse({ paused: false })
      if (url === '/api/settings/notifications') {
        return jsonResponse({
          telegram_bot_token_set: false,
          telegram_chat_id: '',
          smtp_url_set: false,
          smtp_to: '',
        })
      }
      if (url === '/api/settings/backup') {
        return jsonResponse({ ok: false, reason: 'no backup yet' })
      }
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows editable defaults and read-only concurrency', async () => {
    render(<Settings />)
    const mrph = await screen.findByLabelText(/default max runs per hour/i)
    expect(mrph).toHaveValue(6)
    expect(screen.getByLabelText(/default budget/i)).toHaveValue(null)
    // concurrency is display-only
    expect(screen.getByText(/global concurrency/i)).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.queryByLabelText(/global concurrency/i)).not.toBeInTheDocument()
  })

  it('saves edited defaults via PUT', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    const mrph = await screen.findByLabelText(/default max runs per hour/i)
    await user.clear(mrph)
    await user.type(mrph, '3')
    await user.type(screen.getByLabelText(/default budget/i), '0.5')
    await user.click(screen.getByRole('button', { name: /save limits/i }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (c) =>
          String(c[0]) === '/api/settings/limits' &&
          (c[1] as RequestInit | undefined)?.method === 'PUT',
      )
      expect(call).toBeDefined()
      expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
        default_max_runs_per_hour: 3,
        default_budget_usd_per_run: 0.5,
      })
    })
  })

  it('shows backup status', async () => {
    render(<Settings />)
    expect(await screen.findByTestId('backup-status')).toHaveTextContent(
      /no backup yet/i,
    )
  })
})
