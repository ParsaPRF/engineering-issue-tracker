import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies the API so the browser sees one origin (127.0.0.1:5173).
// That is what makes the session cookie work at all: no CORS, no SameSite=None,
// no third-party-cookie policy in the way. `changeOrigin: false` keeps the Host
// header as the frontend's, which Django's CSRF trusted-origins check accepts for
// same-origin classification.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
      '/media': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Split the framework and the data layer out of the app bundle. The app code is small and
        // changes often; these two chunks do not, so a deploy only invalidates the app chunk.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          data: ['@tanstack/react-query', 'react-hook-form', 'zod', '@hookform/resolvers'],
        },
      },
    },
  },
})
