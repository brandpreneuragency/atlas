import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { ChatMessage } from '../api/types'

export function SessionDetail() {
  const { sid = '' } = useParams()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .get<ChatMessage[]>(`/api/hermes/sessions/${sid}/messages`)
      .then((rows) => {
        if (!cancelled) setMessages(rows)
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sid])

  if (loading) {
    return <p className="text-slate-400">Loading transcript…</p>
  }
  return (
    <div className="space-y-4" data-testid="session-detail">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Session {sid}</h1>
        <Link to="/sessions" className="text-sm text-cyan-200 hover:underline">
          ← back
        </Link>
      </div>
      <div className="space-y-3">
        {messages.map((m, i) => {
          const isTool = m.role === 'tool' || m.role === 'function'
          if (isTool) {
            return (
              <details
                key={i}
                className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm"
              >
                <summary className="cursor-pointer text-slate-400">tool call</summary>
                <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300">
                  {m.content}
                </pre>
              </details>
            )
          }
          const isUser = m.role === 'user'
          return (
            <div
              key={i}
              className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                  isUser
                    ? 'bg-cyan-400/15 text-cyan-100'
                    : 'bg-slate-800/70 text-slate-200'
                }`}
              >
                <p className="mb-1 text-xs uppercase tracking-wider text-slate-500">
                  {m.role}
                </p>
                <p className="whitespace-pre-wrap">{m.content}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}