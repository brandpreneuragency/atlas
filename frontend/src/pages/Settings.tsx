import { useEffect, useState } from 'react'

import { api } from '../api/client'

type NotifyView = {
  telegram_bot_token_set: boolean
  telegram_chat_id: string
  smtp_url_set: boolean
  smtp_to: string
}

function NotificationSettings() {
  const [view, setView] = useState<NotifyView | null>(null)
  const [token, setToken] = useState('')
  const [chatId, setChatId] = useState('')
  const [smtpUrl, setSmtpUrl] = useState('')
  const [smtpTo, setSmtpTo] = useState('')
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<NotifyView>('/api/settings/notifications')
      .then((body) => {
        setView(body)
        setChatId(body.telegram_chat_id)
        setSmtpTo(body.smtp_to)
      })
      .catch(() => setView(null))
  }, [])

  const save = async () => {
    setStatus(null)
    const body: Record<string, string> = {}
    if (token) body.telegram_bot_token = token
    if (chatId) body.telegram_chat_id = chatId
    if (smtpUrl) body.smtp_url = smtpUrl
    if (smtpTo) body.smtp_to = smtpTo
    try {
      const updated = await api.put<NotifyView>('/api/settings/notifications', body)
      setView(updated)
      setToken('')
      setSmtpUrl('')
      setStatus('Saved.')
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'save failed')
    }
  }

  const sendTest = async () => {
    setStatus('Sending test message…')
    try {
      const result = await api.post<{ telegram: boolean; email: boolean }>(
        '/api/settings/notifications/test',
        {},
      )
      setStatus(
        `Test: telegram ${result.telegram ? 'sent ✓' : 'failed / not configured'}, ` +
          `email ${result.email ? 'sent ✓' : 'failed / not configured'}`,
      )
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'test failed')
    }
  }

  const input =
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm'

  return (
    <section className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
      <h2 className="text-lg font-medium text-slate-200">Notifications</h2>
      <label className="block text-sm text-slate-300">
        Telegram bot token{' '}
        {view?.telegram_bot_token_set && (
          <span className="text-xs text-emerald-400">(set)</span>
        )}
        <input
          type="password"
          className={input}
          placeholder={view?.telegram_bot_token_set ? '•••••• (leave blank to keep)' : ''}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
      </label>
      <label className="block text-sm text-slate-300">
        Telegram chat id
        <input
          className={input}
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
        />
      </label>
      <label className="block text-sm text-slate-300">
        SMTP URL{' '}
        {view?.smtp_url_set && <span className="text-xs text-emerald-400">(set)</span>}
        <input
          type="password"
          className={input}
          placeholder={view?.smtp_url_set ? '•••••• (leave blank to keep)' : 'smtp://user:pass@host:port'}
          value={smtpUrl}
          onChange={(e) => setSmtpUrl(e.target.value)}
        />
      </label>
      <label className="block text-sm text-slate-300">
        Email to
        <input
          className={input}
          value={smtpTo}
          onChange={(e) => setSmtpTo(e.target.value)}
        />
      </label>
      {status && <p className="text-sm text-slate-300">{status}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950"
          onClick={() => void save()}
        >
          Save
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200"
          onClick={() => void sendTest()}
        >
          Send test message
        </button>
      </div>
    </section>
  )
}

export function Settings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [paused, setPaused] = useState<boolean | null>(null)

  useEffect(() => {
    api
      .get<{ paused: boolean }>('/api/killswitch')
      .then((body) => setPaused(body.paused))
      .catch(() => setPaused(null))
  }, [])

  const changePassword = async () => {
    setMessage(null)
    try {
      await api.post('/api/settings/password', { current, new: next })
      setMessage('Password changed.')
      setCurrent('')
      setNext('')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'change failed')
    }
  }

  return (
    <div className="max-w-xl space-y-8" data-testid="settings-page">
      <h1 className="text-3xl font-semibold">Settings</h1>

      <section className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <h2 className="text-lg font-medium text-slate-200">Change password</h2>
        <label className="block text-sm text-slate-300">
          Current password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-300">
          New password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </label>
        {message && <p className="text-sm text-slate-300">{message}</p>}
        <button
          type="button"
          disabled={!current || !next}
          className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-40"
          onClick={() => void changePassword()}
        >
          Change password
        </button>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <h2 className="text-lg font-medium text-slate-200">Kill switch</h2>
        <p className="mt-2 text-sm text-slate-400">
          {paused === null
            ? 'state unknown'
            : paused
              ? 'ENGAGED — automation paused'
              : 'released — automation running'}
        </p>
      </section>

      <NotificationSettings />
      <section className="rounded-2xl border border-dashed border-slate-800 p-5 text-sm text-slate-500">
        Backups — coming in Phase 8
      </section>
    </div>
  )
}
