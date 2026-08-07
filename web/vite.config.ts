import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Relative, so a built bundle works from a subpath (GitHub Pages) as well as
  // from the API's own origin.
  base: './',
  server: {
    // In development the viewer talks to the FastAPI service on 8000.
    proxy: {
      '/plans': 'http://127.0.0.1:8000',
      '/jobs': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
