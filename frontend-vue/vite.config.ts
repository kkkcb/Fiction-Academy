import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端端口可用环境变量覆盖：VITE_API_PROXY_TARGET=http://127.0.0.1:8000
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
