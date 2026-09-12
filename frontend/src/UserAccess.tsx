import { useEffect, useState } from 'react'
import { api, message } from './api'
import { titleCase } from './clinical'
import { Loading, Notice, PageHeader, Panel } from './components'
import type { User } from './types'

export default function UserAccess({ currentUser }: { currentUser: User }) {
  const [users, setUsers] = useState<User[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState(''), [success, setSuccess] = useState(''), [busy, setBusy] = useState(false), [pending, setPending] = useState<User | null>(null), [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); let active = true
    setLoading(true); setError('')
    api<User[]>('/users', { signal: controller.signal }).then(value => { if (active) setUsers(value) }).catch(error => { if (active) setError(message(error)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [attempt])
  async function update() {
    if (!pending || pending.active === undefined || pending.id === currentUser.id) return
    const user = pending; setBusy(true); setError(''); setSuccess('')
    try {
      const saved = await api<User>(`/users/${encodeURIComponent(user.id)}/status`, { method: 'PATCH', body: { active: !user.active } })
      setUsers(items => items.map(item => item.id === saved.id ? saved : item)); setPending(null)
      setSuccess(`${saved.display_name} is now ${saved.active ? 'active and can sign in again' : 'inactive; existing sessions were signed out'}.`)
    } catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <><PageHeader eyebrow="FACILITY ADMINISTRATION" title="User access" description={`Manage existing accounts at ${currentUser.facility_name}.`} action={<button className="button button-secondary" disabled={busy || loading} onClick={() => { setPending(null); setSuccess(''); setAttempt(value => value + 1) }}>Refresh accounts</button>} />
    <Notice>Deactivation prevents sign-in and closes the account’s sessions. Reactivation permits a new sign-in. Your own account and the last active administrator are protected.</Notice>
    {error && <Notice tone="error">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}
    {loading ? <Loading label="Loading facility accounts…" /> : <Panel title="Facility accounts"><div className="user-access-list">{users.length === 0 ? <p className="empty-inline">No accounts returned.</p> : users.map(user => <article className="user-access-row" key={user.id}><div><h3>{user.display_name}{user.id === currentUser.id && <span className="muted"> (you)</span>}</h3><p>{user.email}</p><small>{titleCase(user.role)} · {user.active === true ? 'Active' : user.active === false ? 'Inactive' : 'Status unavailable'}</small></div><button type="button" className={`button button-secondary button-small ${user.active ? 'danger-text' : ''}`} disabled={busy || user.id === currentUser.id || user.active === undefined} aria-label={`${user.active ? 'Deactivate' : 'Activate'} ${user.display_name}`} onClick={() => { setPending(user); setError(''); setSuccess('') }}>{user.id === currentUser.id ? 'Current account' : user.active === undefined ? 'Status unavailable' : user.active ? 'Deactivate' : 'Activate'}</button></article>)}</div></Panel>}
    {pending && <section className="access-confirmation" aria-labelledby="access-confirmation-title"><h2 id="access-confirmation-title">{pending.active ? 'Deactivate' : 'Activate'} {pending.display_name}?</h2><p>{pending.email} · {titleCase(pending.role)}</p><p>{pending.active ? 'This account will lose access and its signed-in sessions will close.' : 'This account will be able to sign in with its existing password.'}</p><div className="button-row"><button type="button" className="button button-primary" disabled={busy} onClick={update}>{busy ? 'Updating access…' : pending.active ? 'Confirm deactivation' : 'Confirm activation'}</button><button type="button" className="button button-secondary" disabled={busy} onClick={() => setPending(null)}>Cancel</button></div></section>}
  </>
}
