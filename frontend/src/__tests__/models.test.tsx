import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Models } from '../pages/Models'

const MODEL = {
  current: {
    model: 'gpt-5.5',
    provider: 'openai-codex',
    capabilities: { context_window: 1050000 },
  },
  options: {
    providers: {
      'openai-codex': ['gpt-5.5', 'gpt-5.5-mini'],
      openrouter: ['stepfun/step-3.7-flash:free'],
    },
  },
}
const ENV = {
  OPENROUTER_API_KEY: {
    is_set: true,
    redacted_value: 'sk-o...61b8',
    is_password: true,
    category: 'provider',
  },
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>
let prefs: { favorites: string[]; hidden: string[] }

describe('Models page', () => {
  beforeEach(() => {
    prefs = { favorites: [], hidden: [] }
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/api/hermes/model') && init?.method !== 'POST')
        return jsonResponse(MODEL)
      if (url.startsWith('/api/settings/model-prefs')) {
        if (init?.method === 'PUT') {
          prefs = JSON.parse(String(init.body))
          return jsonResponse(prefs)
        }
        return jsonResponse(prefs)
      }
      if (
        url.startsWith('/api/hermes/env') &&
        (init?.method ?? 'GET') === 'GET'
      )
        return jsonResponse(ENV)
      return jsonResponse({}, 200)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders current model card and provider sections', async () => {
    render(<Models />)
    const card = await screen.findByTestId('current-model-card')
    expect(within(card).getByText('gpt-5.5')).toBeInTheDocument()
    expect(within(card).getByText(/openai-codex/)).toBeInTheDocument()
    expect(within(card).getByText(/1,?050,?000|1050000/)).toBeInTheDocument()

    expect(
      screen.getByRole('heading', { name: 'openrouter' }),
    ).toBeInTheDocument()
    expect(screen.getByText('stepfun/step-3.7-flash:free')).toBeInTheDocument()
  })

  it('use-this-model posts model + provider', async () => {
    const user = userEvent.setup()
    render(<Models />)
    await screen.findByTestId('current-model-card')
    const row = screen.getByTestId('model-row-gpt-5.5-mini')
    await user.click(within(row).getByRole('button', { name: /use this model/i }))
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (c) =>
          String(c[0]).startsWith('/api/hermes/model') &&
          (c[1] as RequestInit)?.method === 'POST',
      )
      expect(call).toBeDefined()
      const body = JSON.parse(String((call![1] as RequestInit).body))
      expect(body).toEqual({ model: 'gpt-5.5-mini', provider: 'openai-codex' })
    })
  })

  it('favorite persists via model-prefs and floats to top', async () => {
    const user = userEvent.setup()
    render(<Models />)
    await screen.findByTestId('current-model-card')
    await user.click(screen.getByLabelText('favorite gpt-5.5-mini'))

    await waitFor(() => {
      expect(prefs.favorites).toEqual(['gpt-5.5-mini'])
    })
    const favSection = await screen.findByTestId('favorites-section')
    expect(within(favSection).getByText('gpt-5.5-mini')).toBeInTheDocument()
  })

  it('hidden models collapse under a disclosure', async () => {
    const user = userEvent.setup()
    render(<Models />)
    await screen.findByTestId('current-model-card')
    await user.click(screen.getByLabelText('hide stepfun/step-3.7-flash:free'))

    await waitFor(() => {
      expect(prefs.hidden).toEqual(['stepfun/step-3.7-flash:free'])
    })
    expect(
      screen.queryByTestId('model-row-stepfun/step-3.7-flash:free'),
    ).not.toBeInTheDocument()
    await user.click(screen.getByText(/show hidden \(1\)/i))
    expect(
      screen.getByTestId('model-row-stepfun/step-3.7-flash:free'),
    ).toBeInTheDocument()
  })

  it('search filters model rows', async () => {
    const user = userEvent.setup()
    render(<Models />)
    await screen.findByTestId('current-model-card')
    await user.type(screen.getByLabelText(/search models/i), 'stepfun')
    expect(
      screen.getByTestId('model-row-stepfun/step-3.7-flash:free'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('model-row-gpt-5.5-mini')).not.toBeInTheDocument()
  })

  it('provider keys panel lists masked keys and adds a key', async () => {
    const user = userEvent.setup()
    render(<Models />)
    const panel = await screen.findByTestId('provider-keys-panel')
    expect(within(panel).getByText('OPENROUTER_API_KEY')).toBeInTheDocument()
    expect(within(panel).getByText('sk-o...61b8')).toBeInTheDocument()

    await user.type(within(panel).getByLabelText(/key name/i), 'FAKE_TEST_KEY')
    await user.type(within(panel).getByLabelText(/key value/i), 'shh-secret')
    await user.click(within(panel).getByRole('button', { name: /add key/i }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (c) =>
          String(c[0]) === '/api/hermes/env' &&
          (c[1] as RequestInit)?.method === 'PUT',
      )
      expect(call).toBeDefined()
      const body = JSON.parse(String((call![1] as RequestInit).body))
      expect(body).toEqual({ key: 'FAKE_TEST_KEY', value: 'shh-secret' })
    })
  })
})
