import type { ReactNode } from 'react'

export function ConfirmDialog({
  title,
  paths,
  children,
  confirmLabel = 'Confirm',
  onConfirm,
  onCancel,
}: {
  title: string
  paths: string[]
  children?: ReactNode
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
      <div
        role="dialog"
        aria-label={title}
        className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
        <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto text-sm text-slate-300">
          {paths.map((p) => (
            <li key={p} className="rounded bg-slate-950/60 px-2 py-1 font-mono">
              {p}
            </li>
          ))}
        </ul>
        {children}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-lg bg-cyan-500 px-3 py-1.5 text-sm font-medium text-slate-950"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
