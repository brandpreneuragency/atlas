import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, setOnUnauthorized } from '../api/client'
import { ConnectionBanner } from '../components/ui/ConnectionBanner'
import { DataState } from '../components/ui/DataState'
import { ErrorBoundary } from '../components/ui/ErrorBoundary'
import { useSession } from '../stores/useSession'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('DataState', () => {
  it('renders a loading skeleton', () => {
    render(
      <DataState loading={true} error={null} empty="none" onRetry={() => {}}>
        <p>content</p>
      </DataState>,
    )
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument()
    expect(screen.queryByText('content')).not.toBeInTheDocument()
  })

  it('renders the empty state', () => {
    render(
      <DataState loading={false} error={null} empty="Nothing here yet" isEmpty onRetry={() => {}}>
        <p>content</p>
      </DataState>,
    )
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })

  it('renders the error state with a working retry', async () => {
    const onRetry = vi.fn()
    render(
      <DataState loading={false} error="boom failed" onRetry={onRetry} empty="none">
        <p>content</p>
      </DataState>,
    )
    expect(screen.getByText(/boom failed/)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('renders children when loaded with data', () => {
    render(
      <DataState loading={false} error={null} empty="none" onRetry={() => {}}>
        <p>content</p>
      </DataState>,
    )
    expect(screen.getByText('content')).toBeInTheDocument()
  })
})

describe('ErrorBoundary', () => {
  it('catches render errors and recovers via try again', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    let shouldThrow = true
    function Bomb() {
      if (shouldThrow) throw new Error('kaboom')
      return <p>recovered</p>
    }
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    shouldThrow = false
    await userEvent.setup().click(screen.getByRole('button', { name: /try again/i }))
    expect(screen.getByText('recovered')).toBeInTheDocument()
    spy.mockRestore()
  })
})

describe('ConnectionBanner', () => {
  it('shows on SSE disconnect and clears on reconnect', () => {
    useSession.setState({ sseStatus: 'closed' })
    const { rerender } = render(<ConnectionBanner />)
    expect(screen.getByText(/live feed disconnected/i)).toBeInTheDocument()
    useSession.setState({ sseStatus: 'open' })
    rerender(<ConnectionBanner />)
    expect(screen.queryByText(/live feed disconnected/i)).not.toBeInTheDocument()
  })
})

describe('401 handling', () => {
  it('invokes the unauthorized handler on any 401 API response', async () => {
    const handler = vi.fn()
    setOnUnauthorized(handler)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{"detail":"unauthorized"}', { status: 401 })),
    )
    await expect(api.get('/api/agents')).rejects.toThrow()
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not redirect for a failed login attempt', async () => {
    const handler = vi.fn()
    setOnUnauthorized(handler)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{"detail":"bad password"}', { status: 401 })),
    )
    await expect(api.post('/api/auth/login', { password: 'x' })).rejects.toThrow()
    expect(handler).not.toHaveBeenCalled()
  })
})
