import { useState } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import AssessmentReview, { planText } from '../AssessmentReview'
import ClinicalIntake from '../ClinicalIntake'
import Dashboard from '../Dashboard'
import { emptyClinicalData } from '../clinical'
import { api } from '../api'
import type { Encounter, Evidence, Recommendation, User } from '../types'

vi.mock('../api', () => ({ api: vi.fn(), message: (error: Error) => error.message }))
afterEach(() => vi.resetAllMocks())

const kenya: Evidence = { source_id: 'KENYA_HTN_STEPS', title: 'Kenya Ministry of Health: Protocols for Management of Selected NCDs at Primary Care Setting', url: 'https://health.go.ke/protocols.pdf#page=20', section: 'Hypertension treatment steps 1-4, printed page 11 (PDF page 20); target <140/90 mmHg', version: '2025' }
function rec(id: string, patch: Partial<Recommendation> = {}): Recommendation {
  return { id, rule_id: id, category: 'hypertension', severity: 'warning', title: `Title ${id}`, detail: 'Detail.', evidence: [kenya], ...patch }
}
const encounter = {
  id: 'encounter', patient_id: 'patient', status: 'draft', version: 4, data: emptyClinicalData(), created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z',
  assessment: {
    id: 'assessment', urgency: 'soon', summary: 'Review advised.', missing_data: [], warnings: ['Limited catalogue.'], model_info: { mode: 'deterministic_rules', status: 'review_required' },
    generated_at: '2026-01-01T12:00:00Z', evidence_version: 'v1', derived: { bmi: 33.8, bmi_category: 'obesity' },
    recommendations: [
      rec('CRITICAL_ONE', { severity: 'critical', title: 'Act on this now' }),
      rec('TX_HTN_START', { category: 'treatment', title: 'Consider starting antihypertensive treatment', basis: ['BP used for control: 164/100 mmHg'] }),
      rec('BP_HIGH'),
      rec('TOBACCO_SUPPORT', { severity: 'info' }),
    ],
  },
} as unknown as Encounter

function ReviewHarness() {
  const [record, setRecord] = useState(encounter)
  return <AssessmentReview encounter={record} onReviewed={setRecord} onUpdated={setRecord} onConflict={() => {}} />
}

it('groups recommendations, shows the basis and a numbered source link', async () => {
  render(<ReviewHarness />)
  expect(screen.getByRole('heading', { name: /Act now/ })).toBeVisible()
  const treatment = screen.getByRole('heading', { name: /Treatment options/ }).closest('section')!
  expect(within(treatment).getByRole('heading', { name: 'Consider starting antihypertensive treatment' })).toBeVisible()
  expect(within(treatment).getByText('BP used for control: 164/100 mmHg')).toBeVisible()
  const link = within(treatment).getByRole('link', { name: /Kenya MOH NCD Protocols/ })
  expect(link).toHaveAttribute('href', 'https://health.go.ke/protocols.pdf#page=20')
  expect(link).toHaveTextContent('p. 11')
  expect(screen.getAllByRole('link', { name: 'Reference 1' })[0]).toHaveAttribute('href', '#ref-1')
})

