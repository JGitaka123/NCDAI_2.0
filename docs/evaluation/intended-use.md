# Intended use and evaluation release specification

Draft 0.1 · 12 September 2026 · PI review copy. The project owner confirms DHA and ethical approvals already cover care and medication recommendations and are held in office files. Reference/version mapping is an administrative record task; the certificates have not been independently inspected for this draft.

## Purpose and setting

NCDAI 2.0 provides clinician-supervised decision support during adult NCD assessment and follow-up in Kenyan primary care. It organizes current observations and histories, highlights selected acute and medication risks, presents source-linked actions, supports explicit clinical decisions and tracks referrals. The first evaluation concerns a standalone application. Aifya EMR, QAfya and national exchange are future integration options; no live interface or elimination of duplicate entry is assumed.

Intended users are appropriately qualified and locally authorized clinicians, including eligible clinical officers, nurses and medical officers within their professional scope. Supervisors support clinical governance; technical administrators do not gain clinical authority automatically. Patients, community health personnel, referral services and records staff contribute to the evaluation and service pathway, but this is not a consumer self-diagnosis or community-worker prescribing tool.

Intended patients are adults aged 18–120 presenting with relevant NCD care needs. Selected capabilities cover cardiovascular/hypertension, diabetes, chronic respiratory disease, renal findings, cancer warning/referral and multimorbidity. This is not comprehensive management of every NCD. Pediatric, specialist obstetric, cancer-treatment, advanced specialist and other unsupported pathways are excluded. Pregnancy prompts the appropriate separate pathway. Acutely ill patients must receive timely standard care without waiting for data entry or a model response.

## Intervention components and dose-support boundary

The core intervention consists of structured intake with explicit unknown states, deterministic clinical rules and selected medicine checks, source references, a clinician review record and referral follow-through. The external AI component selects canonical rule and missing-data IDs for a short briefing; it does not invent clinical text or calculate doses. Its incremental benefit is a research question.

The requested dose-support expansion will be evaluated only through a **frozen, clinician/pharmacist-approved module manifest**. Each supported item must identify the Kenyan source edition/page, exact ingredient/formulation/route, indication and stage of treatment, relevant age/weight bounds, starting/maintenance or adjustment rules, frequency, maximum dose, renal/hepatic and pregnancy restrictions, interaction checks, required current inputs, monitoring and follow-up. A named dose option is not an executable prescription until a qualified clinician reviews it through the approved workflow.

Only modules actually implemented, independently verified and covered by the release's intended use enter the pilot. Do not use a broad “NCD dosing” label to imply that all medications or diseases are supported. Unsupported ingredients, missing contraindication context, ambiguous formulation/units, contradictory values or a required observation outside its approved freshness window must withhold a dose recommendation and explain the missing information. The AI model cannot fill missing clinical facts or override a deterministic dose constraint.

No autonomous dispensing, order transmission, emergency insulin/fluid calculation, chemotherapy, pediatric or obstetric dosing is included in this draft. An explicit newly approved module would require a revised intended-use statement and validation. Before deployment the final manifest must state whether existing-dose review, initiation and titration are supported separately; they cannot be inferred from a medicine name.

## Required use and outputs

The clinician confirms patient identity, reviews reconciled history/medicines/allergies, enters current findings and units, inspects missing or stale information, and then reviews every recommendation. Clinical judgment determines acceptance, modification, deferral, rejection and referral. Reasons are recorded for nonacceptance and modifications. A normal rule screen is not diagnostic exclusion or clearance for discharge. A dose offer is conditional support, not a statement that treatment is appropriate in unrecorded circumstances.

The tool records input and output versions, rule/evidence/dose versions, provider/prompt configuration, timestamps and clinician decisions. Reviewed snapshots must remain immutable, with corrections handled through the authorized amendment workflow. Source changes and model/provider substitutions create a new evaluation exposure; they are not silently pooled with the frozen release.

## Data and infrastructure

The current public engineering build is restricted to synthetic records. A real-data evaluation deployment is a separately controlled release under the owner-confirmed institutional approvals, with designated controller/processor roles, appropriate privacy notices, consent/waiver process, restricted accounts and verified hosting/transfer arrangements. Record the existing approvals alongside the software and dose-module release manifest as administrative provenance; this is not a request for new permission.

Required operational context includes usable measurement equipment, referral access, current local formulary, authenticated access, backup/recovery evidence and a facility downtime procedure. The application needs connectivity to save; there is no browser offline synchronization claim. Clinical rules survive remote-AI failure, but a backend outage still requires normal facility care. Foreign AI requests remain minimized to allowed identifiers; minimizing payloads alone does not establish anonymization or permit an otherwise unauthorized transfer.

Release owner: PI/institution to enter. Clinical safety owner and independent pharmacist reviewer: to enter. Approved module manifest, hosting profile, software commit and approval references: to enter. These are acceptance-record fields; the purpose and evaluation design above are the proposed completed specification.
