import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import ConsultationRequestForm from '../ConsultationRequestForm'
import Consultations from '../Consultations'
import { api } from '../api'
import { emptyClinicalData } from '../clinical'
import type { Encounter, User } from '../types'

vi.mock('../api', () => ({ api: vi.fn(), message: (error: Error) => error.message }))
afterEach(() => vi.resetAllMocks())
const encounter = { id: 'encounter', patient_id: 'p', status: 'draft', version: 2, data: emptyClinicalData(), assessment: { id: 'assessment', urgency: 'emergency', recommendations: [{ id: 'red-flag', rule_id: 'red-flag', title: 'Immediate assessment', detail: 'Continue emergency care.', severity: 'critical', category: 'acute_safety', evidence: [] }], missing_data: [], warnings: [], model_info: { mode: 'deterministic_rules' }, evidence_version: 'test' } } as unknown as Encounter
const user = { id: 'primary', email: 'primary@example.test', role: 'clinician', display_name: 'Fictional primary clinician' } as User

it('retains a saved question after delivery fails and retries delivery without a duplicate submission', async () => {
  vi.mocked(api).mockResolvedValueOnce({ id: 'request' }).mockRejectedValueOnce(new Error('Consultant storage offline')).mockResolvedValueOnce({ id: 'request', delivered: true })
  render(<ConsultationRequestForm encounter={encounter} onDirtyChange={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Request consultant review' }))
  expect(screen.getByText(/not an emergency response service/)).toBeVisible()
  await userEvent.click(screen.getByRole('checkbox', { name: 'Immediate assessment' }))
  await userEvent.type(screen.getByLabelText('Question and why you need review'), 'Please review these warning signs.')
  await userEvent.type(screen.getByLabelText('Immediate action taken while awaiting advice'), 'Arranged immediate clinical assessment.')
  await userEvent.click(screen.getByRole('button', { name: 'Submit consultation' }))
  expect(await screen.findByText(/Request saved/)).toHaveTextContent('Delivery is pending')
  expect(screen.getByText('Consultant storage offline')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Retry delivery' }))
  expect(await screen.findByText(/Request saved/)).toHaveTextContent('Delivered')
  expect(vi.mocked(api).mock.calls.filter(([path]) => path.includes('/encounters/'))).toHaveLength(1)
  expect(vi.mocked(api).mock.calls[0][1]?.body).toMatchObject({ expected_version: 2, assessment_id: 'assessment', recommendation_ids: ['red-flag'] })
})

const row = { id: 'request', encounter_id: 'encounter', patient_id: 'p', requested_by: 'primary', created_at: '2026-09-13T09:00:00Z', snapshot_hash: 'a'.repeat(64), snapshot_stale: true, current_encounter_version: 4, service_available: true, delivered: true, status: 'answered', urgency: 'emergency', question: 'Review the original finding.', synthetic: true,
  patient_identity: { name: 'Fictional Patient', record_id: 'SYN-1' },
  snapshot: { assessment: encounter.assessment, data: emptyClinicalData(), age: 52, sex: 'female', immediate_action: 'Emergency team contacted.', reason_category: 'disagreement', recommendation_ids: ['red-flag'] },
  opinion: { opinion_hash: 'b'.repeat(64), reviewer_id: 'consultant', reviewer_name: 'Independent consultant', agreement: 'partly_agree', assessment: 'Reviewed the original snapshot.', recommended_action: 'Arrange further supervised assessment.', rationale: 'The newer findings need assessment.', urgency: 'urgent', source_references: 'Test source', reviewed_at: '2026-09-13T09:15:00Z' }, disposition: null }

it('requires acknowledgement of stale clinical context before recording the primary action', async () => {
  vi.mocked(api).mockImplementation(async (path, options) => options?.method === 'POST' ? { ...row, status: 'closed', disposition: { action: 'accepted', action_taken: 'Reassessed and acted on the current findings.' } } : path.includes('?') ? [row] : row)
  render(<Consultations user={user} onDirtyChange={vi.fn()} />)
  await userEvent.click(await screen.findByRole('button', { name: /EMERGENCY/ }))
  expect(await screen.findByText(/encounter has changed since this request/)).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Record consultant opinion' })).not.toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Actual action and reasons'), 'Reassessed and acted on the current findings.')
  await userEvent.click(screen.getByRole('button', { name: 'Record final action' }))
  expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  await userEvent.click(screen.getByRole('checkbox', { name: /checked current findings/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Record final action' }))
  await waitFor(() => expect(vi.mocked(api).mock.calls.find(([, options]) => options?.method === 'POST')?.[1]?.body).toMatchObject({ expected_encounter_version: 4, stale_snapshot_acknowledged: true, opinion_hash: 'b'.repeat(64) }))
})