it('bulk-accepts only non-critical items and still requires a decision on critical ones', async () => {
  const user = userEvent.setup()
  render(<ReviewHarness />)
  await user.click(screen.getByRole('button', { name: 'Accept remaining non-critical (3)' }))
  expect(screen.queryByRole('button', { name: /Accept remaining/ })).toBeNull()
  expect(document.body.textContent).toContain('3 of 4 decided')
  await user.click(screen.getByRole('button', { name: 'Record review & lock encounter' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Choose a decision for “Act on this now”')
})

it('offers quick reasons that fill the required reason field', async () => {
  const user = userEvent.setup()
  render(<ReviewHarness />)
  const critical = screen.getByRole('heading', { name: 'Act on this now' }).closest('article')!
  await user.click(within(critical).getByRole('radio', { name: 'Defer' }))
  await user.click(within(critical).getByRole('button', { name: 'Awaiting results' }))
  expect(within(critical).getByLabelText('Reason for deferral (required)')).toHaveValue('Awaiting results')
})

it('records every decision including bulk-accepted ones', async () => {
  const user = userEvent.setup()
  vi.mocked(api).mockResolvedValue({ ...encounter, status: 'reviewed' })
  render(<ReviewHarness />)
  const critical = screen.getByRole('heading', { name: 'Act on this now' }).closest('article')!
  await user.click(within(critical).getByRole('radio', { name: 'Accept' }))
  await user.click(screen.getByRole('button', { name: 'Accept remaining non-critical (3)' }))
  await user.click(screen.getByRole('button', { name: 'Record review & lock encounter' }))
  const body = vi.mocked(api).mock.calls[0][1]!.body as { decisions: { recommendation_id: string; action: string }[] }
  expect(body.decisions).toHaveLength(4)
  expect(body.decisions.every(decision => decision.action === 'accept')).toBe(true)
})

function IntakeHarness() { const [data, setData] = useState(emptyClinicalData()); return <ClinicalIntake data={data} onChange={setData} disabled={false} /> }

it('calculates BMI from weight and height and captures lipids and fasting glucose', async () => {
  const user = userEvent.setup()
  render(<IntakeHarness />)
  expect(screen.getByText('BMI is calculated when weight and height are entered.')).toBeVisible()
  await user.type(screen.getByLabelText('Weight (kg)'), '92')
  await user.type(screen.getByLabelText('Height (cm)'), '165')
  expect(within(screen.getByRole('status')).getByText('33.8')).toBeVisible()
  expect(screen.getByText('Obesity')).toBeVisible()
  await user.selectOptions(screen.getByLabelText(/Glucose sample/), 'fasting')
  expect(screen.getByLabelText(`Fasting blood sugar (mmol/L)`)).toBeVisible()
  for (const label of ['Total cholesterol (mmol/L)', 'LDL cholesterol (mmol/L)', 'HDL cholesterol (mmol/L)', 'Triglycerides (mmol/L)']) expect(screen.getByLabelText(label)).toBeVisible()
})

const clinician: User = { id: 'u', email: 'c@example.test', display_name: 'Grace Wanjiru', role: 'clinician', facility_id: 'f', facility_name: 'Mary Help Hospital' }

it('lists open encounters most urgent first and opens the selected one', async () => {
  const user = userEvent.setup()
  const onOpenEncounter = vi.fn()
  vi.mocked(api).mockImplementation(async (path: string) => path === '/dashboard' ? {
    patients: 4, encounters: 6, reviewed: 2, open_referrals: 1, urgent_assessments: 1, drafts: 2,
    attention: [
      { encounter_id: 'e-routine', patient_id: 'p1', patient_name: 'Routine Patient', patient_external_id: 'MH-2', updated_at: '2026-01-02T09:00:00Z', stage: 'intake', urgency: null, recommendations: 0 },
      { encounter_id: 'e-urgent', patient_id: 'p2', patient_name: 'Urgent Patient', patient_external_id: 'MH-9', updated_at: '2026-01-01T09:00:00Z', stage: 'review', urgency: 'urgent', recommendations: 7 },
    ],
  } : [] as never)
  render(<Dashboard user={clinician} onPatients={() => {}} onReferrals={() => {}} onOpenEncounter={onOpenEncounter} />)
  const items = await screen.findAllByRole('listitem')
  expect(within(items[0]).getByText('Urgent Patient')).toBeVisible()
  expect(within(items[0]).getByText('Review 7 recommendations')).toBeVisible()
  await user.click(within(items[0]).getByRole('button'))
  expect(onOpenEncounter).toHaveBeenCalledWith(expect.objectContaining({ encounter_id: 'e-urgent' }))
})

const plan = { headline: '63-year-old woman with hypertension on 1 recorded medicine. Clinical priority: soon.', problems: [{ name: 'Hypertension', status: 'BP 158/96 mmHg: above target (<140/90)', tone: 'attention' as const }], medicines: [{ name: 'Amlodipine', dose: '5 mg once daily', class: 'Calcium channel blocker', note: 'below the Table 4 maximum of 10 mg' }], monitoring: [{ item: 'Blood pressure', when: 'Monthly until below 140/90 mmHg, then every 4-6 months', source_id: 'KENYA_HTN_STEPS' }] }

it('shows the patient summary with status against target and a copyable plan', () => {
  const withPlan = { ...encounter, assessment: { ...encounter.assessment!, care_plan: plan } } as Encounter
  render(<AssessmentReview encounter={withPlan} onReviewed={() => {}} onUpdated={() => {}} onConflict={() => {}} />)
  expect(screen.getByRole('heading', { name: plan.headline })).toBeVisible()
  const row = screen.getByRole('row', { name: /Hypertension/ })
  expect(within(row).getByText('BP 158/96 mmHg: above target (<140/90)')).toBeVisible()
  expect(within(row).getByText('Needs action')).toBeVisible()
  expect(screen.getByText('Monthly until below 140/90 mmHg, then every 4-6 months', { exact: false })).toBeVisible()
  const text = planText(plan)
  expect(text).toContain('- Hypertension: BP 158/96 mmHg: above target (<140/90)')
  expect(text).toContain('- Amlodipine 5 mg once daily (below the Table 4 maximum of 10 mg)')
})
