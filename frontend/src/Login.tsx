import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, HeartPulse, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import { api, message } from './api'
import type { Session } from './types'
import { BrandLogo } from './Brand'
import { Field, Notice } from './components'

export default function Login({ onLogin, expired }: { onLogin: (session: Session) => void; expired: boolean }) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try { onLogin(await api<Session>('/auth/login', { method: 'POST', body: { email, password } })) } catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <div className="login-page">
    <div className="login-story">
      <a className="brand brand-light" href="#main"><BrandLogo /><span>NCDAI <em>2.0</em></span></a>
      <div className="login-story-content"><div className="eyebrow">A MORE CONNECTED CARE JOURNEY</div><h1>Clearer decisions.<br />Continuity of care.</h1><p>A clinical workspace for adult noncommunicable disease care. Built around the patient, guided by evidence, reviewed by you.</p><div className="login-points"><span><ShieldCheck size={20} /> Clinician review at every decision</span><span><HeartPulse size={20} /> One longitudinal patient record</span><span><LockKeyhole size={20} /> Access within your facility</span></div></div>
      <div className="login-footnote">NCDAI 2.0 · Kenya-first NCD care</div>
    </div>
    <main id="main" className="login-form-wrap"><div className="login-form">
      <div className="research-label">Research preview • synthetic cases only</div>
      <div className="eyebrow">CLINICAL WORKSPACE</div><h2>Welcome back</h2><p className="muted">Sign in with your facility account.</p>
      {expired && <Notice tone="warning">Your session ended. Sign in again to continue. Unsaved work may need to be re-entered.</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      <form onSubmit={submit}>
        <Field label="Email address"><input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></Field>
        <Field label="Password"><input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></Field>
        <button className="button button-primary login-submit" disabled={busy} type="submit">{busy ? <LoaderCircle size={18} className="spin" /> : <>Sign in <ArrowRight size={18} /></>}</button>
      </form>
      <div className="login-help"><strong>Setting up a local demonstration?</strong><p>An administrator must explicitly create synthetic demo accounts using the setup guide. No account is enabled automatically.</p></div>
      <p className="fine-print">This research build supports supervised testing. It is not approved for live patient care and does not prescribe treatment.</p>
    </div></main>
  </div>
}
