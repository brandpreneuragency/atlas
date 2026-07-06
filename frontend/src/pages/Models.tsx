import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import { ConfirmDialog } from '../components/files/ConfirmDialog'

type ModelInfo = {
  current: {
    model: string
    provider: string
    capabilities?: { context_window?: number }
  }
  options: { providers?: Record<string, string[]> }
}
type EnvEntry = {
  is_set?: boolean
  redacted_value?: string | null
  is_password?: boolean
  category?: string
}
type Prefs = { favorites: string[]; hidden: string[] }

function ModelRow({
  model,
  provider,
  prefs,
  onUse,
  onToggle,
}: {
  model: string
  provider: string
  prefs: Prefs
  onUse: (model: string, provider: string) => void
  onToggle: (kind: keyof Prefs, model: string) => void
}) {
  const fav = prefs.favorites.includes(model)
  const hidden = prefs.hidden.includes(model)
  return (
    <div
      data-testid={`model-row-${model}`}
      className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2"
    >
      <div className="flex items-center gap-2 truncate">
        <button
          type="button"
          aria-label={`favorite ${model}`}
          className={fav ? 'text-amber-300' : 'text-slate-600 hover:text-slate-300'}
          onClick={() => onToggle('favorites', model)}
        >
          ★
        </button>
        <button
          type="button"
          aria-label={`hide ${model}`}
          className={hidden ? 'text-red-300' : 'text-slate-600 hover:text-slate-300'}
          onClick={() => onToggle('hidden', model)}
        >
          🚫
        </button>
        <span className="truncate font-mono text-sm text-slate-200">{model}</span>
        <span className="text-xs text-slate-500">{provider}</span>
      </div>
      <button
        type="button"
        className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
        onClick={() => onUse(model, provider)}
      >
        Use this model
      </button>
    </div>
  )
}

