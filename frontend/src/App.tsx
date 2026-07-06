import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useRoutes } from 'react-router-dom'

import { routes } from './routes'

const queryClient = new QueryClient()

function App() {
  const element = useRoutes(routes)
  return <QueryClientProvider client={queryClient}>{element}</QueryClientProvider>
}

export default App
