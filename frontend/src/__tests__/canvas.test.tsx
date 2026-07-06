import '@testing-library/jest-dom/vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowGraph } from '../api/types'
import { fromFlow, toFlow, useGraph } from '../components/flow/useGraph'

// The MASTER_PLAN §6 example graph — the round-trip test is exact.
const EXAMPLE: WorkflowGraph = {
  nodes: [
    { id: 'n1', type: 'trigger.cron', position: { x: 0, y: 0 }, config: { expr: '0 7 * * *' } },
    {
      id: 'n2',
      type: 'hermes.task',
      position: { x: 260, y: 0 },
      config: {
        prompt: 'Summarize {{trigger.file_path}}',
        context_files: [],
        session_key: null,
        timeout_s: 900,
        retries: 1,
      },
    },
    {
      id: 'n3',
      type: 'gate.approval',
      position: { x: 520, y: 0 },
      config: { message: 'Publish digest?', timeout_h: 24, notify: ['telegram'] },
    },
    {
      id: 'n4',
      type: 'file.op',
      position: { x: 780, y: 0 },
      config: { op: 'write', path: '04_reports/digest.md', content: '{{n2.output_text}}' },
    },
  ],
  edges: [
    { id: 'e1', source: 'n1', target: 'n2', condition: null },
    { id: 'e2', source: 'n2', target: 'n3', condition: null },
    { id: 'e3', source: 'n3', target: 'n4', condition: 'approved' },
  ],
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

describe('graph conversion', () => {
  it('round-trips the §6 example graph losslessly', () => {
    const { nodes, edges } = toFlow(EXAMPLE)
    expect(fromFlow(nodes, edges)).toEqual(EXAMPLE)
  })

  it('renders edge condition as label', () => {
    const { edges } = toFlow(EXAMPLE)
    const gateEdge = edges.find((e) => e.id === 'e3')
    expect(gateEdge?.label).toBe('approved')
  })
})

describe('useGraph', () => {
  it('addNode appends with unique id n<max+1>', () => {
    const { result } = renderHook(() => useGraph(EXAMPLE))
    act(() => {
      result.current.addNode('notify.telegram', { x: 10, y: 10 })
    })
    const added = result.current.nodes[result.current.nodes.length - 1]
    expect(added.id).toBe('n5')
    const graph = fromFlow(result.current.nodes, result.current.edges)
    expect(graph.nodes).toHaveLength(5)
    expect(graph.nodes[4].type).toBe('notify.telegram')
  })

  it('deleteNode removes the node and its edges', () => {
    const { result } = renderHook(() => useGraph(EXAMPLE))
    act(() => {
      result.current.deleteNode('n2')
    })
    const graph = fromFlow(result.current.nodes, result.current.edges)
    expect(graph.nodes.map((n) => n.id)).toEqual(['n1', 'n3', 'n4'])
    expect(graph.edges.map((e) => e.id)).toEqual(['e3'])
  })

  it('save PUTs the serialized graph and reports the new version', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/workflows/7') {
        return jsonResponse({ id: 7, name: 'wf', version: 2, graph: EXAMPLE })
      }
      return jsonResponse({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGraph(EXAMPLE))
    let version: number | undefined
    await act(async () => {
      version = await result.current.save(7, { name: 'wf', description: '' })
    })
    expect(version).toBe(2)

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.method).toBe('PUT')
    const body = JSON.parse(String(init.body)) as { graph: WorkflowGraph }
    expect(body.graph).toEqual(EXAMPLE)
    await waitFor(() => expect(result.current.dirty).toBe(false))
  })

  it('tracks dirty state on edits', () => {
    const { result } = renderHook(() => useGraph(EXAMPLE))
    expect(result.current.dirty).toBe(false)
    act(() => {
      result.current.addNode('file.op', { x: 0, y: 0 })
    })
    expect(result.current.dirty).toBe(true)
  })
})
