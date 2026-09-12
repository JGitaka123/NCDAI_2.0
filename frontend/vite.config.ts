import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', proxy: { '/api': { target: 'http://127.0.0.1:8010', changeOrigin: false } } },
  preview: { host: '127.0.0.1' },
  test: { include: ['src/**/*.test.{ts,tsx}'], environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], restoreMocks: true, pool: 'threads', maxWorkers: 1, fileParallelism: false, testTimeout: 15000 },
})
