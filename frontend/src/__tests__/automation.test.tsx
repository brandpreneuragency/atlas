import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { MemoryRouter } from 'react-router-dom'

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
      if (url.startsWith('/api/workflows')) return jsonResponse([])
      if (url.startsWith('/api/runs')) return jsonResponse([])
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows workflows empty state and cron job rows', async () => {
    render(<MemoryRouter><Automation /></MemoryRouter>)
    expect(await screen.findByText(/No workflows yet/)).toBeInTheDocument()

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
    render(<MemoryRouter><Automation /></MemoryRouter>)
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
    render(<MemoryRouter><Automation /></MemoryRouter>)
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

describe('Automation workflows section', () => {
  const WF = {
    id: 3,
    name: 'digest',
    description: '',
    graph: {
      nodes: [
        { id: 'n1', type: 'trigger.cron', position: { x: 0, y: 0 }, config: { expr: '0 8 * * *' } },
      ],
      edges: [],
    },
    enabled: true,
    version: 4,
    max_runs_per_hour: 6,
    budget_usd_per_run: null,
    created_at: '2026-07-06T00:00:00+00:00',
    updated_at: '2026-07-06T00:00:00+00:00',
  }
  const TODAY_RUN = {
    id: 11,
    workflow_id: 3,
    status: 'succeeded',
    trigger_kind: 'cron',
    trigger_payload: {},
    dry_run: false,
    error: null,
    cost_usd: 0.02,
    tokens_in: 1,
    tokens_out: 1,
    created_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
  }

  let wfFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    wfFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/api/hermes/cron')) return jsonResponse([JOB])
      if (url === '/api/workflows' && init?.method === 'POST') {
        return jsonResponse({ ...WF, id: 42, name: 'New workflow' }, 201)
      }
      if (url.startsWith('/api/workflows')) return jsonResponse([WF])
      if (url.startsWith('/api/runs')) return jsonResponse([TODAY_RUN])
      return jsonResponse({}, 204)
    })
    vi.stubGlobal('fetch', wfFetch)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('lists workflows with enable toggle, last run, schedule, count and cost', async () => {
    render(<MemoryRouter><Automation /></MemoryRouter>)
    expect(await screen.findByText('digest')).toBeInTheDocument()
    expect(screen.getByText('succeeded')).toBeInTheDocument()
    expect(screen.getByText(/daily at 08:00/)).toBeInTheDocument()
    const row = screen.getByTestId('workflow-row-3')
    expect(within(row).getByText('1')).toBeInTheDocument() // runs today
    expect(within(row).getByText(/\$0.02/)).toBeInTheDocument() // cost today
    expect(within(row).getByRole('switch')).toBeChecked()
  })

  it('enable toggle posts to the enable endpoint', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Automation /></MemoryRouter>)
    await user.click(await screen.findByRole('switch'))
    await waitFor(() => {
      const call = wfFetch.mock.calls.find((c) =>
        String(c[0]).endsWith('/api/workflows/3/enable'),
      )
      expect(call).toBeDefined()
      expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
        enabled: false,
      })
    })
  })

  it('New workflow creates a manual-trigger workflow', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Automation /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: /new workflow/i }))
    await waitFor(() => {
      const call = wfFetch.mock.calls.find(
        (c) =>
          String(c[0]) === '/api/workflows' &&
          (c[1] as RequestInit | undefined)?.method === 'POST',
      )
      expect(call).toBeDefined()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.graph.nodes).toHaveLength(1)
      expect(body.graph.nodes[0].type).toBe('trigger.manual')
    })
  })
})

describe('VersionsDrawer', () => {
  it('lists versions and rolls back after confirm', async () => {
    const { VersionsDrawer } = await import('../components/flow/VersionsDrawer')
    const versions = [
      { id: 1, workflow_id: 3, version: 1, created_at: '2026-07-05T10:00:00+00:00' },
      { id: 2, workflow_id: 3, version: 2, created_at: '2026-07-06T10:00:00+00:00' },
    ]
    const rolled = { id: 3, name: 'digest', version: 3, graph: { nodes: [], edges: [] } }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/workflows/3/versions') return jsonResponse(versions)
      if (url === '/api/workflows/3/rollback' && init?.method === 'POST') {
        return jsonResponse(rolled)
      }
      return jsonResponse({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => true))

    const onRollback = vi.fn()
    render(
      <VersionsDrawer workflowId={3} currentVersion={2} onRollback={onRollback} onClose={vi.fn()} />,
    )
    expect(await screen.findByText('v1')).toBeInTheDocument()
    expect(screen.getByText('v2')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /rollback/i }))
    await waitFor(() => expect(onRollback).toHaveBeenCalled())
    const call = fetchMock.mock.calls.find((c) =>
      String(c[0]).endsWith('/rollback'),
    )
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ version: 1 })
  })
})

describe('Automation guardrails (Task 8.2)', () => {
  const WF_OK = {
    id: 3, name: 'digest', description: '', enabled: true, version: 1,
    max_runs_per_hour: 6, budget_usd_per_run: null,
    graph: { nodes: [], edges: [] },
    created_at: '2026-07-06T00:00:00+00:00', updated_at: '2026-07-06T00:00:00+00:00',
  }
  const WF_BUDGET = { ...WF_OK, id: 4, name: 'expensive' }
  const WF_BREAKER = { ...WF_OK, id: 5, name: 'loopy' }
  const runBase = {
    trigger_kind: 'manual', trigger_payload: {}, dry_run: false,
    tokens_in: 0, tokens_out: 0, started_at: null, finished_at: null,
    created_at: new Date().toISOString(),
  }
  const RUNS = [
    { ...runBase, id: 20, workflow_id: 3, status: 'succeeded', error: null, cost_usd: 1.25 },
    { ...runBase, id: 21, workflow_id: 4, status: 'budget_exceeded', error: 'budget exceeded ($0.5 > $0.1)', cost_usd: 0.5 },
    { ...runBase, id: 22, workflow_id: 5, status: 'failed', error: 'circuit breaker', cost_usd: 0 },
  ]

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/hermes/cron')) return jsonResponse([])
      if (url.startsWith('/api/workflows')) return jsonResponse([WF_OK, WF_BUDGET, WF_BREAKER])
      if (url.startsWith('/api/runs')) return jsonResponse(RUNS)
      return jsonResponse({}, 204)
    }))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows today totals across all workflows', async () => {
    render(<MemoryRouter><Automation /></MemoryRouter>)
    const totals = await screen.findByTestId('workflow-totals')
    expect(totals).toHaveTextContent('3 runs today')
    expect(totals).toHaveTextContent('$1.75')
  })

  it('budget_exceeded and circuit breaker get distinct badges with reason', async () => {
    render(<MemoryRouter><Automation /></MemoryRouter>)
    const budgetBadge = await screen.findByTestId('guard-badge-4')
    expect(budgetBadge).toHaveTextContent(/budget/i)
    expect(budgetBadge).toHaveAttribute('title', expect.stringContaining('$0.5'))
    const breakerBadge = screen.getByTestId('guard-badge-5')
    expect(breakerBadge).toHaveTextContent(/circuit breaker/i)
    expect(screen.queryByTestId('guard-badge-3')).not.toBeInTheDocument()
  })
})
