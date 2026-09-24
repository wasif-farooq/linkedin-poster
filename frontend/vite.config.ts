import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Python API (`uv run linkedin-poster serve`) runs on :8000; in dev, /api is proxied to it.
const API_URL = process.env.API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5180, // 5173 is often taken by other Vite apps
    strictPort: false,
    proxy: {
      '/api': { target: API_URL, changeOrigin: true },
    },
  },
})
