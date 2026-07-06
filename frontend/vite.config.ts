import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8700',
      '/hermes': 'http://localhost:8700',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
