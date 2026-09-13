import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import Login from '../Login'
import ClinicalIntake from '../ClinicalIntake'
import AssessmentReview from '../AssessmentReview'
import { emptyClinicalData } from '../clinical'
import type { Encounter } from '../types'

afterEach(() => vi.unstubAllGlobals())
function IntakeHarness() { const [data, setData] = useState(emptyClinicalData()); return <><ClinicalIntake data={data} onChange={setData} disabled={false} /><output aria-label="Current input">{JSON.stringify(data)}</output></> }
const encounter = { id: 'encounter', patient_id: 'patient', status: 'draft', version: 3, data: emptyClinicalData(), created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z', assessment: { id: 'assessment', urgency: 'emergency', summary: 'Emergency red flags require assessment.', recommendations: [{ id: 'rec-1', rule_id: 'URGENT', category: 'cardiovascular', severity: 'critical', title: 'Arrange urgent assessment', detail: 'Follow emergency procedures without waiting for this form.', evidence: [] }], missing_data: ['repeat_systolic_bp'], warnings: [], model_info: { mode: 'deterministic_rules', status: 'clinical_review_required' }, generated_at: '2026-01-01T12:00:00Z', evidence_version: 'v0.1' } } as Encounter

describe('Clinician workflow safeguards', () => {
  it('requires explicit login and displays the authorized hospital-testing boundary', async () => {
    const user = userEvent.setup(); const onLogin = vi.fn(); const fetch = vi.fn().mockResolvedValue(new Response('{"detail":"Invalid credentials"}', { status: 401 })); vi.stubGlobal('fetch', fetch)
    render(<Login onLogin={onLogin} expired={false} />)
    expect(screen.getByLabelText('Email address')).toHaveValue(''); expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(screen.getByText('Hospital testing · authorized accounts only')).toBeVisible()
    await user.type(screen.getByLabelText('Email address'), 'clinician@example.test'); await user.type(screen.getByLabelText('Password'), 'synthetic-not-a-secret'); await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials'); expect(onLogin).not.toHaveBeenCalled()
  })
  it('lets a clinician record symptoms and explicitly mark the list reviewed', async () => {
    const user = userEvent.setup(); render(<IntakeHarness />)
    await user.click(screen.getByRole('checkbox', { name: 'Chest pain' })); await user.click(screen.getByRole('checkbox', { name: /Symptom assessment completed/ }))
    const state = JSON.parse(screen.getByLabelText('Current input').textContent || '{}')
    expect(state.symptoms).toContain('chest_pain'); expect(state.symptoms_reviewed).toBe(true); expect(state.systolic_bp).toBeNull()
  })
  it('does not preselect acceptance and blocks incomplete review', async () => {
    const user = userEvent.setup(); render(<AssessmentReview encounter={encounter} onReviewed={vi.fn()} onUpdated={vi.fn()} onConflict={vi.fn()} />)
    expect(screen.getByText('Do not delay emergency care to complete this review.')).toBeVisible()
    expect(screen.getByRole('radio', { name: 'Accept' })).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Record review & lock encounter' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a decision')
  })
  it('records modification with a reason, replacement text and exact assessment version', async () => {
    const user = userEvent.setup(); const onReviewed = vi.fn(); const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...encounter, status: 'reviewed' }), { status: 200 })); vi.stubGlobal('fetch', fetch)
    render(<AssessmentReview encounter={encounter} onReviewed={onReviewed} onUpdated={vi.fn()} onConflict={vi.fn()} />)
    await user.click(screen.getByRole('radio', { name: 'Modify' })); await user.type(screen.getByLabelText('Reason for modification (required)'), 'Local transfer pathway'); await user.type(screen.getByLabelText('Modified clinical action (required)'), 'Call the receiving emergency team'); await user.click(screen.getByRole('button', { name: 'Record review & lock encounter' }))
    const sent = JSON.parse(fetch.mock.calls[0][1].body)
    expect(sent.expected_version).toBe(3); expect(sent.assessment_id).toBe('assessment'); expect(sent.decisions[0]).toEqual({ recommendation_id: 'rec-1', action: 'modify', reason: 'Local transfer pathway', modified_text: 'Call the receiving emergency team' })
    expect(onReviewed).toHaveBeenCalled()
  })
  it('retains safety recommendations when optional AI briefing is unavailable', async () => {
    const user = userEvent.setup(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Provider unavailable"}', { status: 503 })))
    render(<AssessmentReview encounter={encounter} onReviewed={vi.fn()} onUpdated={vi.fn()} onConflict={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Prepare AI briefing' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your original safety recommendations remain available')
    expect(screen.getByRole('heading', { name: 'Arrange urgent assessment' })).toBeVisible()
  })
})
