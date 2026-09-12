import { Plus, Trash2 } from 'lucide-react'
import type { ClinicalData, Medication, TriState } from './types'
import { medicineNames, numericInput, symptoms } from './clinical'
import { Field } from './components'
import DoseSupport from './DoseSupport'

export default function ClinicalIntake({ data, onChange, disabled }: { data: ClinicalData; onChange: (data: ClinicalData) => void; disabled: boolean }) {
  const change = <K extends keyof ClinicalData>(key: K, value: ClinicalData[K]) => onChange({ ...data, [key]: value })
  function med(index: number, patch: Partial<Medication>) { change('medications', data.medications.map((item, i) => i === index ? { ...item, ...patch } : item)) }
  return <fieldset className="intake-fieldset" disabled={disabled}>
    <div className="intake-intro"><strong>Today’s clinical picture</strong><p>Blank measurements remain unknown. Confirm findings and lists explicitly before assessment.</p></div>
    <details className="intake-section" open><summary><span><span className="section-number">01</span> Measurements & vital signs</span><span className="summary-tag">Units required</span></summary><div className="intake-section-content">
      <div className="form-grid three-cols">
        <NumberField label="Systolic BP" unit="mmHg" value={data.systolic_bp} min={40} max={300} onChange={v => change('systolic_bp', v)} />
        <NumberField label="Diastolic BP" unit="mmHg" value={data.diastolic_bp} min={20} max={200} onChange={v => change('diastolic_bp', v)} />
        <NumberField label="Pulse" unit="beats/min" value={data.pulse} min={20} max={250} onChange={v => change('pulse', v)} />
        <NumberField label="Repeat systolic BP" unit="mmHg" value={data.repeat_systolic_bp} min={40} max={300} onChange={v => change('repeat_systolic_bp', v)} />
        <NumberField label="Repeat diastolic BP" unit="mmHg" value={data.repeat_diastolic_bp} min={20} max={200} onChange={v => change('repeat_diastolic_bp', v)} />
        <Field label="Measurements observed at" hint="Local date and time; leaving blank means unrecorded"><input type="datetime-local" value={toLocalDateTime(data.observed_at)} onChange={e => change('observed_at', e.target.value ? new Date(e.target.value).toISOString() : null)} /></Field>
        <NumberField label="Oxygen saturation" unit="%" value={data.oxygen_saturation} min={30} max={100} onChange={v => change('oxygen_saturation', v)} />
        <NumberField label="Respiratory rate" unit="breaths/min" value={data.respiratory_rate} min={4} max={80} onChange={v => change('respiratory_rate', v)} />
      </div>
      <p className="field-note">Repeat BP values are a separate measurement, not a replacement for the first reading. Reassess according to the clinical context.</p>
    </div></details>
    <details className="intake-section" open><summary><span><span className="section-number">02</span> Symptoms & warning signs</span><span className="summary-tag">{data.symptoms.length} recorded</span></summary><div className="intake-section-content">
      <p className="field-note">Select symptoms reported or observed now. An unchecked item is not a confirmed negative finding.</p>
      <div className="form-grid two-cols">
        <HistoryField label="Acutely unwell now" value={data.acutely_unwell ?? 'unknown'} onChange={v => change('acutely_unwell', v)} />
        <HistoryField label="Acute kidney injury suspected or confirmed" value={data.acute_kidney_injury ?? 'unknown'} onChange={v => change('acute_kidney_injury', v)} />
      </div>
      <div className="symptom-grid">{symptoms.map(([value, label]) => <label key={value} className={`check-tile ${data.symptoms.includes(value) ? 'check-tile-selected' : ''}`}><input type="checkbox" checked={data.symptoms.includes(value)} onChange={e => change('symptoms', e.target.checked ? [...data.symptoms, value] : data.symptoms.filter(s => s !== value))} /><span>{label}</span></label>)}</div>
      <label className="review-checkbox"><input type="checkbox" checked={data.symptoms_reviewed} onChange={e => change('symptoms_reviewed', e.target.checked)} /><span><strong>Symptom assessment completed</strong><small>{data.symptoms.length ? 'The selected symptoms reflect the assessment.' : 'If checked with no symptoms selected, none of the listed symptoms were reported or observed.'}</small></span></label>
    </div></details>
    <details className="intake-section"><summary><span><span className="section-number">03</span> NCD history & context</span><span className="summary-tag">6 disease groups</span></summary><div className="intake-section-content">
      <div className="form-grid three-cols">
        <HistoryField label="Known hypertension" value={data.known_hypertension} onChange={v => change('known_hypertension', v)} />
        <HistoryField label="Known diabetes" value={data.known_diabetes} onChange={v => change('known_diabetes', v)} />
        <HistoryField label="Known asthma" value={data.known_asthma} onChange={v => change('known_asthma', v)} />
        <HistoryField label="Known COPD" value={data.known_copd} onChange={v => change('known_copd', v)} />
        <HistoryField label="Known chronic kidney disease" value={data.known_ckd} onChange={v => change('known_ckd', v)} />
        <HistoryField label="Known cancer" value={data.known_cancer} onChange={v => change('known_cancer', v)} />
        <Field label="Pregnancy status"><select value={data.pregnancy_status} onChange={e => change('pregnancy_status', e.target.value as ClinicalData['pregnancy_status'])}><option value="unknown">Unknown / not assessed</option><option value="no">Not pregnant</option><option value="yes">Pregnant</option><option value="not_applicable">Not applicable</option></select></Field>
        <Field label="Tobacco use"><select value={data.tobacco_use} onChange={e => change('tobacco_use', e.target.value as ClinicalData['tobacco_use'])}><option value="unknown">Unknown / not assessed</option><option value="current">Current</option><option value="former">Former</option><option value="never">Never</option></select></Field>
      </div>
      <p className="field-note">Cancer support is limited to warning signs and referral considerations. This workspace does not provide oncology treatment plans.</p>
    </div></details>
    <details className="intake-section"><summary><span><span className="section-number">04</span> Laboratory results</span><span className="summary-tag">Diabetes & renal safety</span></summary><div className="intake-section-content">
      <div className="form-grid three-cols">
        <NumberField label="HbA1c" unit="%" value={data.hba1c} min={2} max={25} step="0.1" onChange={v => change('hba1c', v)} />
        <NumberField label="Blood glucose" unit={data.glucose_unit} value={data.glucose} min={0.1} max={data.glucose_unit === 'mmol/L' ? 83.3 : 1500} step="0.1" onChange={v => change('glucose', v)} />
        <Field label="Glucose unit" hint="Changing units does not convert the entered value"><select value={data.glucose_unit} onChange={e => { change('glucose_unit', e.target.value as ClinicalData['glucose_unit']) }}><option value="mmol/L">mmol/L</option><option value="mg/dL">mg/dL</option></select></Field>
        <NumberField label="eGFR" unit="mL/min/1.73 m²" value={data.egfr} min={0} max={200} step="0.1" onChange={v => change('egfr', v)} />
        <NumberField label="Potassium" unit="mmol/L" value={data.potassium} min={1} max={10} step="0.1" onChange={v => change('potassium', v)} />
      </div>
      <p className="field-note">Confirm when each result was obtained. Results with uncertain timing require clinician verification. Record the renal result time below when requesting a medicine reference check.</p>
    </div></details>
    <details className="intake-section" open><summary><span><span className="section-number">05</span> Medicines & allergies</span><span className="summary-tag">Reconciliation</span></summary><div className="intake-section-content">
      <div className="subsection-heading"><div><h3>Current medicines</h3><p>Record what the patient is actually taking.</p></div><button type="button" className="button button-secondary button-small" onClick={() => change('medications', [...data.medications, { code: '', name: '', dose: null, unit: '', frequency: '' }])}><Plus size={16} /> Add medicine</button></div>
      <datalist id="medication-options">{medicineNames.map(name => <option key={name} value={name} />)}</datalist>
      {data.medications.length === 0 && <div className="empty-inline">{data.medications_reviewed ? 'No current medicines recorded after review.' : 'Medication list not yet reconciled.'}</div>}
      {data.medications.map((medication, index) => <div className="medication-row" key={index}>
        <Field label={`Medicine ${index + 1}`}><input list="medication-options" value={medication.name} required onChange={e => med(index, { name: e.target.value, code: e.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/_$/, '') })} placeholder="Medicine name" /></Field>
        <Field label="Dose"><input type="number" inputMode="decimal" min={0.001} max={100000} step="any" value={medication.dose ?? ''} onChange={e => med(index, { dose: numericInput(e.target.value) })} placeholder="e.g. 500" /></Field>
        <Field label="Unit"><input value={medication.unit ?? ''} onChange={e => med(index, { unit: e.target.value })} placeholder="e.g. mg" /></Field>
        <Field label="Frequency"><input value={medication.frequency ?? ''} onChange={e => med(index, { frequency: e.target.value })} placeholder="e.g. twice daily" /></Field>
        <button className="icon-button danger-text" type="button" aria-label={`Remove medicine ${index + 1}`} onClick={() => change('medications', data.medications.filter((_, i) => i !== index))}><Trash2 size={18} /></button>
      </div>)}
      <label className="review-checkbox"><input type="checkbox" checked={data.medications_reviewed} onChange={e => change('medications_reviewed', e.target.checked)} /><span><strong>Medication list reviewed</strong><small>An empty, unreviewed list means unknown medication use.</small></span></label>
      <div className="form-grid two-cols"><Field label="Medicine adherence"><select value={data.adherence} onChange={e => change('adherence', e.target.value as ClinicalData['adherence'])}><option value="unknown">Unknown / not assessed</option><option value="taking">Taking as reported</option><option value="missed">Missed doses reported</option></select></Field><Field label="Medicine availability"><select value={data.medicine_availability} onChange={e => change('medicine_availability', e.target.value as ClinicalData['medicine_availability'])}><option value="unknown">Unknown / not verified</option><option value="available">Available, verified</option><option value="limited">Limited or unavailable</option></select></Field></div>
      <div className="allergy-entry"><Field label="Allergies and reactions" hint="One entry per line. Include the substance and reaction where known."><textarea rows={3} value={data.allergies.join('\n')} onChange={e => change('allergies', e.target.value.split('\n'))} placeholder="e.g. enalapril — angioedema" /></Field><label className="review-checkbox"><input type="checkbox" checked={data.allergies_reviewed} onChange={e => change('allergies_reviewed', e.target.checked)} /><span><strong>Allergy status reviewed</strong><small>Check only after review. An empty, reviewed list means no known allergies were reported.</small></span></label></div>
      <p className="field-note">Medication safety checks cover a limited catalogue. Unlisted medicines, interactions and dose suitability require manual clinical review.</p>
    </div></details>
    <DoseSupport data={data} onChange={onChange} disabled={disabled} />
    <details className="intake-section"><summary><span><span className="section-number">07</span> Consultation notes</span><span className="summary-tag">Additional context</span></summary><div className="intake-section-content"><Field label="Clinical notes" hint="Notes are retained in the record. Structured fields drive the safety rules; critical findings must be entered above."><textarea rows={5} maxLength={10000} value={data.notes} onChange={e => change('notes', e.target.value)} placeholder="Patient priorities, relevant history, examination, context and follow-up considerations…" /></Field></div></details>
  </fieldset>
}

function NumberField({ label, unit, value, min, max, step = '1', onChange }: { label: string; unit: string; value: number | null; min: number; max: number; step?: string; onChange: (value: number | null) => void }) {
  return <Field label={`${label} (${unit})`}><input type="number" inputMode="decimal" value={value ?? ''} min={min} max={max} step={step} placeholder="Not measured" onChange={e => onChange(numericInput(e.target.value))} /></Field>
}
function HistoryField({ label, value, onChange }: { label: string; value: TriState; onChange: (value: TriState) => void }) {
  return <Field label={label}><select value={value} onChange={e => onChange(e.target.value as TriState)}><option value="unknown">Unknown / not assessed</option><option value="yes">Yes, documented</option><option value="no">No known history</option></select></Field>
}
function toLocalDateTime(value?: string | null): string { if (!value) return ''; const date = new Date(value); if (Number.isNaN(date.getTime())) return ''; return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16) }
