import { create } from 'zustand'

type SessionState = {
  authenticated: boolean
  setAuthenticated: (authenticated: boolean) => void
}

export const useSession = create<SessionState>((set) => ({
  authenticated: false,
  setAuthenticated: (authenticated) => set({ authenticated }),
}))
