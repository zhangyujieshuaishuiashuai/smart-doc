import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000', // 👈 关键修改：必须是 8000
        changeOrigin: true,
        // 如果后端接口没有 /api 前缀，可能需要 rewrite，但在我们的 main.py 里定义的就是 /api，所以不需要 rewrite
      }
    }
  }
})