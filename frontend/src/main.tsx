/**
 * Application entry point.
 *
 * Boot order matters:
 *
 * 1. `ensureCsrfCookie()` fires first and is deliberately **not awaited** before render. The
 *    cookie must exist before the first unsafe request; waiting for it would hold the whole app
 *    behind a round trip that nothing on the first paint needs. Every mutation awaits it too (see
 *    `features/auth/hooks.ts`), so the two together make a missing token impossible.
 * 2. `QueryClientProvider` wraps `AuthProvider`, because the session probe *is* a react-query query.
 * 3. `AuthProvider` sits above the router so both public and protected routes can read the session.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './app/router'
import { AuthProvider } from './features/auth/AuthProvider'
import { ToastProvider } from './components/toast/ToastProvider'
import { Toaster } from './components/ui/Toaster'
import { ensureCsrfCookie } from './lib/http'
import { queryClient } from './lib/queryClient'
import './styles/tokens.css'
import './styles/app.css'

// Step 1: prime the CSRF cookie. Failure is non-fatal and retried on the first mutation.
void ensureCsrfCookie()

const container = document.getElementById('root')
if (!container) throw new Error('Root container #root is missing from index.html')

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </BrowserRouter>
        <Toaster />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
)
