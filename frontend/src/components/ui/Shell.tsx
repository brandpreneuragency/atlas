import type { ReactNode } from 'react'

import { KillSwitch } from './KillSwitch'
import { Nav } from './Nav'

type ShellProps = {
  children: ReactNode
}

export function Shell({ children }: ShellProps) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex min-h-screen">
        <aside className="w-64 border-r border-slate-800 bg-slate-950/95 p-5">
          <div className="mb-8">
            <p className="text-xs uppercase tracking-[0.35em] text-cyan-300">ATLAS</p>
            <h1 className="mt-2 text-2xl font-semibold">Control</h1>
          </div>
          <Nav />
        </aside>
        <main className="flex-1">
          <header className="flex items-center justify-between border-b border-slate-800 px-8 py-4">
            <p className="text-sm text-slate-400">Single-user command plane</p>
            <div className="flex items-center gap-4 text-sm text-slate-300">
              <span className="inline-flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-emerald-400" /> Connected
              </span>
              <KillSwitch />
            </div>
          </header>
          <div className="p-8">{children}</div>
        </main>
      </div>
    </div>
  )
}
