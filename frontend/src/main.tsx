import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles.css'
import { applyTheme, storedTheme } from './lib/theme'
import { SessionBoundary } from './components/session-boundary'
applyTheme(storedTheme())
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15000, refetchOnWindowFocus: false }, mutations: { retry: false } } })
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><SessionBoundary><BrowserRouter><App/></BrowserRouter></SessionBoundary></QueryClientProvider></React.StrictMode>)
