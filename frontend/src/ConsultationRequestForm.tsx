import { useEffect, useState } from 'react'
import { api, message } from './api'
import { Field, Notice, Panel } from './components'
import type { Encounter } from './types'

export default function ConsultationRequestForm({ encounter, onDirtyChange }: { encounter: Encounter; onDirtyChange: (value: boolean) => void }) {
  const [open, setOpen] = useState(false), [selected, setSelected] = useState<string[]>([]), [reason, setReason] = useState('uncertainty'), [question, setQuestion] = useState(''), [action, setAction] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(''), [delivered, setDelivered] = useState(false)
  const [key] = useState(() => crypto.randomUUID())
  const dirty = open && !saved && !!(question || action || selected.length)
  useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false) }, [dirty, onDirtyChange])
  async function deliver(id: string) {
    setBusy(true); setError('')
    try { await api(`/consultations/${id}/sync`, { method: 'POST' }); setDelivered(true) }
    catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!selected.length) { setError('Select the recommendation(s) you want reviewed.'); return }
    setBusy(true); setError('')
    try {
      const result = await api<{ id: string }>(`/encounters/${encounter.id}/consultations`, { method: 'POST', body: {
        idempotency_key: key, expected_version: encounter.version, assessment_id: encounter.assessment!.id,
        recommendation_ids: selected, reason_category: reason, question, immediate_action: action,
      } })
      setSaved(result.id); await deliver(result.id)
    } catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  if (!open) return <div className="panel-body"><button className="button button-secondary" onClick={() => setOpen(true)}>Request consultant review</button><p>Disagree with a recommendation or need a second opinion? Preserve the case and ask a consultant.</p></div>
  return <Panel title="Request consultant review"><div className="panel-body">
    <Notice tone="warning">A consultation is not an emergency response service. Continue immediate assessment, treatment and referral through the hospital team; do not wait for an online reply.</Notice>
    {error && <Notice tone="error">{error}</Notice>}
    {saved ? <><Notice tone="success">Request saved. {delivered ? 'Delivered to the consultant workspace.' : 'Delivery is pending; the question has not been lost.'}</Notice><p className="mono">{saved}</p>{!delivered && <button className="button button-secondary" disabled={busy} onClick={() => deliver(saved)}>Retry delivery</button>}<p><a href="/consultant">Open consultations and follow the response</a></p></> : <form onSubmit={submit}>
      <fieldset disabled={busy}><legend>Recommendations for a second opinion</legend>{encounter.assessment!.recommendations.map(rec => <label key={rec.id} className="review-checkbox"><input type="checkbox" checked={selected.includes(rec.id)} onChange={e => setSelected(e.target.checked ? [...selected, rec.id] : selected.filter(id => id !== rec.id))} /><span>{rec.title}</span></label>)}</fieldset>
      <Field label="Reason for consultation"><select value={reason} onChange={e => setReason(e.target.value)}><option value="uncertainty">Uncertainty</option><option value="disagreement">Disagreement with recommendation</option><option value="dose_question">Medicine or dose question</option><option value="outside_scope">Case outside application scope</option><option value="other">Other</option></select></Field>
      <Field label="Question and why you need review"><textarea required minLength={10} maxLength={4000} value={question} onChange={e => setQuestion(e.target.value)} /></Field>
      <Field label="Immediate action taken while awaiting advice"><textarea required minLength={10} maxLength={4000} value={action} onChange={e => setAction(e.target.value)} /></Field>
      <p>The current assessment and clinical inputs will be preserved. Subsequent changes will be identified separately.</p>
      <button type="button" className="button button-secondary" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard this consultation draft?')) { setOpen(false); setQuestion(''); setAction(''); setSelected([]) } }}>Cancel consultation draft</button>
      <button className="button button-primary" disabled={busy}>{busy ? 'Saving request…' : 'Submit consultation'}</button>
    </form>}
  </div></Panel>
}
