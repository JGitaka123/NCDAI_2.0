import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

// Run explicitly with provisioned, separate fictional clinician/consultant accounts.
const accessPath = process.env.NCDAI_CONSULTANT_BROWSER_ACCESS
test.skip(!accessPath, 'Separate fictional consultant verification accounts are required')
const access = accessPath ? JSON.parse(readFileSync(resolve(accessPath), 'utf8')) : null
const audits: object[] = []
async function login(page: Page, role: 'clinician' | 'supervisor') {
  await page.goto('/')
  await page.getByLabel('Email address').fill(access[role].email)
  await page.getByLabel('Password', { exact: true }).fill(access[role].password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'A clearer view of care.' })).toBeVisible()
}
async function audit(page: Page, label: string) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()
  audits.push({ label, viewport: page.viewportSize(), violations: result.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target) })) })
  const dir = resolve(process.env.NCDAI_BROWSER_ARTIFACT_DIR || '../.runtime/consultant-browser')
  mkdirSync(dir, { recursive: true })
  writeFileSync(resolve(dir, `${label}-axe.json`), JSON.stringify({ label, viewport: page.viewportSize(), violations: result.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => ({ target: n.target, failureSummary: n.failureSummary })) })) }, null, 2))
  expect(result.violations.map(v => v.id)).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

