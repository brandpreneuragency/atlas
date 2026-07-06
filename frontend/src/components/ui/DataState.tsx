import type { ReactNode } from 'react'

type DataStateProps = {
  loading: boolean
  error: string | null
  empty: string
  isEmpty?: boolean
  onRetry: () => void
  children: ReactNode
}

/** Shared loading-skeleton / empty / error-with-retry wrapper for data pages. */
export function DataState({ loading, error, empty, isEmpty = false, onRetry, children }: DataStateProps) {
  if (loading) {
    return (
      <div data-testid="loading-skeleton" className="mt-6 space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-2xl bg-slate-800/60" />
        ))}
      </div>
    )
  }
  if (error) {
    return (
      <div className="mt-6 rounded-2xl border border-rose-500/30 bg-rose-500/5 p-6 text-center">
        <p className="text-sm text-rose-300">{error}</p>
        <button
          type="button"
          className="mt-3 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          onClick={onRetry}
        >
          Retry
        </button>
      </div>
    )
  }
  if (isEmpty) {
    return <p className="mt-8 text-slate-500">{empty}</p>
  }
  return <>{children}</>
}
