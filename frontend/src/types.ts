export type Role = 'clinician' | 'supervisor' | 'admin'
export type User = { id: string; email: string; display_name: string; role: Role; facility_id: string; facility_name: string }
export type Session = { user: User; csrf_token: string }
export type Patient = { id: string; external_id: string; given_name: string; family_name: string; date_of_birth: string; sex: 'female' | 'male' | 'other' | 'unknown'; phone?: string; facility_id?: string; synthetic: boolean }
export type TriState = 'yes' | 'no' | 'unknown'
export type Medication = { code: string; name: string; dose?: number | null; unit?: string; frequency?: string }
export type ClinicalData = {
  systolic_bp: number | null; diastolic_bp: number | null; repeat_systolic_bp: number | null; repeat_diastolic_bp: number | null;
  pulse: number | null; hba1c: number | null; glucose: number | null; glucose_unit: 'mmol/L' | 'mg/dL';
  egfr: number | null; potassium: number | null; pregnancy_status: TriState | 'not_applicable';
  known_hypertension: TriState; known_diabetes: TriState; medications: Medication[]; medications_reviewed: boolean;
  known_asthma: TriState; known_copd: TriState; known_ckd: TriState; known_cancer: TriState;
  oxygen_saturation: number | null; respiratory_rate: number | null; tobacco_use: 'unknown' | 'current' | 'former' | 'never';
  allergies: string[]; allergies_reviewed: boolean; symptoms: string[]; symptoms_reviewed: boolean;
  adherence: 'taking' | 'missed' | 'unknown'; notes: string; observed_at?: string | null;
  medicine_availability: 'available' | 'limited' | 'unknown';
}
export type Evidence = { source_id: string; title: string; url: string; section: string; version: string }
export type Recommendation = { id: string; rule_id: string; category: string; severity: 'info' | 'warning' | 'critical'; title: string; detail: string; evidence: Evidence[] }
export type Urgency = 'routine' | 'soon' | 'urgent' | 'emergency'
export type AiBriefing = { status: 'ready' | 'disabled' | 'unavailable' | 'blocked'; reason_code?: string; provider?: string; model?: string; prompt_version?: string; focus?: Recommendation[]; checklist?: string[]; source_ids?: string[] }
export type Assessment = { id: string; urgency: Urgency; summary: string; recommendations: Recommendation[]; missing_data: string[]; warnings: string[]; model_info: { mode: string; provider?: string; model?: string; status: string }; evidence_version: string; generated_at: string; ai_briefing?: AiBriefing }
export type DecisionAction = 'accept' | 'modify' | 'defer' | 'reject'
export type Decision = { recommendation_id: string; action: DecisionAction; reason?: string; modified_text?: string }
export type Encounter = { id: string; patient_id: string; version: number; status: 'draft' | 'reviewed'; data: ClinicalData; assessment: Assessment | null; created_at: string; updated_at: string; review?: { decisions: Decision[]; note?: string; reviewer_name?: string; reviewed_at?: string } }
export type Referral = { id: string; encounter_id: string; patient_id: string; patient_name?: string; patient_external_id?: string; destination: string; reason: string; urgency: Urgency; status: 'requested' | 'accepted' | 'completed' | 'cancelled'; created_at: string; outcome?: string }
export type Dashboard = { patients: number; encounters: number; reviewed: number; open_referrals: number; urgent_assessments: number }
export type AuditEvent = { id: string; action: string; entity_type: string; entity_id: string; actor_id: string; created_at: string; chain_hash: string }
