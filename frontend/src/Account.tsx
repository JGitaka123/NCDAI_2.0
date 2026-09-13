import { useRef, useState } from 'react'
import { KeyRound } from 'lucide-react'
import { api, message } from './api'
import { titleCase } from './clinical'
import { Field, Notice, PageHeader, Panel } from './components'
import type { User } from './types'

export default function Account({ user }: { user: User }) {
  const [currentPassword, setCurrentPassword] = useState(''), [newPassword, setNewPassword] = useState(''), [confirmation, setConfirmation] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [success, setSuccess] = useState('')
  const confirmationRef = useRef<HTMLInputElement>(null)
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setSuccess('')
    if (newPassword !== confirmation) { setError('The new passwords do not match. Re-enter the confirmation.'); confirmationRef.current?.focus(); return }
    if (!newPassword.trim() || newPassword === currentPassword) { setError('Choose a new password that differs from the current password and is not all spaces.'); return }
    setBusy(true)
    try {
      const result = await api<{ status: 'password_changed'; other_sessions_revoked: number }>('/auth/change-password', { method: 'POST', body: { current_password: currentPassword, new_password: newPassword } })
      window.dispatchEvent(new Event('ncdai-account-updated'))
      setCurrentPassword(''); setNewPassword(''); setConfirmation('')
      setSuccess(`Password changed. Your current session remains active. ${result.other_sessions_revoked} other session${result.other_sessions_revoked === 1 ? ' was' : 's were'} signed out.`)
    } catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <><PageHeader eyebrow="YOUR WORKSPACE" title="Account" description="Manage your sign-in details." /><div className="account-layout"><Panel title="Your account"><dl className="account-details"><div><dt>Name</dt><dd>{user.display_name}</dd></div><div><dt>Email</dt><dd>{user.email}</dd></div><div><dt>Role</dt><dd>{titleCase(user.role)}</dd></div><div><dt>Facility</dt><dd>{user.facility_name}</dd></div></dl></Panel><Panel title="Change password" subtitle="Use 14–256 characters. Other signed-in sessions will be closed; this session will remain active."><form className="account-form" onSubmit={submit}><fieldset disabled={busy}><legend className="sr-only">Change your password</legend><Field label="Current password"><input type="password" required maxLength={256} autoComplete="current-password" value={currentPassword} onChange={event => { setCurrentPassword(event.target.value); setError(''); setSuccess('') }} /></Field><Field label="New password"><input type="password" required minLength={14} maxLength={256} autoComplete="new-password" value={newPassword} onChange={event => { setNewPassword(event.target.value); setError(''); setSuccess('') }} /></Field><Field label="Confirm new password"><input ref={confirmationRef} type="password" required minLength={14} maxLength={256} autoComplete="new-password" value={confirmation} onChange={event => { setConfirmation(event.target.value); setError(''); setSuccess('') }} /></Field>{error && <Notice tone="error">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}<button className="button button-primary" type="submit"><KeyRound size={17} />{busy ? 'Changing password…' : 'Change password'}</button></fieldset></form></Panel></div></>
}
