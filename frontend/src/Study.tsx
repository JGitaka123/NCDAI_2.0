import { useEffect, useState } from 'react'
import { api, message } from './api'
import { Field, Notice, Panel, PageHeader } from './components'
import type { Encounter, Patient, User } from './types'

type Values = Record<string, string | number | boolean | null>
type Observation = { id: string; encounter_id: string | null; revision: number; payload: Values }
type Definition = { key: string; label: string; type?: string; options?: string[]; required?: boolean; min?: number; max?: number }
const localDate = (value = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit' }).format(value)
const choices = (key: string, label: string, options: string[]): Definition => ({ key, label, options })
const number = (key: string, label: string, min: number, max: number, required = false): Definition => ({ key, label, type: 'number', min, max, required })
const dates = (key: string, label: string): Definition => ({ key, label, type: 'date', required: true })
const definitions: Record<string, Definition[]> = {
  enrolment: [dates('index_date', 'Index visit date'), choices('status', 'Participation status', ['pending','enrolled','declined','not_eligible','withdrawn']), { key: 'participation_documented', label: 'Participation documented under the approved protocol', type: 'checkbox' }],
  visit: [number('consultation_minutes','Total consultation time (minutes)',0.1,480), choices('timing_method','How was time measured?', ['not_recorded','observed','estimated']), choices('decision_changed','Did the support change your decision?', ['unknown','yes','no']), choices('workflow_issue','Main workflow issue', ['not_recorded','none','duplicate_entry','slow','connectivity','missing_data','other']), choices('language','Consultation language', ['not_recorded','English','Kiswahili','other']), number('helpfulness','Helpfulness (1 = lowest, 5 = highest)',1,5), choices('safety_screening','Safety screening at this visit', ['not_assessed','no_event_reported','event_reported'])],
  followup: [dates('contact_date','Follow-up contact / attempted contact date'), choices('status','Contact outcome',['completed','missed','unreachable','declined','died']), number('systolic_bp','Systolic BP (mmHg)',50,300), number('diastolic_bp','Diastolic BP (mmHg)',30,200), number('hba1c','HbA1c (%)',3,25), choices('hospitalisation','Hospital admission since index visit',['unknown','yes','no'])],
  safety: [dates('occurred_on','Incident date'), choices('severity','Severity',['near_miss','no_harm','mild','moderate','severe','death']), choices('category','Incident category',['unsafe_recommendation','missed_urgent_action','medication','delay','privacy','other']), choices('suspected_app_related','Suspected relation to NCDAI',['unknown','yes','no']), { key:'description',label:'What happened? Avoid names and contact details.',type:'textarea',required:true }, { key:'immediate_action',label:'Immediate action taken',type:'textarea',required:true }, choices('status','Incident status',['open','resolved'])],
  daily_tally: [dates('clinic_date','Clinic date'), number('eligible_visits','All eligible adult NCD visits',0,10000,true), number('app_used_visits','Visits using NCDAI',0,10000,true), number('non_use_connectivity','Not used: connectivity',0,10000,true), number('non_use_workload','Not used: workload',0,10000,true), number('non_use_declined','Not used: declined',0,10000,true), number('non_use_other','Not used: other reason',0,10000,true)],
}
function defaults(kind: string, date = localDate()): Values {
  const output: Values = { kind }
  for (const field of definitions[kind]) output[field.key] = field.options?.[0] ?? (field.type === 'date' ? date : field.type === 'checkbox' ? false : field.type === 'number' ? field.required ? 0 : null : '')
  if (kind === 'safety') output.incident_id = crypto.randomUUID()
  return output
}
const label = (text: string) => text.replaceAll('_',' ')

function RecordForm({ kind, records, patient, encounter, synthetic, onSaved, onDirtyChange }: { kind: string; records: Observation[]; patient?: Patient; encounter?: Encounter; synthetic: boolean; onSaved: () => Promise<void>; onDirtyChange: (value: boolean) => void }) {
  const [values,setValues] = useState<Values>(() => defaults(kind,kind==='enrolment' && encounter ? localDate(new Date(encounter.created_at)) : localDate()))
  const [previous,setPrevious] = useState<Observation | null>(null), [key,setKey] = useState(() => crypto.randomUUID()), [dirty,setDirty] = useState(false), [busy,setBusy] = useState(false), [error,setError] = useState(''), [success,setSuccess] = useState('')
  useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false) },[dirty,onDirtyChange])
  useEffect(() => { const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue='' } }; window.addEventListener('beforeunload',warn); return () => window.removeEventListener('beforeunload',warn) },[dirty])
  const candidates = records.filter(row => row.payload.kind===kind && (kind!=='visit' || row.encounter_id===encounter?.id))
  function edit(row: Observation | null) {
    if (dirty && !window.confirm('Discard unsaved study observations?')) return
    setPrevious(row); setValues(row ? {...row.payload} : defaults(kind)); setKey(crypto.randomUUID()); setDirty(false); setSuccess(''); setError('')
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('')
    try {
      const result = await api<Observation>('/study/records',{method:'POST',body:{idempotency_key:key,previous_id:previous?.id ?? null,patient_id:patient?.id ?? null,encounter_id:previous?.encounter_id ?? encounter?.id ?? null,synthetic,payload:values}})
      setPrevious(result); setKey(crypto.randomUUID()); setDirty(false); setSuccess(`Study observation saved · revision ${result.revision}.`)
      await onSaved()
    } catch(error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <form className="study-form" onSubmit={save}>
    {candidates.length>0 && <Field label="Saved observation to correct"><select value={previous?.id ?? ''} onChange={event => edit(candidates.find(row=>row.id===event.target.value) ?? null)} disabled={busy}><option value="">New observation</option>{candidates.map(row=><option key={row.id} value={row.id}>{String(row.payload.clinic_date ?? row.payload.contact_date ?? row.payload.occurred_on ?? row.payload.index_date ?? 'This visit')} · revision {row.revision}</option>)}</select></Field>}
    {kind==='enrolment' && <p>One index visit per patient. Record participation under the approved protocol. The index date, encounter and baseline are fixed after saving; select the saved observation to update participation status.</p>}
    {kind==='safety' && <Notice tone="warning">Use the hospital’s immediate incident and emergency escalation process. Saving this report does not send a notification.</Notice>}
    {kind==='daily_tally' && <p>Enter whole-clinic totals once per day. Count visits, including repeat visits. App use plus all reasons for non-use must equal eligible visits. For a correction, select the saved day above.</p>}
    <div className="form-grid">{definitions[kind].map(field=><Field key={field.key} label={field.label}>{field.options ? <select disabled={busy} value={String(values[field.key])} onChange={event=>{setValues({...values,[field.key]:event.target.value});setDirty(true);setKey(crypto.randomUUID())}}>{field.options.map(option=><option key={option} value={option}>{label(option)}</option>)}</select> : field.type==='textarea' ? <textarea disabled={busy} minLength={10} maxLength={2000} required value={String(values[field.key])} onChange={event=>{setValues({...values,[field.key]:event.target.value});setDirty(true);setKey(crypto.randomUUID())}}/> : <input disabled={busy || (kind==='enrolment' && field.key==='index_date' && !!previous)} type={field.type} min={field.min} max={field.type==='date'?localDate():field.max} step={field.key==='helpfulness' || kind==='daily_tally' ? 1 : 'any'} required={field.required} checked={field.type==='checkbox'?Boolean(values[field.key]):undefined} value={field.type==='checkbox'?undefined:String(values[field.key]??'')} onChange={event=>{setValues({...values,[field.key]:field.type==='checkbox'?event.target.checked:field.type==='number'?event.target.value===''?null:Number(event.target.value):event.target.value});setDirty(true);setKey(crypto.randomUUID())}}/>}</Field>)}</div>
    {error && <Notice tone="error">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}
    <div className="form-actions"><button className="button button-primary" disabled={busy}>{busy?'Saving…':previous?'Save correction':'Save study observation'}</button><button type="button" className="button button-secondary" disabled={busy} onClick={()=>{void onSaved().catch(error=>setError(message(error)))}}>Reload saved observations</button></div>
  </form>
}

export function StudyCase({ patient, encounter, onDirtyChange }: { patient: Patient; encounter: Encounter; onDirtyChange: (value: boolean) => void }) {
  const [records,setRecords] = useState<Observation[]>([]), [kind,setKind] = useState('enrolment'), [dirty,setDirty] = useState(false), [error,setError] = useState(''), [opened,setOpened] = useState(false)
  async function load() { setRecords(await api<Observation[]>(`/study/patients/${patient.id}/records`)) }
  useEffect(()=>{onDirtyChange(dirty);return()=>onDirtyChange(false)},[dirty,onDirtyChange])
  return <Panel title="Study observations" subtitle="Record participation, workflow, follow-up and safety separately from clinical care."><button className="button button-secondary" onClick={()=>{if(opened){if(dirty&&!window.confirm('Discard unsaved study observations?'))return;setOpened(false);setDirty(false)}else{void load().then(()=>{setError('');setOpened(true)}).catch(error=>setError(message(error)))}}}>{opened?'Close study observations':'Open study observations'}</button>{error&&<Notice tone="error">{error}</Notice>}{opened&&<><Field label="Observation type"><select value={kind} onChange={event=>{if(dirty&&!window.confirm('Discard unsaved study observations?'))return;setKind(event.target.value)}}>{['enrolment','visit','followup','safety'].map(k=><option key={k} value={k}>{label(k)}</option>)}</select></Field><RecordForm key={kind} kind={kind} records={records} patient={patient} encounter={encounter} synthetic={patient.synthetic} onSaved={load} onDirtyChange={setDirty}/></>}</Panel>
}

type Rate = {numerator:number;denominator:number;percent:number|null}
type Summary = {patients_seen:number;encounters:number;enrolled_patients:number;adoption:Rate;followup_completion:Rate;review_completion:Rate;safety_reports:number;open_safety_reports:number;clinic_days_reported:number;visit_observation_coverage:Rate;consultation_minutes:Record<string,{n:number;median:number|null}>;limits:string[]}
function download(data: unknown, name: string) { const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000) }
const showRate = (r:Rate) => `${r.numerator}/${r.denominator} (${r.percent===null?'not yet measurable':`${r.percent}%`})`

