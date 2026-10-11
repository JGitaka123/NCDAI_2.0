import { useEffect, useState } from 'react'
import { Activity, ArrowRight, ClipboardCheck, ClipboardList, FilePenLine, HeartPulse, Route, Search, UserPlus, UsersRound } from 'lucide-react'
import { api, message } from './api'
import { Badge, Empty, Loading, Notice, PageHeader, Panel } from './components'
import { formatDate, titleCase } from './clinical'
import type { AttentionItem, Dashboard as DashboardData, Referral, User } from './types'

const URGENCY_ORDER = { emergency: 0, urgent: 1, soon: 2, routine: 3 } as const

export default function Dashboard({ user, onPatients, onReferrals, onOpenEncounter, onStudy }: { user: User; onPatients: (search?: string) => void; onReferrals: () => void; onOpenEncounter?: (item: AttentionItem) => void; onStudy?: () => void }) {
  const [data, setData] = useState<DashboardData | null>(null), [referrals, setReferrals] = useState<Referral[]>([]), [error, setError] = useState(''), [revision, setRevision] = useState(0), [search, setSearch] = useState('')
  useEffect(() => { let active = true; setError(''); setData(null); Promise.all([api<DashboardData>('/dashboard'), api<Referral[]>('/referrals')]).then(([data, referrals]) => { if (active) { setData(data); setReferrals(referrals) } }).catch(error => { if (active) setError(message(error)) }); return () => { active = false } }, [revision])
  const hour = new Date().getHours()
  const attention = [...(data?.attention ?? [])].sort((a, b) => (URGENCY_ORDER[a.urgency ?? 'routine'] - URGENCY_ORDER[b.urgency ?? 'routine']) || b.updated_at.localeCompare(a.updated_at))
  const openReferrals = referrals.filter(r => ['requested', 'accepted'].includes(r.status))
  return <>
    <PageHeader eyebrow={`${user.facility_name} · ${formatDate(new Date().toISOString())}`} title={`Good ${hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'}, ${user.display_name.split(' ')[0]}.`} description="Pick up open work, or start with a patient." />
    <form className="dashboard-search" role="search" onSubmit={event => { event.preventDefault(); onPatients(search.trim()) }}><Search size={19} aria-hidden="true" /><label className="sr-only" htmlFor="dashboard-search">Find a patient by name or record ID</label><input id="dashboard-search" value={search} maxLength={100} onChange={event => setSearch(event.target.value)} placeholder="Find a patient by name or record ID…" /><button className="button button-primary" type="submit">Search <ArrowRight size={17} /></button></form>
    <div className="quick-actions">
      <button type="button" onClick={() => onPatients()}><span><UserPlus size={20} /></span><strong>Register or open a patient</strong><small>Start a new consultation</small></button>
      <button type="button" onClick={onReferrals}><span><Route size={20} /></span><strong>Referrals</strong><small>{data ? `${data.open_referrals} open` : 'Track follow-through'}</small></button>
      {onStudy && <button type="button" onClick={onStudy}><span><Activity size={20} /></span><strong>Study metrics</strong><small>Record study observations</small></button>}
    </div>
    {error ? <><Notice tone="error">{error}</Notice><button className="button button-secondary" onClick={() => setRevision(r => r + 1)}>Refresh overview</button></> : !data ? <Loading /> : <>
      {data.urgent_assessments > 0 && <Notice tone="warning"><strong>{data.urgent_assessments} urgent or emergency assessment{data.urgent_assessments === 1 ? '' : 's'} in facility records.</strong> Urgent open encounters are listed first below. This count includes recorded assessments; it does not confirm current clinical urgency.</Notice>}
      <div className="dashboard-grid">
        <Panel className="attention-panel"><div className="panel-heading panel-heading-row"><div><h2>Continue where you left off</h2><p>Open encounters not yet reviewed, most urgent first.</p></div><span className="count-pill">{data.drafts ?? attention.length} open</span></div>
          {attention.length === 0 ? <Empty title="No open encounters">Draft and unreviewed encounters will appear here.</Empty> : <ul className="attention-list">{attention.map(item => <li key={item.encounter_id}><button type="button" onClick={() => onOpenEncounter?.(item)} disabled={!onOpenEncounter}>
            <span className={`attention-icon ${item.urgency ? `text-${item.urgency}` : ''}`}>{item.stage === 'review' ? <ClipboardCheck size={19} /> : <FilePenLine size={19} />}</span>
            <div><strong>{item.patient_name}</strong><small>{item.patient_external_id} · updated {formatDate(item.updated_at, true)}</small></div>
            <span className="attention-stage">{item.stage === 'review' ? `Review ${item.recommendations} recommendation${item.recommendations === 1 ? '' : 's'}` : 'Finish intake & assess'}</span>
            {item.urgency && <Badge value={item.urgency} />}<ArrowRight size={16} aria-hidden="true" />
          </button></li>)}</ul>}
        </Panel>
        <Panel><div className="panel-heading panel-heading-row"><div><h2>Referral follow-through</h2><p>Keep the next step in sight.</p></div><button className="text-button" onClick={onReferrals}>View all <ArrowRight size={17} /></button></div>{openReferrals.slice(0, 4).map(referral => <div className="referral-preview" key={referral.id}><span className="avatar"><Route size={19} /></span><div><strong>{referral.destination}</strong>{referral.patient_name && <p className="referral-patient-preview">{referral.patient_name} · {referral.patient_external_id ?? 'Record ID unavailable'}</p>}<p>{referral.reason}</p><small>{formatDate(referral.created_at)} · {titleCase(referral.urgency)}</small></div><Badge value={referral.status} /></div>)}{openReferrals.length === 0 && <Empty title="No open referrals">Requested and accepted referrals will appear here.</Empty>}</Panel>
      </div>
      <div className="stat-grid"><Stat icon={<UsersRound size={21} />} value={data.patients} title="Patients" subtitle="Registered at your facility" onClick={() => onPatients()} /><Stat icon={<HeartPulse size={21} />} value={data.encounters} title="Encounters" subtitle="Saved clinical records" /><Stat icon={<ClipboardList size={21} />} value={data.reviewed} title="Reviewed" subtitle="Clinician decisions recorded" /><Stat icon={<Route size={21} />} value={data.open_referrals} title="Open referrals" subtitle="Follow-through in progress" onClick={onReferrals} /></div>
      <Panel title="How this workspace supports you" className="workflow-guide"><ol><li><span>01</span><div><strong>Confirm the patient</strong><p>Use their record ID and review the longitudinal history.</p></div></li><li><span>02</span><div><strong>Build the clinical picture</strong><p>Capture measurements, weight, FBS or HbA1c and lipids. Leave unknown findings explicit.</p></div></li><li><span>03</span><div><strong>Review the recommendations</strong><p>Check the treatment options and sources, accept or adjust, and arrange follow-up.</p></div></li></ol><div className="guide-footer">Research software · adult noncommunicable disease care</div></Panel>
    </>}
  </>
}
function Stat({ icon, value, title, subtitle, onClick }: { icon: React.ReactNode; value: number; title: string; subtitle: string; onClick?: () => void }) {
  const body = <><div className="stat-top"><span>{title}</span><span className="stat-icon">{icon}</span></div><strong className="stat-value">{value.toLocaleString()}</strong><small>{subtitle}</small></>
  return onClick ? <button type="button" className="stat-card stat-card-link" onClick={onClick}>{body}</button> : <div className="stat-card">{body}</div>
}