export function Models() {
  const [info, setInfo] = useState<ModelInfo | null>(null)
  const [env, setEnv] = useState<Record<string, EnvEntry>>({})
  const [prefs, setPrefs] = useState<Prefs>({ favorites: [], hidden: [] })
  const [q, setQ] = useState('')
  const [showHidden, setShowHidden] = useState(false)
  const [keyName, setKeyName] = useState('')
  const [keyValue, setKeyValue] = useState('')
  const [deletingKey, setDeletingKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.get<ModelInfo>('/api/hermes/model').then(setInfo).catch(() => setInfo(null))
    api
      .get<Record<string, EnvEntry>>('/api/hermes/env')
      .then(setEnv)
      .catch(() => setEnv({}))
    api
      .get<Prefs>('/api/settings/model-prefs')
      .then(setPrefs)
      .catch(() => undefined)
  }, [])

  useEffect(load, [load])

  const savePrefs = async (next: Prefs) => {
    setPrefs(next)
    try {
      await api.put('/api/settings/model-prefs', next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'prefs save failed')
    }
  }

  const toggle = (kind: keyof Prefs, model: string) => {
    const list = prefs[kind]
    const next = list.includes(model)
      ? list.filter((m) => m !== model)
      : [...list, model]
    void savePrefs({ ...prefs, [kind]: next })
  }

  const use = async (model: string, provider: string) => {
    setError(null)
    try {
      await api.post('/api/hermes/model', { model, provider })
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'model switch failed')
    }
  }

  const allModels = useMemo(() => {
    const providers = info?.options.providers ?? {}
    return Object.entries(providers).flatMap(([provider, models]) =>
      models.map((model) => ({ provider, model })),
    )
  }, [info])

  const matches = (model: string) =>
    !q || model.toLowerCase().includes(q.toLowerCase())

  const favorites = allModels.filter(
    (m) => prefs.favorites.includes(m.model) && matches(m.model),
  )
  const hiddenModels = allModels.filter(
    (m) => prefs.hidden.includes(m.model) && matches(m.model),
  )
  const visibleByProvider = (() => {
    const grouped: Record<string, { provider: string; model: string }[]> = {}
    for (const entry of allModels) {
      if (prefs.hidden.includes(entry.model)) continue
      if (!matches(entry.model)) continue
      grouped[entry.provider] = grouped[entry.provider] ?? []
      grouped[entry.provider].push(entry)
    }
    return grouped
  })()

  return (
    <div className="space-y-8" data-testid="models-page">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Models</h1>
        <input
          aria-label="search models"
          className="w-72 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter models…"
        />
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}

      <section
        data-testid="current-model-card"
        className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5"
      >
        <p className="text-xs uppercase tracking-wider text-slate-500">
          Current model
        </p>
        {info ? (
          <div className="mt-2 flex items-baseline gap-4">
            <span className="text-2xl font-semibold text-slate-100">
              {info.current.model}
            </span>
            <span className="text-sm text-slate-400">{info.current.provider}</span>
            {info.current.capabilities?.context_window !== undefined && (
              <span className="text-sm text-slate-400">
                ctx {info.current.capabilities.context_window.toLocaleString('en-US')}
              </span>
            )}
          </div>
        ) : (
          <p className="mt-2 text-slate-400">unavailable</p>
        )}
      </section>

      {favorites.length > 0 && (
        <section data-testid="favorites-section" className="space-y-2">
          <h2 className="text-lg font-medium text-amber-200">★ Favorites</h2>
          {favorites.map((m) => (
            <ModelRow
              key={m.model}
              {...m}
              prefs={prefs}
              onUse={(model, provider) => void use(model, provider)}
              onToggle={toggle}
            />
          ))}
        </section>
      )}

      {Object.entries(visibleByProvider).map(([provider, models]) => (
        <section key={provider} className="space-y-2">
          <h2 className="text-lg font-medium text-slate-200">{provider}</h2>
          {models.map((m) => (
            <ModelRow
              key={m.model}
              {...m}
              prefs={prefs}
              onUse={(model, provider_) => void use(model, provider_)}
              onToggle={toggle}
            />
          ))}
        </section>
      ))}

      {hiddenModels.length > 0 && (
        <section>
          <button
            type="button"
            className="text-sm text-slate-400 hover:text-slate-200"
            onClick={() => setShowHidden((v) => !v)}
          >
            Show hidden ({hiddenModels.length})
          </button>
          {showHidden && (
            <div className="mt-2 space-y-2">
              {hiddenModels.map((m) => (
                <ModelRow
                  key={m.model}
                  {...m}
                  prefs={prefs}
                  onUse={(model, provider) => void use(model, provider)}
                  onToggle={toggle}
                />
              ))}
            </div>
          )}
        </section>
      )}

      <section
        data-testid="provider-keys-panel"
        className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-5"
      >
        <h2 className="text-lg font-medium text-slate-200">Provider keys</h2>
        <ul className="space-y-1">
          {Object.entries(env)
            .filter(([, entry]) => entry.is_set)
            .map(([name, entry]) => (
              <li
                key={name}
                className="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-2 text-sm"
              >
                <span className="font-mono text-slate-200">{name}</span>
                <span className="flex items-center gap-3">
                  <span className="font-mono text-slate-500">
                    {entry.redacted_value ?? '••••'}
                  </span>
                  <button
                    type="button"
                    className="text-xs text-red-300 hover:underline"
                    onClick={() => setDeletingKey(name)}
                  >
                    delete
                  </button>
                </span>
              </li>
            ))}
        </ul>
        <div className="flex items-end gap-2">
          <label className="flex-1 text-sm text-slate-300">
            Key name
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
            />
          </label>
          <label className="flex-1 text-sm text-slate-300">
            Key value
            <input
              type="password"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm"
              value={keyValue}
              onChange={(e) => setKeyValue(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!keyName || !keyValue}
            className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-40"
            onClick={() => {
              void (async () => {
                try {
                  await api.put('/api/hermes/env', {
                    key: keyName,
                    value: keyValue,
                  })
                  setKeyName('')
                  setKeyValue('')
                  load()
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'add key failed')
                }
              })()
            }}
          >
            Add key
          </button>
        </div>
      </section>

      {deletingKey && (
        <ConfirmDialog
          title={`Delete provider key ${deletingKey}?`}
          paths={[deletingKey]}
          confirmLabel="Confirm delete"
          onConfirm={() => {
            void (async () => {
              try {
                await api.delete(`/api/hermes/env/${deletingKey}`)
              } finally {
                setDeletingKey(null)
                load()
              }
            })()
          }}
          onCancel={() => setDeletingKey(null)}
        />
      )}
    </div>
  )
}
