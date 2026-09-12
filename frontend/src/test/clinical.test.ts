import { describe, expect, it } from 'vitest'
import { carryForwardContext, emptyClinicalData, isDirty, numericInput, reviewErrors, safeEvidenceUrl } from '../clinical'
import type { Encounter, Recommendation } from '../types'

const recommendation: Recommendation = { id: 'r1', rule_id: 'HTN_URGENT', category: 'cardiovascular', severity: 'critical', title: 'Urgent assessment', detail: 'Inspect red flags.', evidence: [] }
describe('Clinical input safety and accountable review', () => {
  it('keeps blank clinical values unknown, not zero or normal', () => {
    expect(numericInput('')).toBeNull(); expect(numericInput('   ')).toBeNull(); expect(numericInput('0')).toBe(0)
    const data = emptyClinicalData(); expect(data.systolic_bp).toBeNull(); expect(data.known_hypertension).toBe('unknown'); expect(data.pregnancy_status).toBe('unknown')
  })
  it('does not interpret empty lists as reviewed negatives', () => {
    const data = emptyClinicalData(); expect(data.medications_reviewed).toBe(false); expect(data.allergies_reviewed).toBe(false); expect(data.symptoms_reviewed).toBe(false)
  })
  it('requires an explicit action for every recommendation', () => {
    expect(reviewErrors([recommendation], {})).toHaveLength(1)
    expect(reviewErrors([recommendation], { r1: { action: 'accept' } })).toEqual([])
  })
  it.each(['modify', 'defer', 'reject'] as const)('requires a nonblank reason for %s', action => {
    expect(reviewErrors([recommendation], { r1: { action, reason: '   ' } })).toHaveLength(1)
  })
  it('requires the actual modified action in addition to a reason', () => {
    expect(reviewErrors([recommendation], { r1: { action: 'modify', reason: 'Facility limitation' } })).toHaveLength(1)
    expect(reviewErrors([recommendation], { r1: { action: 'modify', reason: 'Facility limitation', modified_text: 'Arrange immediate transfer' } })).toEqual([])
  })
  it('carries history forward without turning old observations into current findings', () => {
    const prior = { id: 'old-encounter', created_at: '2026-01-01T12:00:00Z', data: { ...emptyClinicalData(), acutely_unwell: 'yes', acute_kidney_injury: 'yes', systolic_bp: 190, glucose: 18, egfr: 28, oxygen_saturation: 80, symptoms: ['chest_pain'], symptoms_reviewed: true, known_diabetes: 'yes', medications: [{ code: 'metformin', name: 'Metformin', dose: 500 }], medications_reviewed: true, allergies: ['enalapril'], allergies_reviewed: true, pregnancy_status: 'no' } } as Encounter
    const next = carryForwardContext(prior)
    expect(next.acutely_unwell).toBe('unknown'); expect(next.acute_kidney_injury).toBe('unknown')
    expect(next.known_diabetes).toBe('yes'); expect(next.medications).toEqual(prior.data.medications)
    expect(next.systolic_bp).toBeNull(); expect(next.glucose).toBeNull(); expect(next.egfr).toBeNull(); expect(next.oxygen_saturation).toBeNull(); expect(next.symptoms).toEqual([])
    expect(next.pregnancy_status).toBe('unknown'); expect(next.medications_reviewed).toBe(false); expect(next.allergies_reviewed).toBe(false); expect(next.symptoms_reviewed).toBe(false)
    expect(next.notes).toContain(prior.id)
    next.medications[0].dose = 200; expect(prior.data.medications[0].dose).toBe(500)
  })
  it('does not import unreviewed medication or allergy lists', () => {
    const prior = { id: 'old-encounter', created_at: '2026-01-01T12:00:00Z', data: { ...emptyClinicalData(), medications: [{ code: 'insulin', name: 'Insulin' }], allergies: ['unknown'] } } as Encounter
    const next = carryForwardContext(prior); expect(next.medications).toEqual([]); expect(next.allergies).toEqual([])
  })
  it('identifies new and changed clinical inputs without dirtying an empty form', () => {
    const data = emptyClinicalData(); expect(isDirty(null, data)).toBe(false)
    expect(isDirty(null, { ...data, systolic_bp: 120 })).toBe(true)
    expect(isDirty({ data } as Encounter, { ...data, allergies_reviewed: true })).toBe(true)
  })
  it('renders only navigable http(s) evidence links', () => {
    expect(safeEvidenceUrl('javascript:alert(1)')).toBeUndefined(); expect(safeEvidenceUrl('data:text/html,test')).toBeUndefined()
    expect(safeEvidenceUrl('https://www.who.int/test')).toBe('https://www.who.int/test')
  })
})
