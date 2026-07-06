import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

/** Recoverable route-level error boundary (PHASE_8 Task 8.3). */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('route error boundary caught:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="m-8 rounded-2xl border border-rose-500/30 bg-rose-500/5 p-8 text-center">
          <h2 className="text-lg font-medium text-rose-300">Something went wrong</h2>
          <p className="mt-2 text-sm text-slate-400">{this.state.error.message}</p>
          <button
            type="button"
            className="mt-4 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
