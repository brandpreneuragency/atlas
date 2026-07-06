import { useRef, useState } from 'react'

import { api } from '../../api/client'
import { ConfirmDialog } from './ConfirmDialog'

export function Toolbar({
  selection,
  onMutated,
  onClearSelection,
}: {
  selection: string[]
  onMutated: () => void
  onClearSelection: () => void
}) {
  const [dialog, setDialog] = useState<'move' | 'delete' | null>(null)
  const [dest, setDest] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const run = async (action: () => Promise<unknown>) => {
    setError(null)
    try {
      await action()
      setDialog(null)
      onClearSelection()
      onMutated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'operation failed')
    }
  }

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const form = new FormData()
    form.set('path', '')
    form.set('file', files[0])
    await run(() => api.postForm('/api/files/upload', form))
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
        onClick={() => fileInput.current?.click()}
      >
        Upload
      </button>
      <input
        ref={fileInput}
        type="file"
        aria-label="upload file"
        className="hidden"
        onChange={(e) => void upload(e.target.files)}
      />
      <button
        type="button"
        disabled={selection.length === 0}
        className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40"
        onClick={() => {
          setDest('')
          setDialog('move')
        }}
      >
        Move
      </button>
      <button
        type="button"
        disabled={selection.length === 0}
        className="rounded-lg border border-red-900 px-3 py-1.5 text-sm text-red-300 hover:bg-red-950 disabled:opacity-40"
        onClick={() => setDialog('delete')}
      >
        Delete
      </button>
      {error && <span className="text-xs text-red-300">{error}</span>}

      {dialog === 'move' && (
        <ConfirmDialog
          title={`Move ${selection.length} item(s)`}
          paths={selection}
          onConfirm={() =>
            void run(() =>
              api.post('/api/files/move', { paths: selection, dest }),
            )
          }
          onCancel={() => setDialog(null)}
        >
          <label className="mt-3 block text-sm text-slate-300">
            Destination
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100"
              value={dest}
              onChange={(e) => setDest(e.target.value)}
              placeholder="02_processed/01_short"
            />
          </label>
        </ConfirmDialog>
      )}
      {dialog === 'delete' && (
        <ConfirmDialog
          title={`Delete ${selection.length} item(s)?`}
          paths={selection}
          confirmLabel="Confirm delete"
          onConfirm={() =>
            void run(() =>
              api.post('/api/files/delete', {
                paths: selection,
                recursive: true,
              }),
            )
          }
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}
