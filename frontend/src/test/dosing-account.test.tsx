import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import DoseSupport from '../DoseSupport'
import Account from '../Account'
import UserAccess from '../UserAccess'
import { emptyClinicalData, emptyDosingContext } from '../clinical'
import { api } from '../api'
import type { ClinicalData, User } from '../types'

vi.mock('../api', () => ({ api: vi.fn(), message: (error: Error) => error.message }))
afterEach(() => vi.resetAllMocks())
const user: User = { id: 'self', email: 'admin@example.test', display_name: 'Synthetic Admin', role: 'admin', facility_id: 'f', facility_name: 'Test clinic', active: true }
const catalogue = { version: 'test', scope_note: 'Selected references only.', medicines: [{ medicine_id: 'amlodipine_tablet', name: 'Amlodipine', indication: 'hypertension', formulation: 'Single tablet', route: 'oral', unit: 'mg', clinical_checks: 'Review hepatic disease and hypotension.' }] }
function DoseHarness() {
  const [data, setData] = useState<ClinicalData>({ ...emptyClinicalData(), dosing_context: emptyDosingContext(), dosing_requests: [{ medicine_id: 'amlodipine_tablet', indication: 'hypertension' }] })
  return <><DoseSupport data={data} onChange={setData} disabled={false} /><output data-testid="data">{JSON.stringify(data)}</output></>
}

it('keeps unknown dose context and shows the medicine-specific checklist', async () => {
  vi.mocked(api).mockResolvedValue(catalogue)
  render(<DoseHarness />)
  expect(await screen.findByText('Review hepatic disease and hypotension.')).toBeVisible()
  expect(screen.getByLabelText('Hepatic impairment')).toHaveValue('unknown')
  expect(screen.getByLabelText(/No unresolved contraindications/)).not.toBeChecked()
  expect(screen.getByLabelText(/Proposed dose per administration/)).toHaveValue(null)
  await userEvent.type(screen.getByLabelText(/Proposed dose per administration/), '5')
  expect(screen.getByLabelText(/Proposed administrations per day/)).toBeRequired()
  await userEvent.type(screen.getByLabelText(/Proposed administrations per day/), '1')
  const data = JSON.parse(screen.getByTestId('data').textContent!)
  expect(data.dosing_requests[0]).toMatchObject({ proposed_dose_mg: 5, frequency_per_day: 1 })
  expect(data.dosing_context.interactions_reviewed).toBe(false)
})

it('does not fetch optional catalogue while the empty section is closed', () => {
  render(<DoseSupport data={emptyClinicalData()} onChange={vi.fn()} disabled={false} />)
  expect(api).not.toHaveBeenCalled()
})

it('keeps existing requests removable when the optional catalogue fails', async () => {
  vi.mocked(api).mockRejectedValue(new Error('Temporary outage'))
  render(<DoseHarness />)
  expect(await screen.findByRole('alert')).toHaveTextContent('The rest of the intake remains available')
  await userEvent.click(screen.getByLabelText('Remove reference check 1'))
  expect(JSON.parse(screen.getByTestId('data').textContent!).dosing_requests).toEqual([])
})

it('requires matching passwords without transmitting a mismatched form', async () => {
  render(<Account user={user} />)
  await userEvent.type(screen.getByLabelText('Current password'), 'current-test-password')
  await userEvent.type(screen.getByLabelText('New password'), 'replacement-test-password')
  await userEvent.type(screen.getByLabelText('Confirm new password'), 'different-test-password')
  await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
  expect(screen.getByRole('alert')).toHaveTextContent('do not match')
  expect(api).not.toHaveBeenCalled()
})

it('clears successful password fields and explains other-session revocation', async () => {
  vi.mocked(api).mockResolvedValue({ status: 'password_changed', other_sessions_revoked: 2 })
  render(<Account user={user} />)
  await userEvent.type(screen.getByLabelText('Current password'), 'current-test-password')
  await userEvent.type(screen.getByLabelText('New password'), 'replacement-test-password')
  await userEvent.type(screen.getByLabelText('Confirm new password'), 'replacement-test-password')
  await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
  await waitFor(() => expect(screen.getByLabelText('Current password')).toHaveValue(''))
  expect(screen.getByRole('status')).toHaveTextContent('2 other sessions were signed out')
  expect(api).toHaveBeenCalledWith('/auth/change-password', expect.objectContaining({ method: 'POST' }))
})

it('protects self access and confirms another account change before calling the API', async () => {
  const colleague = { ...user, id: 'other', email: 'other@example.test', display_name: 'Synthetic Colleague', role: 'clinician' as const }
  vi.mocked(api).mockResolvedValueOnce([user, colleague]).mockResolvedValueOnce({ ...colleague, active: false })
  render(<UserAccess currentUser={user} />)
  await screen.findByText('Synthetic Colleague')
  expect(screen.getByRole('button', { name: 'Deactivate Synthetic Admin' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Deactivate Synthetic Colleague' }))
  expect(api).toHaveBeenCalledTimes(1)
  await userEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/users/other/status', { method: 'PATCH', body: { active: false } }))
  expect(await screen.findByRole('button', { name: 'Activate Synthetic Colleague' })).toBeEnabled()
})
