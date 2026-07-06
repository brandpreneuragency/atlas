import { useCallback, useEffect, useState } from 'react'

import { api } from '../../api/client'

export type TreeEntry = {
  name: string
  is_dir: boolean
  size: number
  mtime: number
}

function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name
}

function DirEntries({
  path,
  refreshKey,
  onSelectFile,
  selected,
  onToggleSelect,
}: {
  path: string
  refreshKey: number
  onSelectFile: (path: string) => void
  selected: Set<string>
  onToggleSelect: (path: string) => void
}) {
  const [entries, setEntries] = useState<TreeEntry[] | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    api
      .get<{ entries: TreeEntry[] }>(
        `/api/files/tree?path=${encodeURIComponent(path)}`,
      )
      .then((body) => {
        if (!cancelled) setEntries(body.entries)
      })
      .catch(() => {
        if (!cancelled) setEntries([])
      })
    return () => {
      cancelled = true
    }
  }, [path, refreshKey])

  const toggleDir = useCallback((full: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(full)) next.delete(full)
      else next.add(full)
      return next
    })
  }, [])

  if (entries === null) {
    return <div className="px-2 py-1 text-xs text-slate-500">Loading…</div>
  }
  return (
    <ul className="space-y-0.5">
      {entries.map((entry) => {
        const full = joinPath(path, entry.name)
        const isOpen = expanded.has(full)
        return (
          <li key={full}>
            <div className="group flex items-center gap-1.5 rounded px-1 py-0.5 hover:bg-slate-800/60">
              <input
                type="checkbox"
                aria-label={`select ${entry.name}`}
                checked={selected.has(full)}
                onChange={() => onToggleSelect(full)}
                className="h-3.5 w-3.5 accent-cyan-500"
              />
              <button
                type="button"
                className="flex flex-1 items-center gap-1.5 truncate text-left text-sm text-slate-200"
                onClick={() =>
                  entry.is_dir ? toggleDir(full) : onSelectFile(full)
                }
              >
                <span aria-hidden>{entry.is_dir ? (isOpen ? '📂' : '📁') : '📄'}</span>
                <span className="truncate">{entry.name}</span>
              </button>
            </div>
            {entry.is_dir && isOpen && (
              <div className="ml-5 border-l border-slate-800 pl-2">
                <DirEntries
                  path={full}
                  refreshKey={refreshKey}
                  onSelectFile={onSelectFile}
                  selected={selected}
                  onToggleSelect={onToggleSelect}
                />
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export function Tree(props: {
  refreshKey: number
  onSelectFile: (path: string) => void
  selected: Set<string>
  onToggleSelect: (path: string) => void
}) {
  return (
    <nav aria-label="file tree" className="text-sm">
      <DirEntries path="" {...props} />
    </nav>
  )
}
