import { create } from 'zustand'

type SseStatus = 'connecting' | 'open' | 'closed'

type SessionState = {
  authenticated: boolean
  setAuthenticated: (authenticated: boolean) => void
  sseStatus: SseStatus
  setSseStatus: (sseStatus: SseStatus) => void
}

export const useSession = create<SessionState>((set) => ({
  authenticated: false,
  setAuthenticated: (authenticated) => set({ authenticated }),
  sseStatus: 'connecting',
  setSseStatus: (sseStatus) => set({ sseStatus }),
}))
