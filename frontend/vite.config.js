import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_API_TARGET || 'http://localhost:8010'
  const wsUrl      = backendUrl.replace(/^http/, 'ws')

  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_PORT) || 5173,
      proxy: {
        '/api': { target: backendUrl, ws: true, changeOrigin: true },
        '/ws':  { target: wsUrl,      ws: true },
      },
    },
    define: {
      __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
    },
  }
})
