import type { Plugin } from 'vite'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const UTF8_TEXT_LIKE_MIME = /^(text\/|application\/(javascript|json|xml)|image\/svg\+xml)/i

function withUtf8Charset(contentType: string): string {
  if (/charset=/i.test(contentType)) return contentType
  const mime = contentType.split(';', 1)[0]?.trim() ?? ''
  if (!UTF8_TEXT_LIKE_MIME.test(mime)) return contentType
  return `${contentType}; charset=utf-8`
}

function enforceUtf8Charset(): Plugin {
  type HeaderValue = string | number | readonly string[]
  const patchResponseHeader = (res: { setHeader: (name: string, value: HeaderValue) => unknown }) => {
    const originalSetHeader = res.setHeader.bind(res)
    res.setHeader = (name: string, value: HeaderValue) => {
      if (name.toLowerCase() === 'content-type' && typeof value === 'string') {
        return originalSetHeader(name, withUtf8Charset(value))
      }
      return originalSetHeader(name, value)
    }
  }

  return {
    name: 'enforce-utf8-charset',
    configureServer(server) {
      server.middlewares.use((_req, res, next) => {
        patchResponseHeader(res)
        next()
      })
    },
    configurePreviewServer(server) {
      server.middlewares.use((_req, res, next) => {
        patchResponseHeader(res)
        next()
      })
    }
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue(), enforceUtf8Charset()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      // 浏览器请求发到 Vite 时：/api/* 应转发到 Spring Boot（8080），不是 ai-engine（8001）
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  }
})