export default function StudyWorkspace({ user,onDirtyChange }: { user:User;onDirtyChange:(value:boolean)=>void }) {
  const [synthetic,setSynthetic]=useState(!user.clinical_testing), [start,setStart]=useState(localDate(new Date(Date.now()-55*86400000))), [end,setEnd]=useState(localDate()), [records,setRecords]=useState<Observation[]>([]), [summary,setSummary]=useState<Summary|null>(null), [error,setError]=useState(''), [busy,setBusy]=useState(false), [dirty,setDirty]=useState(false)
  const privileged=['admin','supervisor'].includes(user.role)
  useEffect(()=>{onDirtyChange(dirty);return()=>onDirtyChange(false)},[dirty,onDirtyChange])
  async function load() { setBusy(true);setError('');setSummary(null);try{const query=`?start=${start}&end=${end}&synthetic=${synthetic}`;setRecords(await api<Observation[]>(`/study/tallies${query}`));if(privileged)setSummary(await api<Summary>(`/study/summary${query}`))}catch(error){setError(message(error))}finally{setBusy(false)} }
  async function exportCohort() { setBusy(true);setError('');try{download(await api(`/study/export?start=${start}&end=${end}&synthetic=${synthetic}`),`ncdai-protected-study-${start}-${end}.json`)}catch(error){setError(message(error))}finally{setBusy(false)} }
  return <><PageHeader eyebrow="EVIDENCE COLLECTION" title="Study metrics" description="Use unique patients for recruitment and visits for clinic adoption. Clinical and synthetic records are reported separately."/>
    <Panel title="Reporting window"><div className="form-grid"><Field label="From"><input type="date" value={start} max={end} disabled={busy||dirty} onChange={e=>{setStart(e.target.value);setSummary(null);setRecords([])}}/></Field><Field label="Through"><input type="date" value={end} max={localDate()} disabled={busy||dirty} onChange={e=>{setEnd(e.target.value);setSummary(null);setRecords([])}}/></Field><Field label="Record class"><select value={String(synthetic)} disabled={busy||dirty} onChange={e=>{setSynthetic(e.target.value==='true');setSummary(null);setRecords([])}}><option value="true">Synthetic practice records</option>{user.clinical_testing&&<option value="false">Clinical records</option>}</select></Field></div><button className="button button-primary" onClick={()=>void load()} disabled={busy}>{busy?'Loading…':'Load study readout'}</button></Panel>
    {error&&<Notice tone="error">{error}</Notice>}
    {summary&&<Panel title="Descriptive feasibility readout"><dl className="study-metrics"><dt>Unique patients seen / visits</dt><dd>{summary.patients_seen} / {summary.encounters}</dd><dt>Currently enrolled patients</dt><dd>{summary.enrolled_patients}</dd><dt>App use among eligible visits on reported days</dt><dd>{showRate(summary.adoption)} · {summary.clinic_days_reported} days reported</dd><dt>Completed follow-up among those due</dt><dd>{showRate(summary.followup_completion)}</dd><dt>Saved encounters with clinician review</dt><dd>{showRate(summary.review_completion)}</dd><dt>Visits with workflow observations</dt><dd>{showRate(summary.visit_observation_coverage)}</dd><dt>Reported safety events / still open</dt><dd>{summary.safety_reports} / {summary.open_safety_reports}</dd>{Object.entries(summary.consultation_minutes).map(([method,value])=><div key={method}><dt>{label(method)} consultation time</dt><dd>{value.median??'Not recorded'} minutes · n={value.n}</dd></div>)}</dl><button className="button button-secondary" onClick={()=>download(summary,`ncdai-aggregate-${start}-${end}.json`)}>Download aggregate readout</button>{user.role==='supervisor'&&<button disabled={busy} className="button button-secondary" onClick={()=>void exportCohort()}>Download protected cohort extract</button>}<p>Patient-level extracts are pseudonymised health data, not anonymous. Store them only in approved study storage.</p><ul>{summary.limits.map(text=><li key={text}>{text}</li>)}</ul></Panel>}
    <Panel title="Daily clinic tally"><RecordForm key={`${synthetic}-${start}-${end}`} kind="daily_tally" records={records} synthetic={synthetic} onSaved={load} onDirtyChange={setDirty}/></Panel>
  </>
}
