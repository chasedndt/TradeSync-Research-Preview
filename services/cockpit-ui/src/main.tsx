import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ExecutionProvider } from './context'
import { registerServiceWorker } from './pwa/browserPush'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchInterval: 5000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ExecutionProvider>
          <App />
        </ExecutionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)

// The service worker shows notifications and one offline page. It caches no dashboard
// data, and a browser that refuses to register it loses nothing else. See public/sw.js.
void registerServiceWorker()
