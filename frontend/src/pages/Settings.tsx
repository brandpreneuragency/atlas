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

type Limits = {
  default_max_runs_per_hour: number
  default_budget_usd_per_run: number | null
  global_concurrency: number
}

function LimitsSettings() {
  const [mrph, setMrph] = useState('')
  const [budget, setBudget] = useState('')
  const [concurrency, setConcurrency] = useState<number | null>(null)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Limits>('/api/settings/limits')
      .then((body) => {
        setMrph(String(body.default_max_runs_per_hour))
        setBudget(body.default_budget_usd_per_run === null ? '' : String(body.default_budget_usd_per_run))
        setConcurrency(body.global_concurrency)
      })
      .catch(() => undefined)
  }, [])

  const save = async () => {
    setStatus(null)
    try {
      await api.put('/api/settings/limits', {
        default_max_runs_per_hour: Number(mrph),
        default_budget_usd_per_run: budget === '' ? null : Number(budget),
      })
      setStatus('Saved — applied to new workflows.')
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'save failed')
    }
  }

  const input =
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm'

  return (
    <section className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
      <h2 className="text-lg font-medium text-slate-200">Run limits & budgets</h2>
      <label className="block text-sm text-slate-300">
        Default max runs per hour
        <input
          type="number"
          min={1}
          className={input}
          value={mrph}
          onChange={(e) => setMrph(e.target.value)}
        />
      </label>
      <label className="block text-sm text-slate-300">
        Default budget per run (USD, empty = no cap)
        <input
          type="number"
          step="0.01"
          className={input}
          value={budget}
          onChange={(e) => setBudget(e.target.value)}
        />
      </label>
      <p className="text-sm text-slate-400">
        Global concurrency: <span className="text-slate-200">{concurrency ?? '…'}</span>{' '}
        <span className="text-xs text-slate-500">(fixed — engine semaphore)</span>
      </p>
      {status && <p className="text-sm text-slate-300">{status}</p>}
      <button
        type="button"
        className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950"
        onClick={() => void save()}
      >
        Save limits
      </button>
    </section>
  )
}

type BackupInfo = {
  ok: boolean
  ts?: string
  size?: number
  reason?: string
  error?: string
}

function BackupStatus() {
  const [info, setInfo] = useState<BackupInfo | null>(null)

  useEffect(() => {
    api
      .get<BackupInfo>('/api/settings/backup')
      .then(setInfo)
      .catch(() => setInfo(null))
  }, [])

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5" data-testid="backup-status">
      <h2 className="text-lg font-medium text-slate-200">Backups</h2>
      {info === null ? (
        <p className="mt-2 text-sm text-slate-500">status unavailable</p>
      ) : (
        <p className="mt-2 flex items-center gap-2 text-sm text-slate-300">
          <span
            className={`h-2.5 w-2.5 rounded-full ${info.ok ? 'bg-emerald-400' : 'bg-rose-400'}`}
          />
          {info.ok ? (
            <>
              last backup {info.ts ? new Date(info.ts).toLocaleString() : 'unknown time'}
              {typeof info.size === 'number' && (
                <span className="text-slate-500">· {(info.size / 1024).toFixed(0)} KB</span>
              )}
            </>
          ) : (
            <span className="text-rose-300">{info.reason ?? info.error ?? 'failed'}</span>
          )}
        </p>
      )}
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

      <LimitsSettings />

      <NotificationSettings />
      <BackupStatus />
    </div>
  )
}
