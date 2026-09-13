# Mary Help clinical-testing release record

13 September 2026. **Status: deployed for supervised testing at Mary Help Hospital, Thika, planned for 14 September 2026.** This is not a declaration of independently demonstrated clinical accuracy or readiness for unrestricted deployment across all NCD care.

The owner confirms DHA and ethics approvals held in office files cover care and medication recommendations, and confirms the Frankfurt/DeepSeek data-handling arrangement. These confirmations are recorded as supplied; no additional approval request is imposed.

## Facility, accounts and intended use

Mary Help is the only facility enabled for real-patient clinical-testing records. Existing demonstration and verification facilities remain fictional-only. Record classification must be selected explicitly and cannot later be changed. No Mary Help patient records were created during provisioning or engineering verification.

Dr David Kamau has a named supervisor/consultant account. Jesse Gitaka and Jane Ngure have named administrator accounts. Jesse is the incident lead. Contacts are stored privately and shown within the authenticated hospital workspace. All three accounts require a password change before record access. Administrators manage access and evaluation but cannot read clinical charts or provide opinions. The primary health workers need their own clinician accounts; Jesse or Jane can create them under User access. No shared clinical account substitutes for named staff.

The implemented scope is selected adult NCD assessment, safety and referral pathways, with four bounded oral starting-dose references: amlodipine, losartan, lisinopril and immediate-release metformin. This is not comprehensive NCD treatment, general prescribing, insulin/oncology dosing, paediatric or obstetric treatment. Kenya guideline references are versioned source material; no fine-tuning on Kenya guidelines or independent clinical adjudication is claimed. DeepSeek provides a constrained briefing of existing findings and cannot change their wording, urgency or critical-item inclusion. Real-record briefings are enabled only within the explicitly configured facility; names, raw observations and free-text notes are excluded from provider input.

## Consultant review and evaluation

The [consultant workspace](https://ncdai-2.vercel.app/consultant) shares the repository, release and authentication with the main application. It has its **own logical PostgreSQL database and restricted role** within the existing Frankfurt Neon project. This is not a separate physical cluster or region.

A disagreement preserves the original clinical inputs, selected recommendations, rule/evidence/dose versions, primary review if present, question and immediate actions. The main database commits the request before delivery. Delivery retries are idempotent; an outage leaves a recoverable pending request. A different supervisor records a signed immutable opinion. The primary clinician records the actual action and reasons; a newer encounter requires explicit acknowledgement of changed findings. The original assessment is never replaced. Linked FHIR documents and audit events preserve traceability. Evaluation separates fictional and clinical-testing episodes, including agreement, response times and final action; these are workflow measures, not clinical-accuracy estimates.

The online queue is not continuously staffed, and no email/SMS consultant alert has been configured. Agree direct contact and who watches the queue during testing. Emergency assessment, treatment and referral must continue through the hospital team.

## Deployed release and verification

- Application: https://ncdai-2.vercel.app
- Deployed commit: `1ded07988c4086ec75bf512e828410993a095e7b`.
- Deployment: `dpl_BEqK7J126wTCP2QFu3yUrBMYK9M6`; API execution in Frankfurt (`fra1`).
- Primary schema: `20260913_mary_help`; consultant schema: `consultant-20260913-1`.
- Rules: `ncdai-2-rules-0.1.3`; evidence: `ncdai-2026-09-13.1`; dose references: `ncdai-dose-reference-0.1.1`; AI prompt: `ncdai-briefing-select-v1.5`.
- All three [cloud quality jobs passed](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34740182322). Backend: 401 passed, 10 conditional skips; frontend: 30 passed. Separate PostgreSQL jobs exercise database-only checks, including transaction/account checks and concurrent consultant writes. Dependency audits reported no known vulnerabilities at execution.
- 66 general case workflows on SQLite and PostgreSQL, 75 dose workflows on PostgreSQL, and 50 complete consultant workflows using two PostgreSQL databases and restricted runtime roles passed. Repeated database runs are not additional distinct clinical cases. The consultant suite includes two concurrency checks.
- Hosted primary workflow, live DeepSeek briefing, immutable review, referral, dose withholding/reference and acute-potassium scenario passed. The three named hospital account/facility/first-password controls and restricted consultant storage privileges passed.
- The five main browser workflows passed on the same frontend assets, with 23 accessibility scans and no reported violations. Two hosted consultant workflows passed on desktop and phone, with eight additional accessibility scans and no reported violations. Both database recovery rehearsals passed: ten primary tables and three consultant tables matched their snapshot hashes. See the [release evidence](test-results/mary-help-release-summary.json).

Live verification found and corrected two deployment defects: the consultant deep link required a frontend-service rewrite, and PostgreSQL request row locking required a narrow `UPDATE(id)` grant. The immutable trigger still rejects actual updates. The 50-case PostgreSQL runner now uses restricted roles so this permission path remains covered. Two low-contrast labels were corrected without changing the original NCDAI palette.

## Operating handover and remaining evidence

Use the [hospital testing guide](mary-help-testing-guide.md) for the staff rehearsal and actual workflow. Private initial credentials are provided to the owner separately. Staff must change their passwords and rehearse with a fictional case before the supervised patient session.

Logical recovery of the main and consultant databases is exercised separately on fictional snapshots, restoring into fresh local PostgreSQL databases. Compare hashes, immutable triggers, audit history and linked case IDs before using any restored service. These drills do not switch the public application, establish managed retention/PITR, or certify cloud RPO/RTO. Dumps and account material stay private.

The scheduled service-health workflow checks primary and consultant endpoints; its first manual run passed. Scheduling is best effort, and delivered email notifications are not established. Hospital consultant coverage, direct incident contact and downtime documentation must be agreed for each session.

Neon management currently requires the owner's email verification before opening the console. The linked Free plan is confirmed, but its actual backup/PITR retention setting has not been inspected. Complete that verification and confirm retention/recovery arrangements before relying on this service as the sole record of patient care. This is a concrete remaining operational check, not a new regulatory approval request.

Independent clinical/pharmacy adjudication of the exact implemented rules and exclusions, prospective usability/safety assessment and patient-outcome evaluation remain to be performed by the clinical study team. Approval and engineering test success are not substitutes for those results. Aifya/QAfya integration remains deferred until APIs are supplied.

## Potassium source and implementation choice

[UK Kidney Association, July 2026 guideline](https://www.ukkidney.org/health-professionals/guidelines/treatment-acute-hyperkalaemia-adults-0), sections 1.2.1–1.2.3 and 4.1–4.2, rechecked on 12 September 2026: unexpected mild hyperkalaemia calls for repeat testing within three days; moderate elevations within one day; severe elevations require urgent hospital assessment. Acute illness or kidney injury changes hospital-referral consideration at lower concentrations. This is an international supplement, not a claim that it is Kenya national policy.

NCDAI uses contiguous numeric intervals 5.5 to <6, 6 to <6.5 and >=6.5 mmol/L. Same-day routing for recorded acute illness or suspected AKI is a conservative implementation choice for local clinical acceptance. Unknown acute context is explicitly flagged for assessment, not assumed absent. These are referral/assessment prompts, with no electrolyte-treatment dosing generated.
