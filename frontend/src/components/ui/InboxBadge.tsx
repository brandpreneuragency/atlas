import { useEffect, useState } from 'react'

import { api } from '../../api/client'
import type { Approval } from '../../api/types'
import { openAtlasSse } from '../../lib/sse'
import { useSession } from '../../stores/useSession'

/**
 * Pending-approval count for the sidebar: 30s poll + SSE `approval.requested`
 * push (a resolved approval is corrected on the next poll).
 */
export function InboxBadge() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    const refetch = () => {
      api
        .get<Approval[]>('/api/approvals?status=pending')
        .then((rows) => setCount(rows.length))
        .catch(() => undefined)
    }
    refetch()
    const timer = setInterval(refetch, 30_000)
    const sse =
      typeof EventSource === 'undefined'
        ? null
        : openAtlasSse({
            url: '/api/events/stream',
            // the badge is mounted on every Shell page — its connection doubles
            // as the global live-feed health signal (ConnectionBanner)
            onStatusChange: (status) => useSession.getState().setSseStatus(status),
            onEvent: (eventJson) => {
              try {
                const event = JSON.parse(eventJson) as { kind?: string }
                if (event.kind === 'approval.requested') {
                  setCount((c) => c + 1)
                }
                if (event.kind === 'approval.resolved') {
                  setCount((c) => Math.max(0, c - 1))
                }
              } catch {
                // malformed frame — ignore
              }
            },
          })
    return () => {
      clearInterval(timer)
      sse?.close()
    }
  }, [])

  if (count === 0) return null
  return (
    <span className="ml-2 inline-flex min-w-5 items-center justify-center rounded-full bg-cyan-400/20 px-1.5 py-0.5 text-xs font-medium text-cyan-200">
      {count}
    </span>
  )
}
