import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.BACKEND_PORT ? parseInt(process.env.BACKEND_PORT, 10) : 8000
const frontendPort = process.env.FRONTEND_PORT ? parseInt(process.env.FRONTEND_PORT, 10) : 5173

export default defineConfig({
  plugins: [react()],
  server: {
    port: frontendPort,
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
        // Remove the /api prefix when forwarding if backend doesn't expect it
        // Here backend has no /api prefix, so we rewrite to root
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
