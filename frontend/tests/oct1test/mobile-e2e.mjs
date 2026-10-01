// Oct1Test: drives the deployed NCDAI Consult UI once per case and compares the
// rendered triage with the backend's persisted assessment for the same case.
import { chromium } from 'playwright'
import { readFileSync, writeFileSync } from 'node:fs'

const BASE = process.argv[2], OUT = process.argv[3]
const ROOT = new URL('../../..', import.meta.url).pathname.replace(/\/$/, '')
const catalogue = Object.fromEntries(JSON.parse(readFileSync(`${ROOT}/tests/cases/clinical_cases.json`)).cases.map(c => [c.id, c]))
const backend = JSON.parse(readFileSync(`${ROOT}/docs/test-results/Oct1Test.json`))
const selected = backend.cases.map(c => ({ id: c.id, urgency: c.urgency, rules: c.rules, domain: c.domain, title: c.title }))

const NUMERIC = ['systolic_bp','diastolic_bp','repeat_systolic_bp','repeat_diastolic_bp','pulse','oxygen_saturation','respiratory_rate','weight_kg','height_cm','waist_cm',
  'hba1c','glucose','creatinine_umol','egfr','urine_acr_mg_mmol','potassium','total_cholesterol_mmol','hdl_mmol','ldl_mmol','hemoglobin_g_dl',
  'hypoglycaemia_episodes_3m','exacerbations_past_year','reliever_use_per_week']
const SELECTS = ['pregnancy_status','glucose_context','tobacco_use','adherence','eye_screen','foot_exam']
const HISTORY = ['known_hypertension','known_diabetes','known_ckd','known_ascvd','prior_stroke_tia','known_heart_failure','known_atrial_fibrillation','known_asthma','known_copd','known_cancer','acutely_unwell','acute_kidney_injury']

// PLAYWRIGHT_CHROMIUM_PATH pins a prebuilt Chromium; otherwise Playwright resolves its own.
const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {})
const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } })
const page = await ctx.newPage()
const consoleErrors = []
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()) })
page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message))

