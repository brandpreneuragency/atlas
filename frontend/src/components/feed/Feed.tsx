import { useEffect, useRef, useState } from 'react'

import { api } from '../../api/client'
import type { AtlasEvent } from '../../api/types'
import { openAtlasSse } from '../../lib/sse'
import { EventRow } from './EventRow'

export function Feed({ initialEvents = [] }: { initialEvents?: AtlasEvent[] }) {
  const [events, setEvents] = useState<AtlasEvent[]>(initialEvents)
  const seen = useRef<Set<number>>(new Set(initialEvents.map((e) => e.id)))

  // initial fetch (overridden by tests via initialEvents)
  useEffect(() => {
    if (initialEvents.length) return
    let cancelled = false
    api
      .get<AtlasEvent[]>('/api/events?limit=50')
      .then((rows) => {
        if (cancelled) return
        const fresh = rows.filter((r) => !seen.current.has(r.id))
        fresh.forEach((r) => seen.current.add(r.id))
        if (fresh.length) setEvents((prev) => [...fresh, ...prev])
      })
      .catch(() => {
        /* feed is best-effort; errors surface via the connection dot */
      })
    return () => {
      cancelled = true
    }
  }, [initialEvents.length])

  // live SSE prepend (no refetch)
  useEffect(() => {
    const sse = openAtlasSse({
      url: '/api/events/stream',
      onEvent: (raw) => {
        try {
          const ev = JSON.parse(raw) as AtlasEvent
          if (seen.current.has(ev.id)) return
          seen.current.add(ev.id)
          setEvents((prev) => [ev, ...prev])
        } catch {
          /* ignore malformed frames */
        }
      },
    })
    return () => sse.close()
  }, [])

  return (
    <section
      aria-label="live-feed"
      className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20"
    >
      <h2 className="mb-3 text-lg font-semibold text-slate-100">Live feed</h2>
      <ul>
        {events.map((e) => (
          <EventRow key={e.id} event={e} />
        ))}
      </ul>
    </section>
  )
}