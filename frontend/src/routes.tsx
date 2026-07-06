import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import type { RouteObject } from 'react-router-dom'

import { Shell } from './components/ui/Shell'
import { Login } from './pages/Login'
import { MissionControl } from './pages/MissionControl'

function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <div>
      <h1 className="text-3xl font-semibold">{title}</h1>
      <p className="mt-2 text-slate-400">Coming in {phase}</p>
    </div>
  )
}

function ShellPage({ children }: { children: ReactNode }) {
  return <Shell>{children}</Shell>
}

export const routes: RouteObject[] = [
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <ShellPage>
        <MissionControl />
      </ShellPage>
    ),
  },
  {
    path: '/automation',
    element: (
      <ShellPage>
        <Placeholder title="Automation" phase="Phase 6" />
      </ShellPage>
    ),
  },
  {
    path: '/files',
    element: (
      <ShellPage>
        <Placeholder title="Files" phase="Phase 3" />
      </ShellPage>
    ),
  },
  {
    path: '/agent',
    element: (
      <ShellPage>
        <Placeholder title="Agent" phase="Phase 2" />
      </ShellPage>
    ),
  },
  {
    path: '/models',
    element: (
      <ShellPage>
        <Placeholder title="Models" phase="Phase 4" />
      </ShellPage>
    ),
  },
  {
    path: '/inbox',
    element: (
      <ShellPage>
        <Placeholder title="Inbox" phase="Phase 7" />
      </ShellPage>
    ),
  },
  {
    path: '/settings',
    element: (
      <ShellPage>
        <Placeholder title="Settings" phase="Phase 8" />
      </ShellPage>
    ),
  },
  { path: '*', element: <Navigate to="/" replace /> },
]
