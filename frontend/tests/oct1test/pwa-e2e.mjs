// Oct1Test: drives the deployed PWA workspace bundle through the complete
// clinical workflow once per case, against a real NCDAI API and PostgreSQL.
import { chromium } from 'playwright'
import { readFileSync, writeFileSync } from 'node:fs'

const BASE = process.argv[2], OUT = process.argv[3]
const ROOT = new URL('../../..', import.meta.url).pathname.replace(/\/$/, '')
const access = JSON.parse(readFileSync(`${ROOT}/.runtime/demo-access.json`))
const catalogue = Object.fromEntries(JSON.parse(readFileSync(`${ROOT}/tests/cases/clinical_cases.json`)).cases.map(c => [c.id, c]))
const backend = JSON.parse(readFileSync(`${ROOT}/docs/test-results/Oct1Test.json`))

const SYMPTOM = { chest_pain: 'Chest pain', breathlessness: 'Breathlessness', neurological_deficit: 'New neurological deficit',
  confusion: 'Confusion', seizure: 'Seizure', severe_headache: 'Severe headache', visual_disturbance: 'Visual disturbance',
  vomiting: 'Vomiting', dehydration: 'Dehydration', foot_ulcer: 'Foot ulcer', hypoglycemia_symptoms: 'Hypoglycaemia symptoms',
  wheeze: 'Wheeze', hemoptysis: 'Coughing blood', unexplained_weight_loss: 'Unexplained weight loss',
  persistent_cough: 'Persistent cough', breast_lump: 'Breast lump', abnormal_bleeding: 'Abnormal bleeding' }
const HISTORY = { known_hypertension: 'Known hypertension', known_diabetes: 'Known diabetes', known_asthma: 'Known asthma',
  known_copd: 'Known COPD', known_ckd: 'Known chronic kidney disease', known_cancer: 'Known cancer' }

// PLAYWRIGHT_CHROMIUM_PATH pins a prebuilt Chromium; otherwise Playwright resolves its own.
const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {})
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } })
const page = await ctx.newPage()
const consoleErrors = []
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()) })
page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message))

await page.goto(BASE + '/')
await page.getByLabel('Email address').fill(access.email)
await page.getByLabel('Password', { exact: true }).fill(access.password)
await page.getByRole('button', { name: 'Sign in', exact: true }).click()
await page.getByRole('heading', { name: 'A clearer view of care.' }).waitFor({ timeout: 20000 })
console.log('signed in\n')

async function navigate(name) {
  const toggle = page.getByRole('button', { name: 'Open navigation', exact: true })
  if (await toggle.isVisible()) await toggle.click()
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name, exact: true }).click()
}
async function section(text) {
  const s = page.locator('summary').filter({ hasText: text })
  if (await s.count()) { const open = await s.evaluate(e => e.parentElement.hasAttribute('open')); if (!open) await s.click() }
}

