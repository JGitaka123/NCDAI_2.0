import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api, message } from './api'
import { formatDate, titleCase } from './clinical'
import { Empty, Loading, Notice, PageHeader, Panel } from './components'
import type { AuditEvent } from './types'

export default function Audit() {
  const [events, setEvents] = useState<AuditEvent[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState(''), [revision, setRevision] = useState(0)
  useEffect(() => { let active = true; setLoading(true); setError(''); api<AuditEvent[]>('/audit').then(events => { if (active) setEvents(events) }).catch(error => { if (active) setError(message(error)) }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [revision])
  return <><PageHeader eyebrow="SUPERVISOR WORKSPACE" title="An accountable care record." description="Inspect facility activity without exposing clinical notes in the audit view." action={<button className="button button-secondary" onClick={() => setRevision(r => r + 1)}>Refresh activity</button>} /><div className="audit-intro"><ShieldCheck size={24} /><div><strong>Clinical actions leave a trace.</strong><p>Each event identifies the action, actor and record. A displayed hash is an integrity reference; it does not by itself confirm verification of the full chain.</p></div></div><Panel><div className="panel-heading"><h2>Recent facility activity</h2><p>{events.length} events shown · bounded activity view</p></div>{loading ? <Loading label="Loading audit events…" /> : error ? <div className="panel-body"><Notice tone="error">{error}</Notice></div> : events.length === 0 ? <Empty title="No audit events to display" /> : <div className="table-wrap"><table className="audit-table"><thead><tr><th>Time</th><th>Action</th><th>Record</th><th>Actor</th><th>Integrity reference</th></tr></thead><tbody>{events.map(event => <tr key={event.id}><td>{formatDate(event.created_at, true)}</td><td><strong>{titleCase(event.action.replace(/\./g, ' '))}</strong></td><td>{titleCase(event.entity_type)}<small className="mono" title={event.entity_id}>{event.entity_id.slice(0, 12)}</small></td><td className="mono" title={event.actor_id}>{event.actor_id?.slice(0, 12) || 'System'}</td><td className="mono" title={event.chain_hash}>{event.chain_hash?.slice(0, 14)}…</td></tr>)}</tbody></table></div>}</Panel></>
}
