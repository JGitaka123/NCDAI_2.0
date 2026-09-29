// Read-only check of a live deployment at phone width. Never signs in or submits forms.
import { chromium } from '@playwright/test'

const site = (process.argv[2] || 'https://ncdai-2.vercel.app').replace(/\/$/, '')
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
const problems = []

async function visit(path, check) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  page.on('console', (m) => {
    // A 401 from the session probe is the expected signed-out state, not a fault.
    if (m.type() === 'error' && !/status of 401/.test(m.text())) problems.push(`${path} console: ${m.text()}`)
  })
  page.on('pageerror', (e) => problems.push(`${path} error: ${e.message}`))
  await page.goto(site + path, { waitUntil: 'networkidle' })
  await check(page)
  console.log(`${path} ok`)
  await page.close()
}

// The offline consult loads the fictional example patient on start.
await visit('/mobile/', async (page) => {
  await page.getByText('Consultant synthesis').first().waitFor({ timeout: 15000 })
})
// Main app: only confirm the sign-in form renders.
await visit('/', async (page) => {
  await page.locator('input[type="password"]').first().waitFor({ timeout: 15000 })
})
await browser.close()

if (problems.length) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log('No console errors or CSP violations.')