const rows = []
const started = new Date().toISOString()
for (const row of backend.cases) {
  const c = catalogue[row.id], d = c.data
  const t0 = Date.now()
  const record = { id: row.id, domain: row.domain, title: row.title, backend_urgency: row.urgency, backend_rules: [...row.rules].sort() }
  try {
    await navigate('Patients')
    await page.getByRole('button', { name: 'Register patient', exact: true }).click()
    await page.getByRole('button', { name: 'Create patient record' }).click()
    await page.getByLabel('Record ID', { exact: true }).fill(`OCT1UI-${row.id}`)
    await page.getByLabel('Given name', { exact: true }).fill('Synthetic')
    await page.getByLabel('Family name', { exact: true }).fill(`Oct1${row.id.replace('-', '')}`)
    const year = new Date().getUTCFullYear() - c.age
    await page.getByLabel(/^Date of birth/).fill(`${year}-06-15`)
    await page.getByLabel('Sex recorded').selectOption(c.sex)
    await page.getByRole('button', { name: 'Create patient record' }).click()
    await page.getByRole('button', { name: 'Start first encounter' }).click()

    const setNum = async (label, value) => { if (value != null) await page.getByLabel(label, { exact: true }).fill(String(value)) }
    await setNum('Systolic BP (mmHg)', d.systolic_bp)
    await setNum('Diastolic BP (mmHg)', d.diastolic_bp)
    await setNum('Pulse (beats/min)', d.pulse)
    await setNum('Oxygen saturation (%)', d.oxygen_saturation)
    await setNum('Respiratory rate (breaths/min)', d.respiratory_rate)
    await page.getByLabel(/^Measurements observed at/).fill(new Date().toISOString().slice(0, 16))
    for (const s of d.symptoms || []) await page.getByLabel(SYMPTOM[s], { exact: true }).check()
    if (d.symptoms_reviewed) await page.getByLabel(/^Symptom assessment completed/).check()

    await section('NCD history & context')
    for (const [key, label] of Object.entries(HISTORY)) if (d[key] != null) await page.getByLabel(label).selectOption(String(d[key]))
    if (d.pregnancy_status != null) await page.getByLabel('Pregnancy status').selectOption(d.pregnancy_status)
    if (d.tobacco_use != null) await page.getByLabel('Tobacco use').selectOption(d.tobacco_use)

    await section('Laboratory results')
    if (d.glucose_unit) await page.getByLabel('Glucose unit').selectOption(d.glucose_unit)
    await setNum('HbA1c (%)', d.hba1c)
    await setNum(`Blood glucose (${d.glucose_unit || 'mmol/L'})`, d.glucose)
    await setNum('eGFR (mL/min/1.73 m²)', d.egfr)
    await setNum('Potassium (mmol/L)', d.potassium)

    await section('Medicines & allergies')
    const meds = d.medications || []
    for (let i = 0; i < meds.length; i++) {
      await page.getByRole('button', { name: 'Add medicine', exact: true }).click()
      await page.getByLabel(`Medicine ${i + 1}`, { exact: true }).fill(meds[i].name || meds[i].code)
      if (meds[i].dose != null) await page.getByLabel('Dose', { exact: true }).nth(i).fill(String(meds[i].dose))
    }
    const allergies = (d.allergies || []).map(a => typeof a === 'string' ? a : (a.substance || JSON.stringify(a)))
    if (allergies.length) await page.getByLabel('Allergies and reactions').fill(allergies.join('\n'))
    if (d.medications_reviewed) await page.getByLabel(/^Medication list reviewed/).check()
    if (d.allergies_reviewed) await page.getByLabel(/^Allergy status reviewed/).check()
    if (d.adherence != null) await page.getByLabel('Medicine adherence').selectOption(d.adherence)
    if (d.medicine_availability != null) await page.getByLabel('Medicine availability').selectOption(d.medicine_availability)
    if (d.notes) { await section('Consultation notes'); await page.getByLabel('Clinical notes').fill(String(d.notes)) }

    await page.getByRole('button', { name: 'Assess & review', exact: true }).click()
    const banner = page.locator('[class*="urgency-"]').first()
    await banner.waitFor({ timeout: 20000 })
    const uiUrgency = await banner.evaluate(e => (String(e.className).match(/urgency-([a-z]+)/) || [])[1] || null)

    const cards = page.locator('article.recommendation')
    const count = await cards.count()
    let evidenceLinks = 0
    for (const card of await cards.all()) {
      await card.locator('summary').first().click()
      evidenceLinks += await card.locator('.evidence-list a').count()
      await card.getByRole('radio', { name: 'Accept', exact: true }).check()
    }
    await page.getByLabel('Overall review note (optional)').fill(`Oct1Test ${row.id}: every evidence-linked action reviewed.`)
    await page.getByRole('button', { name: 'Record review & lock encounter' }).click()
    await page.getByText('Clinician review recorded.', { exact: true }).waitFor({ timeout: 20000 })
    const locked = await page.getByRole('radio', { name: 'Accept', exact: true }).first().isDisabled()

    Object.assign(record, { pwa_urgency: uiUrgency, urgency_match: uiUrgency === row.urgency,
      recommendations: count, evidence_links: evidenceLinks, locked_after_review: locked,
      ms: Date.now() - t0, status: (uiUrgency === row.urgency && count > 0 && evidenceLinks > 0 && locked) ? 'passed' : 'failed' })
  } catch (error) {
    Object.assign(record, { status: 'failed', error: String(error.message || error).split('\n')[0], ms: Date.now() - t0 })
  }
  rows.push(record)
  process.stdout.write(`${record.id} ${String(record.domain).padEnd(15)} urgency ${String(record.pwa_urgency).padEnd(9)} vs ${String(record.backend_urgency).padEnd(9)} recs=${record.recommendations ?? '-'} evidence=${record.evidence_links ?? '-'} locked=${record.locked_after_review ?? '-'} ${record.status}${record.error ? ' :: ' + record.error : ''}\n`)
}
await browser.close()

const passed = rows.filter(r => r.status === 'passed').length
writeFileSync(OUT, JSON.stringify({ label: 'Oct1Test', surface: 'NCDAI 2.0 installable clinical workspace (PWA) UI',
  base: BASE, frontend: 'deployed production bundle', api: 'NCDAI backend at deployed commit', database: 'PostgreSQL 16.14 (local, synthetic)',
  started_at: started, completed_at: new Date().toISOString(), total: rows.length, passed, failed: rows.length - passed,
  urgency_matches: rows.filter(r => r.urgency_match).length, console_errors: consoleErrors, cases: rows }, null, 2))
console.log(`\n${rows.length} cases | passed ${passed} | urgency ${rows.filter(r => r.urgency_match).length}/${rows.length} | console errors ${consoleErrors.length}`)