const rows = []
for (const sel of selected) {
  const c = catalogue[sel.id]
  const data = { ...c.data }
  let conversion = null
  if (data.glucose_unit === 'mg/dL' && typeof data.glucose === 'number') {
    const before = data.glucose
    data.glucose = Math.round((data.glucose / 18.0182) * 100) / 100
    conversion = `glucose ${before} mg/dL entered as ${data.glucose} mmol/L (form is mmol/L only)`
  }
  const unsupported = ['medicine_availability', 'notes', 'dosing_requests'].filter(k => k in c.data)

  await page.goto(BASE + '/mobile/', { waitUntil: 'domcontentloaded' })
  // The app opens on a bundled example; New patient clears it, medicines included.
  await page.locator('#new-patient').click()
  await page.getByRole('tab', { name: 'Patient data' }).click()
  const residual = await page.locator('#medlist li').count()
  if (residual !== 0) throw new Error(`form not cleared for ${sel.id}: ${residual} medicines remain`)

  const filled = await page.evaluate(({ data, age, sex, NUMERIC, SELECTS, HISTORY }) => {
    const form = document.getElementById('patient-view')
    const set = (name, value) => { const el = form.elements[name]; if (!el) return false; el.value = String(value); return true }
    const missed = []
    if (!set('age', age)) missed.push('age')
    if (!set('sex', sex)) missed.push('sex')
    for (const k of NUMERIC) if (data[k] != null && !set(k, data[k])) missed.push(k)
    for (const k of SELECTS) if (data[k] != null && !set(k, data[k])) missed.push(k)
    if (data.dosing_context && data.dosing_context.frailty) set('frailty', data.dosing_context.frailty)
    for (const k of HISTORY) {
      const want = data[k] == null ? 'unknown' : String(data[k])
      const radio = form.querySelector(`input[name="${k}"][value="${want}"]`)
      if (radio) radio.checked = true; else if (data[k] != null) missed.push(k + '=' + want)
    }
    form.querySelectorAll('input[name="symptoms"]').forEach(el => { el.checked = false })
    for (const s of data.symptoms || []) {
      const box = form.querySelector(`input[name="symptoms"][value="${s}"]`)
      if (box) box.checked = true; else missed.push('symptom:' + s)
    }
    form.elements.allergies.value = (data.allergies || []).map(a => typeof a === 'string' ? a : (a.substance || JSON.stringify(a))).join('\n')
    for (const k of ['medications_reviewed', 'allergies_reviewed', 'symptoms_reviewed']) form.elements[k].checked = !!data[k]
    // The backend runner stamps observed_at = now for every case; ticking
    // "measurements taken today" is how the mobile form expresses the same thing.
    form.elements.measured_now.checked = true
    return { missed }
  }, { data, age: c.age, sex: c.sex, NUMERIC, SELECTS, HISTORY })

  // Medicines go through the app's own add-medicine control.
  for (const med of data.medications || []) {
    await page.locator('#med-name').fill(med.name || med.code)
    if (med.dose != null) await page.locator('#med-dose').fill(String(med.dose))
    await page.getByRole('button', { name: 'Add medicine', exact: true }).click()
  }
  const medCount = await page.locator('#medlist li').count()

  await page.evaluate(() => {
    // app.js holds a reference to the NCDAIEngine object and resolves .assess at
    // call time, so wrapping the property captures the real UI-driven call.
    const engine = self.NCDAIEngine
    if (!engine.__wrapped) {
      const original = engine.assess.bind(engine)
      engine.assess = function (data, age, sex) {
        const result = original(data, age, sex)
        window.__ncdaiCall = { data: JSON.parse(JSON.stringify(data)), age, sex,
          urgency: result.urgency, rules: result.recommendations.map(r => r.rule_id) }
        return result
      }
      engine.__wrapped = true
    }
    window.__ncdaiCall = null
  })
  await page.getByRole('tab', { name: 'Consult' }).click()
  await page.locator('#generate').click()
  await page.waitForTimeout(120)

  const ui = await page.evaluate(() => {
    const v = document.getElementById('consult-view')
    const pill = v.querySelector('.triage .pill')
    return {
      urgency: pill ? pill.textContent.trim() : null,
      headline: (v.querySelector('.triage h2') || {}).textContent || null,
      oneLiner: (v.querySelector('.card.lead h2') || {}).textContent || null,
      findings: [...v.querySelectorAll('.findings li strong')].map(e => e.textContent.trim()),
      problems: v.querySelectorAll('article.card.problem').length,
      derivedTiles: v.querySelectorAll('.tile').length,
      monitoringRows: v.querySelectorAll('table tbody tr').length,
      medicationReview: v.querySelectorAll('.review li').length,
      sourceLinks: v.querySelectorAll('.src a').length,
      summaryChars: ((v.querySelector('pre') || {}).textContent || '').length,
      error: !!v.querySelector('.notice.error'),
    }
  })

  const call = await page.evaluate(() => window.__ncdaiCall)
  const engineRules = call ? [...call.rules].sort() : null
  const backendRules = [...sel.rules].sort()
  const rulesMatch = engineRules !== null && JSON.stringify(engineRules) === JSON.stringify(backendRules)
  const urgencyMatch = ui.urgency === sel.urgency
  rows.push({ id: sel.id, domain: sel.domain, title: sel.title, backend_urgency: sel.urgency, mobile_urgency: ui.urgency,
    urgency_match: urgencyMatch, backend_rules: backendRules, mobile_rules: engineRules, rules_match: rulesMatch,
    collected_by_ui: call ? { age: call.age, sex: call.sex, data: call.data } : null,
    ui, fill_misses: filled.missed, medicines_entered: medCount,
    medicines_expected: (data.medications || []).length, conversion, unsupported_fields: unsupported,
    status: urgencyMatch && rulesMatch && !ui.error && ui.summaryChars > 0 && ui.problems > 0 ? 'passed' : 'failed' })
  process.stdout.write(`${sel.id} ${sel.domain.padEnd(15)} urgency ${String(ui.urgency).padEnd(9)} ${urgencyMatch ? 'ok' : 'MISMATCH'} | rules ${rulesMatch ? 'ok' : 'MISMATCH ' + JSON.stringify({ mobile: engineRules, backend: backendRules })} | problems=${ui.problems}\n`)
}
await browser.close()

const passed = rows.filter(r => r.status === 'passed').length
writeFileSync(OUT, JSON.stringify({ label: 'Oct1Test', surface: 'NCDAI Consult offline mobile app (/mobile/)',
  base: BASE, run_at: new Date().toISOString(), total: rows.length, passed, failed: rows.length - passed,
  urgency_matches: rows.filter(r => r.urgency_match).length, rule_matches: rows.filter(r => r.rules_match).length,
  console_errors: consoleErrors, cases: rows }, null, 2))
console.log(`\n${rows.length} cases | passed ${passed} | urgency ${rows.filter(r => r.urgency_match).length}/${rows.length} | rule sets ${rows.filter(r => r.rules_match).length}/${rows.length} | console errors ${consoleErrors.length}`)
