import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, Plus, Trash2 } from 'lucide-react'
import { api, message } from './api'
import { emptyDosingContext, numericInput, titleCase } from './clinical'
import { Field, Loading, Notice } from './components'
import type { ClinicalData, DosingCatalogue, DosingContext, DosingRequest, TriState } from './types'

export default function DoseSupport({ data, onChange, disabled }: { data: ClinicalData; onChange: (data: ClinicalData) => void; disabled: boolean }) {
  const requests = data.dosing_requests ?? [], context = { ...emptyDosingContext(), ...data.dosing_context }
  const [open, setOpen] = useState(requests.length > 0), [catalogue, setCatalogue] = useState<DosingCatalogue | null>(null), [loading, setLoading] = useState(false), [error, setError] = useState(''), [attempt, setAttempt] = useState(0), [selected, setSelected] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController(); let active = true
    setLoading(true); setError('')
    api<DosingCatalogue>('/dosing/catalogue', { signal: controller.signal }).then(value => { if (active) setCatalogue(value) }).catch(error => { if (active) setError(message(error)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [open, attempt])
  const updateRequests = (value: DosingRequest[]) => onChange({ ...data, dosing_requests: value, dosing_context: context })
  const updateContext = <K extends keyof DosingContext>(key: K, value: DosingContext[K]) => onChange({ ...data, dosing_context: { ...context, [key]: value } })
  function add() {
    const medicine = catalogue?.medicines.find(item => item.medicine_id === selected)
    if (!medicine || requests.length >= 5 || requests.some(item => item.medicine_id === selected)) return
    updateRequests([...requests, { medicine_id: medicine.medicine_id, indication: medicine.indication, proposed_dose_mg: null, frequency_per_day: null }]); setSelected('')
  }
  function update(index: number, patch: Partial<DosingRequest>) { updateRequests(requests.map((item, i) => i === index ? { ...item, ...patch } : item)) }
  return <details className="intake-section" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary><span><span className="section-number">06</span> Starting-dose check</span><span className="summary-tag">Optional · {requests.length} selected</span></summary>
    <div className="intake-section-content">
      <div className="dose-guide">
        <p><strong>What it does:</strong> when you plan to <em>start</em> a medicine, it shows the Kenya MOH starting dose and maximum daily dose (Table 4 and section 4.5), or checks a dose you propose against them. It does not prescribe or change the current medicine list.</p>
        <ol>
          <li><strong>Choose</strong> the medicine you are considering starting.</li>
          <li><strong>Optionally enter</strong> your proposed dose and doses per day to have them checked.</li>
          <li><strong>Complete</strong> the safety questions below, then select <em>Assess & review</em>. The result appears on the Assessment tab with the dose, or the reasons it was withheld.</li>
        </ol>
        <p className="field-note">For medicine suggestions when a patient is untreated or above target, see the treatment recommendations on the Assessment tab; this section only checks starting doses.</p>
      </div>
      {requests.length > 0 && <Readiness data={data} context={context} />}
      {loading && <Loading label="Loading medicine catalogue…" />}
      {error && <Notice tone="error">Medicine catalogue unavailable. {error} The rest of the intake remains available. <button type="button" className="text-button" disabled={disabled || loading} onClick={() => setAttempt(value => value + 1)}>Retry catalogue</button></Notice>}
      {catalogue && <details className="dose-scope"><summary>{catalogue.medicines.length} medicines covered · scope and exclusions</summary><p className="field-note">{catalogue.scope_note}</p><ul className="dose-catalogue-list">{(['hypertension', 'type_2_diabetes'] as const).map(indication => <li key={indication}><strong>{titleCase(indication)}:</strong> {catalogue.medicines.filter(item => item.indication === indication).map(item => item.name).join(', ')}</li>)}</ul><p className="field-note">Catalogue version: {catalogue.version}</p></details>}
      <div className="dosing-picker"><Field label="Catalogue medicine"><select value={selected} disabled={disabled || loading || !!error || !catalogue || requests.length >= 5} onChange={event => setSelected(event.target.value)}><option value="">Choose a medicine</option>{(['hypertension', 'type_2_diabetes'] as const).map(indication => <optgroup key={indication} label={titleCase(indication)}>{catalogue?.medicines.filter(item => item.indication === indication).map(item => <option key={item.medicine_id} value={item.medicine_id} disabled={requests.some(request => request.medicine_id === item.medicine_id)}>{item.name} · {item.formulation}</option>)}</optgroup>)}</select></Field><button type="button" className="button button-secondary" disabled={disabled || !selected || loading || !!error || requests.length >= 5} onClick={add}><Plus size={16} />Add to dose check</button></div>
      {requests.length === 5 && <p className="field-note" role="status">Five medicines selected. Remove one before adding another.</p>}
      {requests.map((request, index) => {
        const medicine = catalogue?.medicines.find(item => item.medicine_id === request.medicine_id)
        return <fieldset className="dose-request" key={request.medicine_id} disabled={disabled}><legend>Reference check {index + 1}: {medicine?.name ?? titleCase(request.medicine_id)}</legend>
          <div className="dose-request-heading"><p>{titleCase(request.indication)}{medicine && <> · {medicine.route} · {medicine.formulation} · Unit: {medicine.unit}</>}</p><button type="button" className="icon-button danger-text" aria-label={`Remove reference check ${index + 1}`} onClick={() => updateRequests(requests.filter((_, i) => i !== index))}><Trash2 size={18} /></button></div>
          <div className="form-grid two-cols"><Field label={`Proposed dose per administration ${index + 1} (mg)`}><input type="number" min={0.001} step="any" inputMode="decimal" value={request.proposed_dose_mg ?? ''} required={request.frequency_per_day != null} onChange={event => update(index, { proposed_dose_mg: numericInput(event.target.value) })} placeholder="Optional" /></Field><Field label={`Proposed administrations per day ${index + 1}`}><input type="number" min={1} max={24} step={1} inputMode="numeric" value={request.frequency_per_day ?? ''} required={request.proposed_dose_mg != null} onChange={event => update(index, { frequency_per_day: numericInput(event.target.value) })} placeholder="Optional" /></Field></div>
          <p className="field-note">{medicine?.clinical_checks}</p><p className="field-note">Leave both proposed values blank to request the reference only. To check a proposed regimen, enter both values. Formulation and route are fixed by the catalogue.</p>
        </fieldset>
      })}
      {requests.length > 0 && <fieldset className="dose-context" disabled={disabled}><legend>Safety context for this encounter</legend><p className="field-note">Unknown answers remain unknown and can prevent a reference from being shown. Confirm pregnancy status, current medicines, allergies and kidney results in the intake above.</p>
        <div className="form-grid three-cols">
          {([['hepatic_impairment', 'Hepatic impairment'], ['acute_illness', 'Acute illness'], ['dialysis', 'Dialysis'], ['frailty', 'Frailty']] as const).map(([key, label]) => <Field key={key} label={label}><select value={context[key]} onChange={event => updateContext(key, event.target.value as TriState)}><option value="unknown">Unknown / not assessed</option><option value="yes">Yes</option><option value="no">No, assessed</option></select></Field>)}
          <Field label="Breastfeeding"><select value={context.breastfeeding} onChange={event => updateContext('breastfeeding', event.target.value as DosingContext['breastfeeding'])}><option value="unknown">Unknown / not assessed</option><option value="yes">Yes</option><option value="no">No, assessed</option><option value="not_applicable">Not applicable</option></select></Field>
          <Field label="Kidney results observed at" hint="Local date and time for the recorded renal results"><input type="datetime-local" value={localDateTime(context.renal_observed_at)} max={localDateTime(new Date().toISOString())} onChange={event => updateContext('renal_observed_at', event.target.value ? new Date(event.target.value).toISOString() : null)} /></Field>
        </div>
        <Field label="Potassium result observed at" hint="Date of the potassium measurement; required separately for ACE inhibitor/ARB references"><input type="datetime-local" value={localDateTime(context.potassium_observed_at ?? null)} onChange={event => updateContext('potassium_observed_at', event.target.value ? new Date(event.target.value).toISOString() : null)} /></Field>
        <label className="review-checkbox"><input type="checkbox" checked={context.contraindications_reviewed} onChange={event => updateContext('contraindications_reviewed', event.target.checked)} /><span><strong>No unresolved contraindications after review</strong><small>I have reviewed the medicine-specific checks above, complete prescribing information and history; none of those exclusions applies.</small></span></label>
        <label className="review-checkbox"><input type="checkbox" checked={context.interactions_reviewed} onChange={event => updateContext('interactions_reviewed', event.target.checked)} /><span><strong>No unresolved interactions after review</strong><small>Includes medicines and interactions outside this limited catalogue.</small></span></label>
      </fieldset>}
    </div>
  </details>
}

function localDateTime(value: string | null): string { if (!value) return ''; const date = new Date(value); if (Number.isNaN(date.getTime())) return ''; return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16) }

// Intake prerequisites only; the server makes the eligibility decision and explains any withholding.
function Readiness({ data, context }: { data: ClinicalData; context: DosingContext }) {
  const recent = (value: string | null | undefined, days: number) => !!value && Date.now() - new Date(value).getTime() <= days * 86_400_000
  const needsPotassium = (data.dosing_requests ?? []).some(request => !['amlodipine_tablet', 'felodipine_pr_tablet', 'metformin_ir_tablet'].includes(request.medicine_id))
  const items: [boolean, string][] = [
    [data.medications_reviewed && data.allergies_reviewed && data.symptoms_reviewed, 'Medicines, allergies and symptoms marked reviewed (sections 02 and 05)'],
    [data.symptoms.length === 0 && data.acutely_unwell === 'no' && data.acute_kidney_injury === 'no', 'No current symptoms; acutely unwell and acute kidney injury answered “No”'],
    [['no', 'not_applicable'].includes(data.pregnancy_status), 'Pregnancy status recorded as not pregnant or not applicable'],
    [data.egfr != null && data.egfr >= 60 && data.known_ckd === 'no' && recent(context.renal_observed_at, 7), 'eGFR ≥60, no known CKD, kidney result dated within 7 days'],
    ...(needsPotassium ? [[data.potassium != null && data.potassium >= 3.5 && data.potassium <= 5 && recent(context.potassium_observed_at, 7), 'Potassium 3.5–5.0 mmol/L, dated within 7 days'] as [boolean, string]] : []),
    [data.systolic_bp != null && data.diastolic_bp != null && recent(data.observed_at, 1), 'Blood pressure recorded with an observation time in the last 24 hours'],
    [data.medicine_availability === 'available', 'Medicine availability verified (section 05)'],
    [(['hepatic_impairment', 'acute_illness', 'dialysis', 'frailty'] as const).every(key => context[key] === 'no') && ['no', 'not_applicable'].includes(context.breastfeeding) && context.contraindications_reviewed && context.interactions_reviewed, 'Safety questions below all answered'],
  ]
  const ready = items.filter(([done]) => done).length
  return <div className="dose-readiness" aria-label="Dose check readiness"><strong>Before a dose can be shown · {ready} of {items.length} complete</strong><ul>{items.map(([done, label]) => <li key={label} className={done ? 'done' : ''}>{done ? <CheckCircle2 size={15} aria-hidden="true" /> : <Circle size={15} aria-hidden="true" />}<span>{label}</span></li>)}</ul><small>Age 18–64 and a documented diagnosis are also required. Other limits are explained in the result.</small></div>
}
