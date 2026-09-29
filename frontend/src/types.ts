export type Role = 'clinician' | 'supervisor' | 'admin'
export type User = { id: string; email: string; display_name: string; role: Role; facility_id: string; facility_name: string; active?: boolean; password_change_required?: boolean; clinical_testing?: boolean; consultant_enabled?: boolean; incident_contact?: string; clinical_lead_contact?: string }
export type Session = { user: User; csrf_token: string }
export type Patient = { id: string; external_id: string; given_name: string; family_name: string; date_of_birth: string; sex: 'female' | 'male' | 'other' | 'unknown'; phone?: string; facility_id?: string; synthetic: boolean }
export type TriState = 'yes' | 'no' | 'unknown'
export type Medication = { code: string; name: string; dose?: number | null; unit?: string; frequency?: string }
export type DosingIndication = 'hypertension' | 'type_2_diabetes'
export type DosingRequest = { medicine_id: string; indication: DosingIndication; proposed_dose_mg?: number | null; frequency_per_day?: number | null }
export type DosingContext = { hepatic_impairment: TriState; breastfeeding: TriState | 'not_applicable'; acute_illness: TriState; dialysis: TriState; frailty: TriState; contraindications_reviewed: boolean; interactions_reviewed: boolean; renal_observed_at: string | null; potassium_observed_at?: string | null }
export type DosingMedicine = { medicine_id: string; name: string; indication: DosingIndication; formulation: string; route: string; unit: 'mg'; clinical_checks?: string }
export type DosingCatalogue = { version: string; medicines: DosingMedicine[]; scope_note: string }
export type DosingAssessment = { version: string; results: { medicine_id: string; name: string; status: 'reference' | 'blocked' | 'outside_reference'; reasons: string[]; reference: null | { initial_dose_mg: number; frequency_per_day: number; max_daily_mg: number }; proposed_daily_mg: number | null; evidence: Evidence[] }[] }
export type ClinicalData = {
  systolic_bp: number | null; diastolic_bp: number | null; repeat_systolic_bp: number | null; repeat_diastolic_bp: number | null;
  pulse: number | null; hba1c: number | null; glucose: number | null; glucose_unit: 'mmol/L' | 'mg/dL';
  acutely_unwell?: TriState; acute_kidney_injury?: TriState;
  egfr: number | null; potassium: number | null; pregnancy_status: TriState | 'not_applicable';
  known_hypertension: TriState; known_diabetes: TriState; medications: Medication[]; medications_reviewed: boolean;
  known_asthma: TriState; known_copd: TriState; known_ckd: TriState; known_cancer: TriState;
  oxygen_saturation: number | null; respiratory_rate: number | null; tobacco_use: 'unknown' | 'current' | 'former' | 'never';
  allergies: string[]; allergies_reviewed: boolean; symptoms: string[]; symptoms_reviewed: boolean;
  adherence: 'taking' | 'missed' | 'unknown'; notes: string; observed_at?: string | null;
  medicine_availability: 'available' | 'limited' | 'unknown';
  dosing_requests?: DosingRequest[]; dosing_context?: DosingContext;
  weight_kg?: number | null; height_cm?: number | null; waist_cm?: number | null; creatinine_umol?: number | null; urine_acr_mg_mmol?: number | null;
  total_cholesterol_mmol?: number | null; hdl_mmol?: number | null; ldl_mmol?: number | null; hemoglobin_g_dl?: number | null;
  glucose_context?: 'fasting' | 'random' | 'unknown'; known_ascvd?: TriState; prior_stroke_tia?: TriState; known_heart_failure?: TriState; known_atrial_fibrillation?: TriState;
  exacerbations_past_year?: number | null; reliever_use_per_week?: number | null; hypoglycaemia_episodes_3m?: number | null;
  eye_screen?: CareInterval; foot_exam?: CareInterval;
}
export type CareInterval = 'within_12_months' | 'over_12_months' | 'never' | 'unknown'
export type ProblemStatus = 'acute' | 'uncontrolled' | 'untreated' | 'above_target' | 'high_risk' | 'review' | 'unconfirmed' | 'needs_confirmation' | 'at_risk' | 'needs_data' | 'established' | 'withheld' | 'at_target'
export type PlanStep = { text: string; source_ids: string[] }
export type ConsultantProblem = { id: string; rank: number; title: string; status: ProblemStatus; facts: string[]; assessment: string; plan: PlanStep[]; targets: string[]; source_ids: string[] }
export type ConsultantSynthesis = {
  version: string; one_liner: string; impression: string; acute_first: boolean; follow_up: string; summary_text: string; boundary: string
  derived: { id: string; label: string; value: string; unit: string; interpretation: string; method: string; source_ids: string[] }[]
  cardiovascular_risk: null | { category: string; basis: string; percent: number | null; method: string | null; statement: string; source_ids: string[] }
  problems: ConsultantProblem[]
  medication_review: { id: string; severity: 'high' | 'moderate' | 'low'; finding: string; action: string; source_ids: string[] }[]
  considerations: { id: string; text: string; source_ids: string[] }[]
  monitoring: { id: string; test: string; timing: string; reason: string; source_ids: string[] }[]
  data_gaps: { field: string; why: string }[]
  sources: Evidence[]
}
export type Evidence = { source_id: string; title: string; url: string; section: string; version: string }
export type Recommendation = { id: string; rule_id: string; category: string; severity: 'info' | 'warning' | 'critical'; title: string; detail: string; evidence: Evidence[] }
export type Urgency = 'routine' | 'soon' | 'urgent' | 'emergency'
export type AiBriefing = { status: 'ready' | 'disabled' | 'unavailable' | 'blocked'; reason_code?: string; provider?: string; model?: string; prompt_version?: string; focus?: Recommendation[]; checklist?: string[]; source_ids?: string[] }
export type Assessment = { id: string; urgency: Urgency; summary: string; recommendations: Recommendation[]; missing_data: string[]; warnings: string[]; model_info: { mode: string; provider?: string; model?: string; status: string }; evidence_version: string; generated_at: string; ai_briefing?: AiBriefing; dosing?: DosingAssessment; consultant?: ConsultantSynthesis }
export type DecisionAction = 'accept' | 'modify' | 'defer' | 'reject'
export type Decision = { recommendation_id: string; action: DecisionAction; reason?: string; modified_text?: string }
export type Encounter = { id: string; patient_id: string; version: number; status: 'draft' | 'reviewed'; data: ClinicalData; assessment: Assessment | null; created_at: string; updated_at: string; review?: { decisions: Decision[]; note?: string; reviewer_name?: string; reviewed_at?: string } }
export type Referral = { id: string; encounter_id: string; patient_id: string; patient_name?: string; patient_external_id?: string; destination: string; reason: string; urgency: Urgency; status: 'requested' | 'accepted' | 'completed' | 'cancelled'; created_at: string; outcome?: string }
export type Dashboard = { patients: number; encounters: number; reviewed: number; open_referrals: number; urgent_assessments: number }
export type AuditEvent = { id: string; action: string; entity_type: string; entity_id: string; actor_id: string; created_at: string; chain_hash: string }
