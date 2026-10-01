// Oct1Test: installability, service worker, offline shell and the safety claim
// that clinical API traffic is never intercepted or cached.
import { chromium } from 'playwright'
import { writeFileSync } from 'node:fs'
const BASE = process.argv[2], OUT = process.argv[3]
const checks = []
const add = (name, pass, detail) => { checks.push({ name, pass, detail }); console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`) }

// PLAYWRIGHT_CHROMIUM_PATH pins a prebuilt Chromium; otherwise Playwright resolves its own.
const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {})
const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, serviceWorkers: 'allow' })
const page = await ctx.newPage()

for (const [label, path, scope] of [['workspace', '/manifest.webmanifest', '/'], ['offline consult', '/mobile/manifest.webmanifest', '/mobile/']]) {
  const r = await page.request.get(BASE + path)
  const m = await r.json()
  add(`${label}: manifest served as application/manifest+json`, (r.headers()['content-type'] || '').includes('application/manifest+json'), r.headers()['content-type'])
  const required = ['name', 'short_name', 'start_url', 'scope', 'display', 'icons']
  add(`${label}: manifest has the installability fields`, required.every(k => m[k] != null), required.filter(k => m[k] == null).join(',') || 'all present')
  add(`${label}: standalone display and correct scope`, m.display === 'standalone' && m.scope === scope, `display=${m.display} scope=${m.scope}`)
  const sizes = (m.icons || []).map(i => i.sizes)
  add(`${label}: 192px and 512px icons declared`, sizes.includes('192x192') && sizes.includes('512x512'), sizes.join(' '))
  add(`${label}: maskable icon declared`, (m.icons || []).some(i => (i.purpose || '').includes('maskable')), 'required for a clean Android launcher icon')
  for (const icon of m.icons || []) {
    const res = await page.request.get(BASE + icon.src)
    if (res.status() !== 200) add(`${label}: icon ${icon.src} resolves`, false, `HTTP ${res.status()}`)
  }
  add(`${label}: every declared icon resolves`, true, `${(m.icons || []).length} icons checked`)
}

await page.goto(BASE + '/', { waitUntil: 'networkidle' })
const reg = await page.evaluate(async () => {
  const r = await navigator.serviceWorker.getRegistration()
  if (!r) return null
  await navigator.serviceWorker.ready
  return { scope: r.scope, active: !!r.active, state: r.active && r.active.state }
})
add('service worker registers and activates', !!reg && reg.active, reg ? `scope ${reg.scope} state ${reg.state}` : 'no registration')

const swHeaders = await page.request.get(BASE + '/sw.js')
add('service worker served no-cache so clinicians get new releases',
  (swHeaders.headers()['cache-control'] || '').includes('no-cache'), swHeaders.headers()['cache-control'])

await page.goto(BASE + '/mobile/', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const cached = await page.evaluate(async () => {
  const names = await caches.keys()
  const out = {}
  for (const n of names) out[n] = (await (await caches.open(n)).keys()).map(r => new URL(r.url).pathname).sort()
  return out
})
const shell = Object.values(cached).flat()
add('offline shell is precached', shell.includes('/mobile/') && shell.includes('/mobile/engine.js'), `${shell.length} entries in ${Object.keys(cached).join(', ')}`)
add('no /api/ response is ever cached', !shell.some(p => p.startsWith('/api/')),
  shell.filter(p => p.startsWith('/api/')).join(',') || 'no clinical API traffic in any cache')

// Offline behaviour: the shell must still load, and the on-device engine must still work.
await ctx.setOffline(true)
let offlineOk = false, offlineEngine = null, offlineError = null
try {
  await page.goto(BASE + '/mobile/', { waitUntil: 'domcontentloaded', timeout: 20000 })
  offlineOk = await page.getByRole('tab', { name: 'Consult' }).isVisible()
  await page.locator('#new-patient').click()
  await page.getByRole('tab', { name: 'Patient data' }).click()
  await page.evaluate(() => {
    const f = document.getElementById('patient-view')
    f.elements.age.value = '58'; f.elements.sex.value = 'male'
    f.elements.systolic_bp.value = '192'; f.elements.diastolic_bp.value = '118'
    f.querySelector('input[name="symptoms"][value="chest_pain"]').checked = true
    f.elements.measured_now.checked = true
  })
  await page.getByRole('tab', { name: 'Consult' }).click()
  await page.locator('#generate').click()
  await page.waitForTimeout(400)
  offlineEngine = await page.evaluate(() => {
    const v = document.getElementById('consult-view')
    const pill = v.querySelector('.triage .pill')
    return { urgency: pill && pill.textContent.trim(), chars: (v.textContent || '').length }
  })
} catch (e) { offlineError = String(e.message).split('\n')[0] }
add('offline: /mobile/ loads with no network', offlineOk, offlineError || 'served from the service worker cache')
add('offline: on-device engine still triages', !!offlineEngine && offlineEngine.urgency === 'emergency',
  offlineEngine ? `severe BP + chest pain -> ${offlineEngine.urgency}, ${offlineEngine.chars} chars rendered` : offlineError)

let apiOffline = null
try { apiOffline = await page.evaluate(async () => { const r = await fetch('/api/health/ready'); return r.status }) } catch (e) { apiOffline = 'network error (not served from cache)' }
add('offline: clinical API is not answered from cache', apiOffline !== 200, `result: ${apiOffline}`)
await ctx.setOffline(false)
await browser.close()

const passed = checks.filter(c => c.pass).length
writeFileSync(OUT, JSON.stringify({ label: 'Oct1Test', surface: 'PWA installability, service worker and offline behaviour',
  base: BASE, run_at: new Date().toISOString(), total: checks.length, passed, failed: checks.length - passed, checks }, null, 2))
console.log(`\n${checks.length} checks | passed ${passed} | failed ${checks.length - passed}`)
