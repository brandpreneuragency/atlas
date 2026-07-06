import { useCallback, useState } from 'react'

import { api } from '../api/client'
import { Editor } from '../components/files/Editor'
import { Preview } from '../components/files/Preview'
import { Toolbar } from '../components/files/Toolbar'
import { Tree } from '../components/files/Tree'

type OpenFile = {
  path: string
  content: string
  mtime: number
}

export function Files() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [selection, setSelection] = useState<Set<string>>(new Set())
  const [open, setOpen] = useState<OpenFile | null>(null)
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), [])

  const openFile = useCallback(async (path: string) => {
    try {
      const body = await api.get<{ content: string; mtime: number }>(
        `/api/files/read?path=${encodeURIComponent(path)}`,
      )
      setOpen({ path, content: body.content, mtime: body.mtime })
      setMode('preview')
    } catch {
      setOpen(null)
    }
  }, [])

  const toggleSelect = useCallback((path: string) => {
    setSelection((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }, [])

  const crumbs = open ? open.path.split('/') : []

  return (
    <div className="space-y-4" data-testid="files-page">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Files</h1>
        <Toolbar
          selection={Array.from(selection).sort()}
          onMutated={() => {
            refresh()
            setOpen(null)
          }}
          onClearSelection={() => setSelection(new Set())}
        />
      </div>
      <div className="flex gap-4">
        <aside className="w-72 shrink-0 resize-x overflow-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-3">
          <Tree
            refreshKey={refreshKey}
            onSelectFile={(path) => void openFile(path)}
            selected={selection}
            onToggleSelect={toggleSelect}
          />
        </aside>
        <section className="min-w-0 flex-1">
          {open ? (
            <div className="space-y-2">
              <nav aria-label="breadcrumbs" className="text-xs text-slate-500">
                {crumbs.map((part, i) => (
                  <span key={`${part}-${String(i)}`}>
                    {i > 0 && <span className="mx-1">/</span>}
                    {part}
                  </span>
                ))}
              </nav>
              {mode === 'preview' ? (
                <Preview
                  path={open.path}
                  content={open.content}
                  onEdit={() => setMode('edit')}
                />
              ) : (
                <Editor
                  path={open.path}
                  initialContent={open.content}
                  mtime={open.mtime}
                  onSaved={() => {
                    void openFile(open.path)
                    refresh()
                  }}
                  onReload={() => void openFile(open.path)}
                />
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-slate-500">
              Select a file to preview it.
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
