import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// API calls to /api are forwarded to the FastAPI backend during development.
// Set VITE_BACKEND_URL (e.g. in frontend/.env) if the backend runs on another port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
