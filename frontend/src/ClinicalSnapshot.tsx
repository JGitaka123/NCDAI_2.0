function display(value: unknown) {
  if (value == null || value === '' || value === 'unknown') return 'Unknown / not recorded'
  if (typeof value === 'boolean') return value ? 'Reviewed / confirmed' : 'Not reviewed'
  return String(value).replaceAll('_', ' ')
}
const observations = [
  ['systolic_bp', 'Systolic blood pressure', 'mmHg'], ['diastolic_bp', 'Diastolic blood pressure', 'mmHg'],
  ['repeat_systolic_bp', 'Repeat systolic pressure', 'mmHg'], ['repeat_diastolic_bp', 'Repeat diastolic pressure', 'mmHg'],
  ['pulse', 'Pulse', 'beats/min'], ['oxygen_saturation', 'Oxygen saturation', '%'], ['respiratory_rate', 'Respiratory rate', 'breaths/min'],
  ['hba1c', 'HbA1c', '%'], ['egfr', 'Estimated kidney filtration', 'mL/min/1.73 m²'], ['potassium', 'Potassium', 'mmol/L'],
]
export default function ClinicalSnapshot({ data }: { data: Record<string, unknown> }) {
  return <div className="panel-body"><dl className="account-details">{observations.map(([key, label, unit]) => <div key={key}><dt>{label}</dt><dd>{display(data[key])}{data[key] != null ? ` ${unit}` : ''}</dd></div>)}<div><dt>Blood glucose</dt><dd>{display(data.glucose)} {data.glucose != null ? display(data.glucose_unit) : ''}</dd></div></dl>
    <h3>Clinical context at handoff</h3><dl className="account-details">{['acutely_unwell', 'acute_kidney_injury', 'pregnancy_status', 'known_hypertension', 'known_diabetes', 'known_asthma', 'known_copd', 'known_ckd', 'known_cancer', 'symptoms_reviewed', 'medications_reviewed', 'allergies_reviewed', 'medicine_availability', 'adherence'].map(key => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{display(data[key])}</dd></div>)}</dl>
    <p><strong>Measurements recorded at:</strong> {display(data.observed_at)}</p>
    <h3>Symptoms</h3><p>{Array.isArray(data.symptoms) && data.symptoms.length ? data.symptoms.map(display).join(', ') : 'None listed; check the symptom-review status above.'}</p>
    <h3>Medication history</h3>{Array.isArray(data.medications) && data.medications.length ? <ul>{data.medications.map((raw, i) => { const med = raw as Record<string, unknown>; return <li key={i}>{display(med.name)} — {display(med.dose)} {display(med.unit)}, {display(med.frequency)}</li> })}</ul> : <p>None listed; check the medication-review status above.</p>}
    <h3>Allergies</h3><p>{Array.isArray(data.allergies) && data.allergies.length ? data.allergies.map(display).join(', ') : 'None listed; check the allergy-review status above.'}</p>
    {data.dosing_context != null && typeof data.dosing_context === 'object' && <><h3>Dose-check context</h3><dl className="account-details">{Object.entries(data.dosing_context as Record<string, unknown>).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{display(value)}</dd></div>)}</dl></>}
    {Array.isArray(data.dosing_requests) && data.dosing_requests.length > 0 && <><h3>Requested medicine checks</h3><ul>{data.dosing_requests.map((raw, index) => { const item = raw as Record<string, unknown>; return <li key={index}>{display(item.medicine_id)} · {display(item.indication)} · proposed dose: {display(item.proposed_dose_mg)} mg, {display(item.frequency_per_day)} administrations/day</li> })}</ul></>}
    <h3>Clinical notes</h3><p>{display(data.notes)}</p>
  </div>
}
