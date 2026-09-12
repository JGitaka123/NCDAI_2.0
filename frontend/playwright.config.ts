import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

export default defineConfig({
  testDir: './tests/browser',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: resolve(process.env.NCDAI_BROWSER_ARTIFACT_DIR || '../.runtime/browser', 'results.json') }], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.NCDAI_BROWSER_URL || 'http://127.0.0.1:5173',
    browserName: 'chromium',
    actionTimeout: 15_000,
    channel: process.env.NCDAI_BROWSER_CHANNEL || undefined,
    viewport: { width: 1366, height: 900 },
    // Traces may retain typed credentials, so deliberately keep them disabled.
    trace: 'off',
    screenshot: 'only-on-failure',
    video: 'off',
  },
})
