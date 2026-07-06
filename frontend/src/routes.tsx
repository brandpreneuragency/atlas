import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import type { RouteObject } from 'react-router-dom'

import { Shell } from './components/ui/Shell'
import { Agent } from './pages/Agent'
import { Automation } from './pages/Automation'
import { Files } from './pages/Files'
import { Inbox } from './pages/Inbox'
import { Review } from './pages/Review'
import { Models } from './pages/Models'
import { Settings } from './pages/Settings'
import { Login } from './pages/Login'
import { MissionControl } from './pages/MissionControl'
import { SessionDetail } from './pages/SessionDetail'
import { Sessions } from './pages/Sessions'
import { RunDetail } from './pages/RunDetail'
import { WorkflowEditor } from './pages/WorkflowEditor'

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
        <Automation />
      </ShellPage>
    ),
  },
  {
    path: '/automation/workflows/:id',
    element: (
      <ShellPage>
        <WorkflowEditor />
      </ShellPage>
    ),
  },
  {
    path: '/automation/runs/:id',
    element: (
      <ShellPage>
        <RunDetail />
      </ShellPage>
    ),
  },
  {
    path: '/files',
    element: (
      <ShellPage>
        <Files />
      </ShellPage>
    ),
  },
  {
    path: '/agent',
    element: (
      <ShellPage>
        <Agent />
      </ShellPage>
    ),
  },
  {
    path: '/sessions',
    element: (
      <ShellPage>
        <Sessions />
      </ShellPage>
    ),
  },
  {
    path: '/sessions/:sid',
    element: (
      <ShellPage>
        <SessionDetail />
      </ShellPage>
    ),
  },
  {
    path: '/models',
    element: (
      <ShellPage>
        <Models />
      </ShellPage>
    ),
  },
  {
    path: '/inbox',
    element: (
      <ShellPage>
        <Inbox />
      </ShellPage>
    ),
  },
  {
    path: '/review',
    element: (
      <ShellPage>
        <Review />
      </ShellPage>
    ),
  },
  {
    path: '/settings',
    element: (
      <ShellPage>
        <Settings />
      </ShellPage>
    ),
  },
  { path: '*', element: <Navigate to="/" replace /> },
]
