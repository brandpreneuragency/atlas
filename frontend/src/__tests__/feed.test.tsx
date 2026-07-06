import '@testing-library/jest-dom/vitest'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fixtureEvents } from '../api/fixtures'
import type { AtlasEvent } from '../api/types'
import { Feed } from '../components/feed/Feed'
import { installMockEventSource, MockEventSource } from './helpers/MockEventSource'

describe('Feed', () => {
  beforeEach(() => {
    installMockEventSource()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders fixture events newest first with icon, summary and relative time', () => {
    render(<Feed initialEvents={fixtureEvents} />)

    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(fixtureEvents.length)

    // fixtureEvents is newest-first (ids 3, 2, 1); rendered order must match
    expect(within(rows[0]).getByText('admin signed in')).toBeInTheDocument()
    expect(within(rows[1]).getByText('chat reply (12 chars)')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Digest workflow started')).toBeInTheDocument()

    // kind icon per row
    expect(within(rows[0]).getByLabelText('kind-system.login')).toHaveTextContent('🔑')
    expect(within(rows[2]).getByLabelText('kind-run.started')).toHaveTextContent('▶')

    // relative time (fixtures are 1m / 5m / 12m in the past)
    expect(screen.getByTestId('event-reltime-3')).toHaveTextContent('1m ago')
    expect(screen.getByTestId('event-reltime-1')).toHaveTextContent('12m ago')
  })

  it('prepends a new SSE event without refetching', async () => {
    render(<Feed initialEvents={fixtureEvents} />)

    const newEvent: AtlasEvent = {
      id: 4,
      ts: new Date().toISOString(),
      kind: 'system.killswitch',
      source: 'system',
      payload: { summary: 'kill switch engaged' },
    }

    const es = MockEventSource.instances[0]
    expect(es).toBeDefined()
    expect(es.url).toBe('/api/events/stream')

    await act(async () => {
      es.emit('atlas', JSON.stringify(newEvent))
    })

    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(fixtureEvents.length + 1)
    expect(within(rows[0]).getByText('kill switch engaged')).toBeInTheDocument()

    // no refetch: initialEvents suppress the list fetch and SSE must not trigger one
    expect(fetch).not.toHaveBeenCalled()
  })

  it('ignores duplicate event ids from the stream', async () => {
    render(<Feed initialEvents={fixtureEvents} />)
    const es = MockEventSource.instances[0]

    await act(async () => {
      es.emit('atlas', JSON.stringify(fixtureEvents[0]))
    })

    expect(screen.getAllByRole('listitem')).toHaveLength(fixtureEvents.length)
  })
})
