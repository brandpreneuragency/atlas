import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AtlasEvent, WorkflowRun } from '../api/types'
import { RunPanel } from '../components/flow/RunPanel'
import { applyRunEvent } from '../components/flow/runStates'
import type { RunNodeStates } from '../components/flow/runStates'
import { RunDetail } from '../pages/RunDetail'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const RUN: WorkflowRun = {
  id: 9,
  workflow_id: 3,
  status: 'succeeded',
  trigger_kind: 'manual',
  trigger_payload: {},
  dry_run: false,
  error: null,
  cost_usd: 0.0123,
  tokens_in: 100,
  tokens_out: 50,
  created_at: '2026-07-06T10:00:00+00:00',
  started_at: '2026-07-06T10:00:00+00:00',
  finished_at: '2026-07-06T10:00:09+00:00',
}

function makeEvent(kind: string, payload: Record<string, unknown>): AtlasEvent {
  return {
    id: 1,
    ts: '',
    kind,
    source: 'engine',
    workflow_id: 3,
    run_id: 9,
    payload: { summary: 's', ...payload },
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('applyRunEvent', () => {
  it('transitions node states from SSE step events', () => {
    let states: RunNodeStates = {}
    states = applyRunEvent(states, makeEvent('run.step_started', { node_id: 'h' }))
    expect(states.h).toBe('running')
    states = applyRunEvent(
      states,
      makeEvent('run.step_finished', { node_id: 'h', status: 'succeeded' }),
    )
    expect(states.h).toBe('succeeded')
    states = applyRunEvent(
      states,
      makeEvent('run.step_finished', { node_id: 'f', status: 'failed' }),
    )
    expect(states.f).toBe('failed')
    states = applyRunEvent(states, makeEvent('run.waiting_approval', { node_id: 'g' }))
    expect(states.g).toBe('waiting')
  })
})

describe('RunPanel', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/api/runs?')) return jsonResponse([RUN])
      if (url === '/api/workflows/3/run' && init?.method === 'POST') {
        return jsonResponse({ run_id: 10 })
      }
      return jsonResponse({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('Run and Dry run buttons POST with the dry_run flag', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <RunPanel workflowId={3} />
      </MemoryRouter>,
    )
    await user.click(screen.getByRole('button', { name: /^run$/i }))
    await user.click(screen.getByRole('button', { name: /dry run/i }))

    const posts = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
    )
    expect(posts).toHaveLength(2)
    expect(JSON.parse(String((posts[0][1] as RequestInit).body))).toMatchObject({
      dry_run: false,
    })
    expect(JSON.parse(String((posts[1][1] as RequestInit).body))).toMatchObject({
      dry_run: true,
    })
  })

  it('lists recent runs with status chip and cost', async () => {
    render(
      <MemoryRouter>
        <RunPanel workflowId={3} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('succeeded')).toBeInTheDocument()
    expect(screen.getByText(/manual/)).toBeInTheDocument()
    expect(screen.getByText(/\$0.0123/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /#9/ })).toHaveAttribute(
      'href',
      '/automation/runs/9',
    )
  })
})

describe('RunDetail', () => {
  it('renders steps with collapsible I/O and error text', async () => {
    const detail = {
      ...RUN,
      status: 'failed',
      error: "step h: timeout after 5s",
      steps: [
        {
          id: 1,
          node_id: 'h',
          node_type: 'hermes.task',
          status: 'failed',
          input: { prompt: 'Do it' },
          output: {},
          error: 'timeout after 5s',
          cost_usd: 0,
          started_at: null,
          finished_at: null,
        },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/runs/9') return jsonResponse(detail)
        if (url.startsWith('/api/approvals')) return jsonResponse([])
        return jsonResponse({}, 404)
      }),
    )
    render(
      <MemoryRouter initialEntries={['/automation/runs/9']}>
        <Routes>
          <Route path="/automation/runs/:id" element={<RunDetail />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText(/hermes.task/)).toBeInTheDocument()
    expect(screen.getAllByText(/timeout after 5s/).length).toBeGreaterThan(0)
    expect(screen.getByText(/"prompt"/)).toBeInTheDocument()
  })

  it('waiting_approval shows Approve/Reject that resolves', async () => {
    const detail = { ...RUN, status: 'waiting_approval', steps: [] }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/runs/9') return jsonResponse(detail)
      if (url === '/api/approvals?status=pending') {
        return jsonResponse([
          { id: 4, run_id: 9, message: 'Go?', status: 'pending' },
        ])
      }
      if (url === '/api/approvals/4/resolve' && init?.method === 'POST') {
        return jsonResponse({ id: 4, status: 'approved' })
      }
      return jsonResponse({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/automation/runs/9']}>
        <Routes>
          <Route path="/automation/runs/:id" element={<RunDetail />} />
        </Routes>
      </MemoryRouter>,
    )
    await user.click(await screen.findByRole('button', { name: /approve/i }))
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            String(call[0]) === '/api/approvals/4/resolve' &&
            (call[1] as RequestInit | undefined)?.method === 'POST',
        ),
      ).toBe(true)
    })
    const resolveCall = fetchMock.mock.calls.find(
      (call) => String(call[0]) === '/api/approvals/4/resolve',
    )
    expect(
      JSON.parse(String((resolveCall?.[1] as RequestInit).body)),
    ).toMatchObject({ decision: 'approved' })
  })
})