for (const viewport of [{ name: 'desktop', width: 1366, height: 900 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`Independent consultant handoff and closure — ${viewport.name}`, async ({ page, browser }) => {
    test.setTimeout(180_000)
    await page.setViewportSize(viewport)
    await login(page, 'clinician')
    const session = await (await page.request.get('/api/auth/session')).json()
    expect(session.user.clinical_testing).toBe(false)
    const headers = { 'X-CSRF-Token': session.csrf_token, Origin: access.url }
    const run = `Consult${Date.now()}`
    const request = async (method: string, path: string, data?: unknown, expected = 200) => {
      const response = await page.request.fetch('/api' + path, { method, headers, data })
      expect(response.status()).toBe(expected)
      return response.status() === 204 ? null : response.json()
    }
    const patient = await request('POST', '/patients', { external_id: run, given_name: 'Fictional', family_name: run, date_of_birth: '1975-01-01', sex: 'male', synthetic: true }, 201)
    let encounter = await request('POST', '/encounters', { patient_id: patient.id, data: { systolic_bp: 154, diastolic_bp: 96, known_hypertension: 'yes', notes: 'Fictional consultant browser verification; no patient care.', observed_at: new Date().toISOString() } }, 201)
    encounter = await request('POST', `/encounters/${encounter.id}/assess`)
    const original = encounter.assessment
    if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) await page.getByRole('button', { name: 'Open navigation' }).click()
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Patients', exact: true }).click()
    await page.getByRole('button', { name: `Open Fictional ${run}`, exact: true }).click()
    await page.locator('.history-card').first().click()
    await page.getByRole('button', { name: 'Request consultant review', exact: true }).click()
    await page.getByRole('group', { name: 'Recommendations for a second opinion' }).getByRole('checkbox').first().check()
    const question = `Fictional ${run}: please independently review this recommendation.`
    await page.getByLabel('Reason for consultation').selectOption('disagreement')
    await page.getByLabel('Question and why you need review').fill(question)
    await page.getByLabel('Immediate action taken while awaiting advice').fill('Fictional rehearsal: local clinical reassessment and direct escalation remain available.')
    await audit(page, `${viewport.name}-request`)
    await page.getByRole('button', { name: 'Submit consultation', exact: true }).click()
    await expect(page.getByText(/Delivered to the consultant workspace/)).toBeVisible()
    const rows = await request('GET', `/consultations?encounter_id=${encounter.id}`)
    expect(rows).toHaveLength(1)
    const id = rows[0].id
    const other = await browser.newContext({ baseURL: access.url, viewport })
    const consultant = await other.newPage()
    try {
      await login(consultant, 'supervisor')
      expect((await consultant.goto('/consultant'))?.status()).toBe(200)
      await consultant.getByRole('button').filter({ hasText: question }).click()
      await expect(consultant.getByRole('heading', { name: 'Independent consultant response' })).toBeVisible()
      await consultant.getByText('Preserved clinical observations', { exact: true }).click()
      await expect(consultant.getByText('154 mmHg', { exact: true })).toBeVisible()
      await consultant.getByLabel('Agreement with selected recommendations').selectOption('partly_agree')
      await consultant.getByLabel('assessment', { exact: true }).fill('Fictional independent assessment: verify repeat observations and complete missing history.')
      await consultant.getByLabel('recommended action', { exact: true }).fill('Fictional advice: reassess with the responsible clinical team before taking action.')
      await consultant.getByLabel('rationale', { exact: true }).fill('The recorded snapshot is incomplete and requires clinician assessment in this fictional test.')
      await consultant.getByLabel('source references', { exact: true }).fill('Fictional engineering test; preserved evidence references checked, not a clinical endorsement.')
      await audit(consultant, `${viewport.name}-independent-response`)
      await consultant.getByRole('button', { name: 'Record consultant opinion', exact: true }).click()
      await expect(consultant.getByRole('heading', { name: 'Consultant opinion', exact: true })).toBeVisible()
      // Make the encounter newer than the preserved handoff; the closure must acknowledge this.
      await request('PATCH', `/encounters/${encounter.id}`, { expected_version: encounter.version, data: { ...encounter.data, systolic_bp: 150 } })
      await page.goto('/consultant')
      await page.getByRole('button').filter({ hasText: question }).click()
      await expect(page.getByText(/encounter has changed since this request/)).toBeVisible()
      await page.getByLabel('Response to consultant advice').selectOption('modified')
      await page.getByLabel('Actual action and reasons').fill('Fictional closure: current observations rechecked; consultant advice considered and action documented.')
      await page.getByLabel('I checked current findings and changes since this consultation snapshot.').check()
      await audit(page, `${viewport.name}-final-action`)
      await page.getByRole('button', { name: 'Record final action', exact: true }).click()
      await expect(page.getByRole('heading', { name: "Primary team's final action" })).toBeVisible()
      const detail = await request('GET', `/consultations/${id}`)
      expect(detail.status).toBe('closed')
      expect(detail.snapshot.assessment).toEqual(original)
      expect(detail.opinion.reviewer_id).toBe(access.supervisor.id)
      expect(detail.requested_by).toBe(access.clinician.id)
      expect(detail.disposition.snapshot_was_stale).toBe(true)
      const artifactDir = resolve(process.env.NCDAI_BROWSER_ARTIFACT_DIR || '../.runtime/consultant-browser')
      mkdirSync(artifactDir, { recursive: true })
      await page.screenshot({ path: resolve(artifactDir, `${viewport.name}-consultant-closed.png`), fullPage: true })
      if (await consultant.getByRole('button', { name: 'Open navigation' }).isVisible()) await consultant.getByRole('button', { name: 'Open navigation' }).click()
      await consultant.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Evaluation', exact: true }).click()
      await expect(consultant.getByRole('heading', { name: 'Consultation follow-through' })).toBeVisible()
      await expect(consultant.getByText('Consultant agreement', { exact: true })).toBeVisible()
      await audit(consultant, `${viewport.name}-evaluation`)
      await consultant.getByLabel('Fictional staff-rehearsal cases only').uncheck()
      await expect(consultant.getByText('Only real-patient clinical-testing episodes are included.')).toBeVisible()
      await expect(consultant.locator('.account-details > div').filter({ hasText: 'Requests' }).locator('dd')).toHaveText('0')
      await request('POST', '/auth/logout', undefined, 204)
      const consultantSession = await (await consultant.request.get('/api/auth/session')).json()
      const out = await consultant.request.post('/api/auth/logout', { headers: { Origin: access.url, 'X-CSRF-Token': consultantSession.csrf_token } })
      expect(out.status()).toBe(204)
    } finally { await other.close() }
  })
}

test.afterAll(() => {
  const dir = resolve(process.env.NCDAI_BROWSER_ARTIFACT_DIR || '../.runtime/consultant-browser')
  mkdirSync(dir, { recursive: true })
  writeFileSync(resolve(dir, 'consultant-axe.json'), JSON.stringify({ checked_at: new Date().toISOString(), audits }, null, 2))
})
