import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fixtureAgent } from '../api/fixtures'
import { Agent } from '../pages/Agent'

const encoder = new TextEncoder()

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Agent chat', () => {
  let streamController: ReadableStreamDefaultController<Uint8Array>

  beforeEach(() => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: RequestInfo | URL, init?: RequestInit) => {
        const path = String(url)
        if (path.startsWith('/api/agents')) {
          return Promise.resolve(jsonResponse([fixtureAgent]))
        }
        if (path === '/api/hermes/chat' && init?.method === 'POST') {
          return Promise.resolve(new Response(stream, { status: 200 }))
        }
        return Promise.reject(new Error(`unexpected fetch: ${path}`))
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('sends a message and renders streamed tokens progressively', async () => {
    render(<Agent />)
    await screen.findByText('Hermes') // agent card loaded

    fireEvent.change(screen.getByLabelText('chat message'), {
      target: { value: 'Reply PONG' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    // user bubble appears immediately
    await waitFor(() =>
      expect(screen.getByTestId('chat-log').textContent).toContain('Reply PONG'),
    )

    // first token
    streamController.enqueue(encoder.encode('data: PO\n\n'))
    await waitFor(() =>
      expect(screen.getByTestId('chat-log').textContent).toContain('assistant: PO'),
    )

    // second token appends to the same assistant bubble (progressive)
    streamController.enqueue(encoder.encode('data: NG\n\n'))
    await waitFor(() =>
      expect(screen.getByTestId('chat-log').textContent).toContain('assistant: PONG'),
    )

    streamController.close()

    // send button re-enables once the stream ends
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled(),
    )

    const chatCalls = (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([u]) => String(u) === '/api/hermes/chat',
    )
    expect(chatCalls).toHaveLength(1)
    expect(JSON.parse((chatCalls[0][1] as RequestInit).body as string)).toEqual({
      thread_id: null,
      message: 'Reply PONG',
    })
  })
})
