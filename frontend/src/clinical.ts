import type { ClinicalData, Decision, DosingContext, Encounter, Recommendation } from './types'

export function emptyDosingContext(): DosingContext {
  return { hepatic_impairment: 'unknown', breastfeeding: 'unknown', acute_illness: 'unknown', dialysis: 'unknown', frailty: 'unknown', contraindications_reviewed: false, interactions_reviewed: false, renal_observed_at: null, potassium_observed_at: null }
}

export function emptyClinicalData(): ClinicalData {
  return {
    systolic_bp: null, diastolic_bp: null, repeat_systolic_bp: null, repeat_diastolic_bp: null,
    pulse: null, hba1c: null, glucose: null, glucose_unit: 'mmol/L', glucose_timing: 'unknown', egfr: null, potassium: null,
    weight_kg: null, height_cm: null, waist_cm: null, total_cholesterol: null, ldl_cholesterol: null, hdl_cholesterol: null, triglycerides: null,
    acutely_unwell: 'unknown', acute_kidney_injury: 'unknown',
    pregnancy_status: 'unknown', known_hypertension: 'unknown', known_diabetes: 'unknown',
    known_asthma: 'unknown', known_copd: 'unknown', known_ckd: 'unknown', known_cancer: 'unknown', known_cvd: 'unknown',
    oxygen_saturation: null, respiratory_rate: null, tobacco_use: 'unknown',
    medications: [], medications_reviewed: false, allergies: [], allergies_reviewed: false, symptoms: [], symptoms_reviewed: false,
    adherence: 'unknown', notes: '', observed_at: null, medicine_availability: 'unknown',
    dosing_requests: [], dosing_context: emptyDosingContext(),
  }
}

export const symptoms: [string, string][] = [
  ['chest_pain', 'Chest pain'], ['breathlessness', 'Breathlessness'], ['neurological_deficit', 'New neurological deficit'],
  ['confusion', 'Confusion'], ['seizure', 'Seizure'], ['severe_headache', 'Severe headache'],
  ['visual_disturbance', 'Visual disturbance'], ['vomiting', 'Vomiting'], ['dehydration', 'Dehydration'],
  ['foot_ulcer', 'Foot ulcer'], ['hypoglycemia_symptoms', 'Hypoglycaemia symptoms'],
  ['wheeze', 'Wheeze'], ['hemoptysis', 'Coughing blood'], ['unexplained_weight_loss', 'Unexplained weight loss'],
  ['persistent_cough', 'Persistent cough'], ['breast_lump', 'Breast lump'], ['abnormal_bleeding', 'Abnormal bleeding'],
]
export const medicineNames = ['Amlodipine', 'Nifedipine', 'Felodipine', 'Hydrochlorothiazide', 'Chlorthalidone', 'Indapamide', 'Lisinopril', 'Enalapril', 'Ramipril', 'Captopril', 'Losartan', 'Telmisartan', 'Valsartan', 'Candesartan', 'Irbesartan', 'Atenolol', 'Bisoprolol', 'Carvedilol', 'Methyldopa', 'Spironolactone', 'Furosemide',
  'Metformin', 'Gliclazide', 'Glimepiride', 'Glibenclamide', 'Sitagliptin', 'Vildagliptin', 'Empagliflozin', 'Dapagliflozin', 'Pioglitazone', 'Insulin NPH', 'Insulin soluble', 'Insulin premixed', 'Insulin glargine',
  'Atorvastatin', 'Simvastatin', 'Rosuvastatin', 'Aspirin', 'Salbutamol', 'Beclometasone', 'Budesonide', 'Ibuprofen', 'Diclofenac']
export function bmiOf(weight?: number | null, height?: number | null): { value: number; category: string } | null {
  if (!weight || !height) return null
  const value = Math.round(weight / (height / 100) ** 2 * 10) / 10
  return { value, category: value < 18.5 ? 'Underweight' : value < 25 ? 'Healthy range' : value < 30 ? 'Overweight' : 'Obesity' }
}
export const formatDate = (date?: string | null, withTime = false) => {
  if (!date) return 'Not recorded'
  const parsed = new Date(date)
  if (Number.isNaN(parsed.getTime())) return 'Invalid date'
  return new Intl.DateTimeFormat('en-KE', { day: 'numeric', month: 'short', year: 'numeric', ...(withTime ? { hour: '2-digit', minute: '2-digit' } as const : {}) }).format(parsed)
}
export function ageInYears(dob: string): number {
  const born = new Date(`${dob}T00:00:00`), now = new Date()
  return now.getFullYear() - born.getFullYear() - (now.getMonth() < born.getMonth() || (now.getMonth() === born.getMonth() && now.getDate() < born.getDate()) ? 1 : 0)
}
export const titleCase = (value: string) => value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
export function numericInput(value: string): number | null { return value.trim() === '' ? null : Number(value) }
export function reviewErrors(recommendations: Recommendation[], decisions: Record<string, Partial<Decision>>): string[] {
  return recommendations.flatMap(item => {
    const decision = decisions[item.id]
    if (!decision?.action) return [`Choose a decision for “${item.title}”.`]
    if (decision.action !== 'accept' && !decision.reason?.trim()) return [`Add your reason for “${item.title}”.`]
    if (decision.action === 'modify' && !decision.modified_text?.trim()) return [`Record the modified action for “${item.title}”.`]
    return []
  })
}
export function isDirty(saved: Encounter | null, draft: ClinicalData): boolean {
  return saved ? JSON.stringify(saved.data) !== JSON.stringify(draft) : JSON.stringify(emptyClinicalData()) !== JSON.stringify(draft)
}
export function carryForwardContext(prior: Encounter): ClinicalData {
  const data = emptyClinicalData()
  for (const key of ['known_hypertension', 'known_diabetes', 'known_asthma', 'known_copd', 'known_ckd', 'known_cancer', 'known_cvd'] as const) data[key] = prior.data[key] ?? 'unknown'
  data.height_cm = prior.data.height_cm ?? null
  if (prior.data.medications_reviewed) data.medications = structuredClone(prior.data.medications)
  if (prior.data.allergies_reviewed) data.allergies = [...prior.data.allergies]
  data.notes = `Historical context brought forward from encounter ${prior.id} (${formatDate(prior.created_at)}). Confirm chronic history, reconcile medicines and allergies for this visit. Current measurements and symptoms were not copied.`
  return data
}
export function safeEvidenceUrl(url: string): string | undefined {
  try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? url : undefined } catch { return undefined }
}
