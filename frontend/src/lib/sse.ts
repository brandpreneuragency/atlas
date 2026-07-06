type SseStatus = 'connecting' | 'open' | 'closed'

type AtlasSseOptions = {
  url: string
  onEvent: (eventJson: string) => void
  onStatusChange?: (status: SseStatus) => void
  maxBackoffMs?: number
}

/**
 * EventSource wrapper with exponential backoff reconnect (1s → 30s cap).
 * Parses `event: atlas` frames and forwards the `data:` payload to `onEvent`.
 * Returns a `close()` for cleanup.
 */
export function openAtlasSse({
  url,
  onEvent,
  onStatusChange,
  maxBackoffMs = 30_000,
}: AtlasSseOptions): { close: () => void } {
  let backoff = 1_000
  let closed = false
  let es: EventSource | null = null

  const setStatus = (s: SseStatus) => {
    if (onStatusChange) onStatusChange(s)
  }

  const connect = () => {
    if (closed) return
    setStatus('connecting')
    es = new EventSource(url)

    es.addEventListener('open', () => {
      backoff = 1_000
      setStatus('open')
    })

    es.addEventListener('atlas', (ev) => {
      // Event data is the JSON payload of one atlas event.
      onEvent((ev as MessageEvent).data as string)
    })

    es.addEventListener('error', () => {
      setStatus('closed')
      es?.close()
      if (closed) return
      setTimeout(connect, backoff)
      backoff = Math.min(backoff * 2, maxBackoffMs)
    })
  }

  connect()

  return {
    close: () => {
      closed = true
      es?.close()
      setStatus('closed')
    },
  }
}