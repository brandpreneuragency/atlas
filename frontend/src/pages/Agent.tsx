import { useState } from 'react'

import { AgentCard } from '../components/cards/AgentCard'
import { api } from '../api/client'
import type { AgentStatus } from '../api/types'

type ChatState = {
  threadId: number | null
  messages: { role: 'user' | 'assistant'; content: string }[]
  streaming: boolean
}

export function Agent() {
  const [agent, setAgent] = useState<AgentStatus | null>(null)
  const [chat, setChat] = useState<ChatState>({
    threadId: null,
    messages: [],
    streaming: false,
  })
  const [draft, setDraft] = useState('')

  const loadAgent = async () => {
    try {
      const agents = await api.get<AgentStatus[]>('/api/agents')
      if (agents.length) setAgent(agents[0])
    } catch {
      setAgent(null)
    }
  }

  const send = async () => {
    const message = draft.trim()
    if (!message || chat.streaming) return
    setDraft('')
    setChat((c) => ({
      ...c,
      streaming: true,
      messages: [...c.messages, { role: 'user', content: message }],
      // reserve the assistant bubble
    }))

    try {
      const tokenStream = await fetch('/api/hermes/chat', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-Atlas-CSRF': '1' },
        body: JSON.stringify({ thread_id: chat.threadId, message }),
      })
      if (!tokenStream.ok || !tokenStream.body) throw new Error('chat failed')
      const reader = tokenStream.body.getReader()
      const decoder = new TextDecoder()
      let assistantText = ''
      setChat((c) => ({ ...c, messages: [...c.messages, { role: 'assistant', content: '' }] }))
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        for (const line of buffer.split('\n')) {
          if (line.startsWith('data:')) {
            const chunk = line.slice(5).trim()
            if (!chunk) continue
            if (chunk === '') continue
            assistantText += chunk
            // update the last assistant message progressively
            setChat((c) => {
              const next = [...c.messages]
              next[next.length - 1] = {
                role: 'assistant',
                content: assistantText,
              }
              return { ...c, messages: next }
            })
          }
        }
        buffer = ''
      }
    } finally {
      setChat((c) => ({ ...c, streaming: false }))
      // refresh agent active runs after the run finishes
      await loadAgent()
    }
  }

  return (
    <div className="space-y-6" data-testid="agent-page">
      <div>
        <h1 className="text-3xl font-semibold">Agent</h1>
        <p className="mt-2 text-slate-400">
          Status and dispatch for the Hermes agent.
        </p>
      </div>
      <AgentCardInline agent={agent} loadAgent={loadAgent} />
      <section
        aria-label="chat"
        className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20"
      >
        <h2 className="mb-3 text-lg font-semibold text-slate-100">Chat</h2>
        <div data-testid="chat-log" className="mb-3 space-y-2 text-sm">
          {chat.messages.map((m, i) => (
            <p key={i} className={`${m.role === 'user' ? 'text-cyan-200' : 'text-slate-200'}`}>
              <strong className="font-medium">{m.role}: </strong>
              {m.content}
            </p>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            aria-label="chat message"
            className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void send()
            }}
            placeholder="Say something…"
          />
          <button
            type="button"
            className="rounded-lg bg-cyan-400/20 px-4 py-2 text-sm text-cyan-100"
            onClick={() => void send()}
            disabled={chat.streaming}
          >
            Send
          </button>
        </div>
      </section>
    </div>
  )
}

function AgentCardInline({
  agent,
  loadAgent,
}: {
  agent: AgentStatus | null
  loadAgent: () => Promise<void>
}) {
  if (!agent) {
    void loadAgent()
    return (
      <div data-testid="agent-card-loading" className="text-slate-400">
        Loading…
      </div>
    )
  }
  return <AgentCard agent={agent} />
}