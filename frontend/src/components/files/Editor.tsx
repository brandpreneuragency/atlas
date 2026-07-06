import { markdown } from '@codemirror/lang-markdown'
import CodeMirror from '@uiw/react-codemirror'
import { useCallback, useEffect, useState } from 'react'

import { api, ApiError } from '../../api/client'

export function Editor({
  path,
  initialContent,
  mtime,
  onSaved,
  onReload,
}: {
  path: string
  initialContent: string
  mtime: number
  onSaved: () => void
  onReload: () => void
}) {
  const [content, setContent] = useState(initialContent)
  const [dirty, setDirty] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = useCallback(
    async (expectedMtime: number | null) => {
      setError(null)
      try {
        await api.put('/api/files/write', {
          path,
          content,
          expected_mtime: expectedMtime,
        })
        setDirty(false)
        setConflict(false)
        onSaved()
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setConflict(true)
        } else {
          setError(err instanceof Error ? err.message : 'save failed')
        }
      }
    },
    [path, content, onSaved],
  )

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 's') {
        event.preventDefault()
        void save(mtime)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [save, mtime])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-slate-500">
          {path}
          {dirty && (
            <span className="ml-2 text-amber-300" data-testid="dirty-indicator">
              ● unsaved
            </span>
          )}
        </span>
        <button
          type="button"
          className="rounded-lg bg-cyan-500 px-3 py-1.5 text-sm font-medium text-slate-950"
          onClick={() => void save(mtime)}
        >
          Save
        </button>
      </div>
      {conflict && (
        <div
          data-testid="conflict-banner"
          className="flex items-center justify-between rounded-xl border border-amber-500/50 bg-amber-500/10 px-4 py-2 text-sm text-amber-200"
        >
          <span>File changed on disk since you opened it.</span>
          <span className="flex gap-2">
            <button
              type="button"
              className="rounded-lg border border-amber-400/60 px-2 py-1"
              onClick={onReload}
            >
              Reload
            </button>
            <button
              type="button"
              className="rounded-lg bg-amber-400 px-2 py-1 font-medium text-slate-950"
              onClick={() => void save(null)}
            >
              Overwrite anyway
            </button>
          </span>
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-red-500/50 bg-red-500/10 px-4 py-2 text-sm text-red-200">
          {error}
        </div>
      )}
      <div className="overflow-hidden rounded-2xl border border-slate-800">
        <CodeMirror
          value={content}
          height="60vh"
          theme="dark"
          extensions={[markdown()]}
          onChange={(value) => {
            setContent(value)
            setDirty(true)
          }}
        />
      </div>
    </div>
  )
}
