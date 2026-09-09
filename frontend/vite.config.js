import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` proxies /api to the FastAPI container so the browser only ever
// talks to one origin — no CORS preflights, same relative URLs as production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': process.env.VITE_PROXY_TARGET || 'http://localhost:8000' },
  },
})
