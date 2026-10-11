import { render,screen,waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach,it,expect,vi } from 'vitest'
import StudyWorkspace,{ StudyCase } from '../Study'
import { api } from '../api'
import type { User,Patient,Encounter } from '../types'
vi.mock('../api',()=>({api:vi.fn(),message:(error:Error)=>error.message}))
afterEach(()=>vi.clearAllMocks())
const user={id:'admin',role:'admin',clinical_testing:true} as User
const patient={id:'p',synthetic:true} as Patient
const encounter={id:'e',created_at:'2026-09-13T09:00:00Z'} as Encounter

it('keeps a failed submission retry identifier and blocks switching observation context with unsaved changes',async()=>{
  vi.mocked(api).mockResolvedValueOnce([]).mockRejectedValue(new Error('Unconfirmed save'))
  render(<StudyCase patient={patient} encounter={encounter} onDirtyChange={vi.fn()}/>)
  await userEvent.click(screen.getByRole('button',{name:'Open study observations'}))
  await userEvent.selectOptions(await screen.findByLabelText('Participation status'),'enrolled')
  await userEvent.click(screen.getByLabelText('Participation documented under the approved protocol'))
  await userEvent.click(screen.getByRole('button',{name:'Save study observation'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Unconfirmed save')
  const first=vi.mocked(api).mock.calls[1][1]?.body
  await userEvent.click(screen.getByRole('button',{name:'Save study observation'}))
  await waitFor(()=>expect(vi.mocked(api).mock.calls[2][1]?.body).toEqual(first))
  vi.spyOn(window,'confirm').mockReturnValue(false)
  await userEvent.selectOptions(screen.getByLabelText('Observation type'),'safety')
  expect(screen.getByLabelText('Observation type')).toHaveValue('enrolment')
})

it('keeps clinical record selection and date filters fixed while a daily tally is unsaved',async()=>{
  render(<StudyWorkspace user={user} onDirtyChange={vi.fn()}/>)
  expect(screen.getByLabelText('Record class')).toHaveValue('false')
  await userEvent.clear(screen.getByLabelText('All eligible adult NCD visits'))
  await userEvent.type(screen.getByLabelText('All eligible adult NCD visits'),'10')
  expect(screen.getByLabelText('Record class')).toBeDisabled()
  expect(screen.getByLabelText('From')).toBeDisabled()
  expect(screen.queryByRole('button',{name:'Download protected cohort extract'})).not.toBeInTheDocument()
})

it('loads a saved revision for correction instead of silently overwriting it',async()=>{
  const saved={id:'saved',encounter_id:'e',revision:2,payload:{kind:'enrolment',index_date:'2026-09-13',status:'enrolled',participation_documented:true}}
  vi.mocked(api).mockResolvedValueOnce([saved])
  render(<StudyCase patient={patient} encounter={encounter} onDirtyChange={vi.fn()}/>)
  await userEvent.click(screen.getByRole('button',{name:'Open study observations'}))
  await userEvent.selectOptions(await screen.findByLabelText('Saved observation to correct'),'saved')
  expect(screen.getByLabelText('Participation status')).toHaveValue('enrolled')
  expect(screen.getByLabelText('Index visit date')).toBeDisabled()
  expect(screen.getByRole('button',{name:'Save correction'})).toBeVisible()
})
