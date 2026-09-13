import { useCallback, useEffect, useState } from 'react'
import { api, message } from './api'
import { Field, Notice, PageHeader, Panel } from './components'
import ClinicalSnapshot from './ClinicalSnapshot'
import type { User, Assessment } from './types'

type Consultation = {
  id: string; encounter_id: string; patient_id: string; requested_by: string; created_at: string; snapshot_hash: string;
  snapshot_stale: boolean; current_encounter_version: number; service_available: boolean; delivered: boolean; status: string;
  urgency: string; question: string; synthetic: boolean;
  patient_identity?: { name: string; record_id: string };
  snapshot?: { assessment: Assessment; data: Record<string, unknown>; age: number; sex: string; immediate_action: string; reason_category: string; recommendation_ids: string[] };
  opinion: null | { opinion_hash: string; reviewer_id: string; reviewer_name: string; agreement: string; assessment: string; recommended_action: string; rationale: string; urgency: string; source_references: string; reviewed_at: string };
  disposition: null | { action: string; action_taken: string; created_at: string };
}
const blankOpinion = { agreement: 'insufficient_information', assessment: '', recommended_action: '', rationale: '', urgency: 'routine', source_references: '' }

export default function Consultations({ user, onDirtyChange }: { user: User; onDirtyChange: (dirty: boolean) => void }) {
  const [rows, setRows] = useState<Consultation[]>([]), [current, setCurrent] = useState<Consultation | null>(null), [offset, setOffset] = useState(0), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [opinion, setOpinion] = useState(blankOpinion), [action, setAction] = useState('accepted'), [taken, setTaken] = useState(''), [acknowledged, setAcknowledged] = useState(false)
  const dirty = !!(opinion.assessment || opinion.recommended_action || opinion.rationale || opinion.source_references || taken)
  useEffect(() => { onDirtyChange(dirty); const warn = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = '' } }; window.addEventListener('beforeunload', warn); return () => { onDirtyChange(false); window.removeEventListener('beforeunload', warn) } }, [dirty, onDirtyChange])
  const refresh = useCallback(async () => { try { setRows(await api<Consultation[]>(`/consultations?limit=50&offset=${offset}`)) } catch (error) { setError(message(error)) } }, [offset])
  useEffect(() => { void refresh(); const timer = window.setInterval(() => { void refresh() }, 30000); return () => window.clearInterval(timer) }, [refresh])
  async function select(row: Consultation) {
    if (dirty && !window.confirm('Discard this unsaved consultation response?')) return
    setError(''); setBusy(true)
    try { setCurrent(await api<Consultation>(`/consultations/${row.id}`)); setOpinion({ ...blankOpinion, urgency: row.urgency }); setTaken(''); setAcknowledged(false) }
    catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  async function mutate(suffix: string, body?: unknown) {
    if (!current) return
    setError(''); setBusy(true)
    try { setCurrent(await api<Consultation>(`/consultations/${current.id}/${suffix}`, { method: 'POST', body })); setOpinion(blankOpinion); setTaken(''); setAcknowledged(false); await refresh() }
    catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <><PageHeader eyebrow="CONSULTANT WORKSPACE" title="Second opinions, connected." description="Preserved recommendations, independent consultant advice and the primary team's final action." />
    <Notice tone="warning">Use direct hospital escalation for urgent or emergency care. The online queue is not continuously staffed or a substitute for immediate referral.</Notice>
    {error && <Notice tone="error">{error}</Notice>}
    <Panel title="Facility consultation queue"><div className="panel-body"><button className="button button-secondary" onClick={refresh}>Refresh queue</button>{rows.length === 0 && <p>No requests on this page.</p>}
      <div className="consultation-list">{rows.map(row => <button key={row.id} className="consultation-card" onClick={() => select(row)} disabled={busy}><strong>{row.urgency.toUpperCase()} · {row.status.replaceAll('_', ' ')}</strong><span>{row.question}</span><small>{new Date(row.created_at).toLocaleString()} · {row.synthetic ? 'Fictional case' : 'Clinical testing'}{!row.service_available ? ' · Consultant service unavailable' : ''}</small></button>)}</div>
      <div className="form-actions"><button className="button button-secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><button className="button button-secondary" disabled={rows.length < 50} onClick={() => setOffset(offset + 50)}>Next</button></div>
    </div></Panel>
    {current && <Panel title="Consultation record"><div className="panel-body">
      <p className="mono">Request {current.id}</p><p><strong>{current.patient_identity?.name}</strong> · Record {current.patient_identity?.record_id}</p><p><strong>{current.question}</strong></p><p>{current.snapshot?.age} years · {current.snapshot?.sex} · {current.synthetic ? 'Fictional record' : 'Clinical testing record'}</p>
      {!current.service_available && <Notice tone="error">Consultant storage is unavailable. The primary request is retained. Use the hospital escalation process and retry delivery.</Notice>}
      {current.snapshot_stale && <Notice tone="warning">The encounter has changed since this request. This opinion concerns the preserved snapshot; check current findings before acting.</Notice>}
      {!current.delivered && <button className="button button-primary" disabled={busy} onClick={() => mutate('sync')}>Deliver saved request</button>}
      <p><strong>Immediate action recorded:</strong> {current.snapshot?.immediate_action}</p>
      <details><summary>Preserved clinical observations</summary><ClinicalSnapshot data={current.snapshot?.data ?? {}} /></details>
      <div className="evidence-list">{current.snapshot?.assessment.recommendations.map(rec => <article key={rec.id}><h3>{current.snapshot?.recommendation_ids.includes(rec.id) ? 'Selected for review: ' : ''}{rec.title}</h3><p>{rec.detail}</p><small>{rec.severity} · {rec.rule_id}</small>{rec.evidence.map(source => <p key={source.source_id}>{source.title} — {source.section}</p>)}</article>)}</div>
      <details><summary>Snapshot traceability</summary><p className="mono consultation-hash">{current.snapshot_hash}</p><p>Encounter {current.encounter_id}. Current version {current.current_encounter_version}.</p></details>
      {current.opinion ? <section><h2>Consultant opinion</h2><p>{current.opinion.reviewer_name} · {new Date(current.opinion.reviewed_at).toLocaleString()}</p><p><strong>{current.opinion.agreement.replaceAll('_', ' ')} · {current.opinion.urgency}</strong></p><p>{current.opinion.assessment}</p><h3>Recommended action</h3><p>{current.opinion.recommended_action}</p><h3>Rationale and sources</h3><p>{current.opinion.rationale}</p><p>{current.opinion.source_references}</p></section> : user.role === 'supervisor' && user.id !== current.requested_by && <form onSubmit={e => { e.preventDefault(); void mutate('opinion', { ...opinion, snapshot_hash: current.snapshot_hash }) }}><h2>Independent consultant response</h2>
        <Field label="Agreement with selected recommendations"><select value={opinion.agreement} onChange={e => setOpinion({ ...opinion, agreement: e.target.value })}><option value="insufficient_information">Insufficient information</option><option value="agree">Agree</option><option value="partly_agree">Partly agree</option><option value="disagree">Disagree</option></select></Field>
        {(['assessment', 'recommended_action', 'rationale', 'source_references'] as const).map(key => <Field key={key} label={key.replaceAll('_', ' ')}><textarea required minLength={key === 'source_references' ? 3 : 10} maxLength={key === 'source_references' ? 4000 : 6000} value={opinion[key]} onChange={e => setOpinion({ ...opinion, [key]: e.target.value })} /></Field>)}
        <Field label="Consultant-assessed urgency"><select value={opinion.urgency} onChange={e => setOpinion({ ...opinion, urgency: e.target.value })}>{['routine', 'soon', 'urgent', 'emergency'].map(value => <option key={value}>{value}</option>)}</select></Field>
        <p>Your response is signed with your account and is immutable. It does not replace the original recommendation.</p><button className="button button-primary" disabled={busy}>Record consultant opinion</button>
      </form>}
      {!current.opinion && current.requested_by === user.id && <p>Another consultant must independently answer your request.</p>}
      {current.disposition ? <section><h2>Primary team's final action</h2><p>{current.disposition.action}</p><p>{current.disposition.action_taken}</p></section> : current.opinion && current.opinion.reviewer_id !== user.id && <form onSubmit={e => { e.preventDefault(); void mutate('disposition', { opinion_hash: current.opinion!.opinion_hash, expected_encounter_version: current.current_encounter_version, action, action_taken: taken, stale_snapshot_acknowledged: acknowledged }) }}><h2>Record the action taken</h2><Field label="Response to consultant advice"><select value={action} onChange={e => setAction(e.target.value)}><option value="accepted">Accepted</option><option value="modified">Modified</option><option value="not_followed">Not followed</option></select></Field><Field label="Actual action and reasons"><textarea required minLength={10} maxLength={6000} value={taken} onChange={e => setTaken(e.target.value)} /></Field>{current.snapshot_stale && <label className="review-checkbox"><input type="checkbox" required checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />I checked current findings and changes since this consultation snapshot.</label>}<p>This signed record does not rewrite an earlier encounter. Document subsequent clinical assessment in a new encounter where needed.</p><button className="button button-primary" disabled={busy}>Record final action</button></form>}
    </div></Panel>}
  </>
}
