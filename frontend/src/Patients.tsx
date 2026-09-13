import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, Plus, Search, UserRound, X } from 'lucide-react'
import { api, message } from './api'
import { ageInYears, formatDate, titleCase } from './clinical'
import { Empty, Field, Loading, Notice, PageHeader, Panel } from './components'
import type { Patient } from './types'

export default function Patients({ onSelect, clinicalTesting = false }: { clinicalTesting?: boolean; onSelect: (patient: Patient) => void }) {
  const [patients, setPatients] = useState<Patient[]>([]), [search, setSearch] = useState(''), [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [register, setRegister] = useState(false), [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    api<Patient[]>(`/patients?search=${encodeURIComponent(query)}`, { signal: controller.signal }).then(setPatients).catch(error => { if (error.name !== 'AbortError') setError(message(error)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [query, revision])
  return <>
    <PageHeader eyebrow="PATIENT WORKSPACE" title="Every visit, connected." description="Find a patient to view their history or begin a new encounter." action={<button className="button button-primary" onClick={() => setRegister(true)}><Plus size={18} /> Register patient</button>} />
    {register && <RegisterPatient clinicalTesting={clinicalTesting} onCancel={() => setRegister(false)} onCreated={patient => { setRegister(false); onSelect(patient) }} />}
    <Panel>
      <form className="search-bar" onSubmit={event => { event.preventDefault(); setQuery(search); setRevision(r => r + 1) }}>
        <Search size={20} aria-hidden="true" /><label className="sr-only" htmlFor="patient-search">Search patients by name or record ID</label><input id="patient-search" placeholder="Search by name or record ID…" value={search} onChange={event => setSearch(event.target.value)} /><button className="button button-secondary" type="submit">Search</button>
      </form>
      <div className="list-heading"><h2>{query ? 'Search results' : 'Patient directory'}</h2><span className="muted">{patients.length} shown · facility records</span></div>
      {loading ? <Loading label="Finding patient records…" /> : error ? <div className="panel-body"><Notice tone="error">{error}</Notice><button className="button button-secondary" onClick={() => setRevision(r => r + 1)}>Try again</button></div> : patients.length === 0 ? <Empty title={query ? 'No matching patients' : 'Your patient directory is ready'}>{query ? 'Try another name or record ID.' : clinicalTesting ? 'Register the patient after confirming their identity and the hospital testing workflow.' : 'Register a synthetic patient to explore the complete care workflow.'}</Empty> : <div className="table-wrap"><table><thead><tr><th>Patient</th><th>Record ID</th><th>Age / sex</th><th>Date of birth</th><th><span className="sr-only">Open record</span></th></tr></thead><tbody>{patients.map(patient => <tr key={patient.id}><td><button className="patient-link" onClick={() => onSelect(patient)}><span className="avatar"><UserRound size={19} /></span><span><strong>{patient.given_name} {patient.family_name}</strong><small>{patient.synthetic ? 'Synthetic record' : 'Clinical testing record'}</small></span></button></td><td className="mono">{patient.external_id}</td><td>{ageInYears(patient.date_of_birth)} years · {titleCase(patient.sex)}</td><td>{formatDate(`${patient.date_of_birth}T00:00:00`)}</td><td><button className="icon-button" aria-label={`Open ${patient.given_name} ${patient.family_name}`} onClick={() => onSelect(patient)}><ArrowRight size={19} /></button></td></tr>)}</tbody></table></div>}
    </Panel>
    <div className="context-note">Confirm the patient’s record ID before entering or reviewing clinical information.</div>
  </>
}

function RegisterPatient({ onCancel, onCreated, clinicalTesting }: { clinicalTesting: boolean; onCancel: () => void; onCreated: (patient: Patient) => void }) {
  const [values, setValues] = useState({ external_id: '', given_name: '', family_name: '', date_of_birth: '', sex: 'unknown', phone: '' })
  const [recordType, setRecordType] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  function field(key: keyof typeof values, value: string) { setValues(v => ({ ...v, [key]: value })) }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if ((ageInYears(values.date_of_birth) < 18 || ageInYears(values.date_of_birth) > 120)) { setError('This release supports adults aged 18 through 120 years.'); return }
    setBusy(true)
    try { onCreated(await api<Patient>('/patients', { method: 'POST', body: { ...values, phone: values.phone || undefined, synthetic: !clinicalTesting || recordType === 'synthetic' } })) } catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <Panel className="registration-panel">
    <div className="panel-heading panel-heading-row"><div><h2>{clinicalTesting ? 'Register patient' : 'Register a synthetic patient'}</h2><p>{clinicalTesting ? 'Select the record type explicitly. Confirm identity before entering clinical information.' : 'Use fictional details only in this research preview.'}</p></div><button className="icon-button" aria-label="Close registration" onClick={onCancel}><X size={20} /></button></div>
    <form className="panel-body" onSubmit={submit}>
      {error && <Notice tone="error">{error}</Notice>}
      {clinicalTesting && <Field label="Record type"><select required value={recordType} onChange={e => setRecordType(e.target.value)}><option value="">Choose before entering details</option><option value="clinical">Real patient — supervised clinical testing</option><option value="synthetic">Fictional case — staff rehearsal</option></select></Field>}
      <div className="form-grid three-cols"><Field label="Record ID"><input value={values.external_id} onChange={e => field('external_id', e.target.value)} maxLength={80} title="Start with a letter or number; use letters, numbers, dots, hyphens, slashes or underscores." required autoFocus /></Field><Field label="Given name"><input value={values.given_name} onChange={e => field('given_name', e.target.value)} maxLength={100} required /></Field><Field label="Family name"><input value={values.family_name} onChange={e => field('family_name', e.target.value)} maxLength={100} required /></Field><Field label="Date of birth" hint="Adult patients only, 18 years and over"><input type="date" value={values.date_of_birth} onChange={e => field('date_of_birth', e.target.value)} max={new Date().toISOString().slice(0, 10)} required /></Field><Field label="Sex recorded"><select value={values.sex} onChange={e => field('sex', e.target.value)}><option value="unknown">Unknown / not recorded</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></Field><Field label="Phone (optional)"><input type="tel" value={values.phone} onChange={e => field('phone', e.target.value)} maxLength={30} /></Field></div>
      <div className="form-actions"><button className="button button-secondary" type="button" onClick={onCancel}>Cancel</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create patient record'}</button></div>
    </form>
  </Panel>
}
