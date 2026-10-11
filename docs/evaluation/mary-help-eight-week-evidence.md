# Mary Help: eight-week evidence collection

Prepared 14 September 2026. Operational proposal, not a powered effectiveness trial. The future EVAH call has not been assumed open; the closed Spring 2026 call remains the planning reference. The owner has confirmed the hospital's approvals. This measurement plan does not assert independent clinical validation.

## Recruitment

Proposed target: **500 unique, consecutive, eligible adult NCD patients over eight weeks**, conditional on clinic volume and staffing. At five collection days per week, this requires 12–13 newly recruited patients per day (62–63 per week). A 300-patient feasibility cohort remains useful if throughput is lower; this is a practical fallback, not a calculated minimum. Count a returning patient once for recruitment and count each genuine clinical encounter separately. Do not register duplicate patients to meet targets or add visits without clinical/study justification.

Recruit across the application's supported NCD presentations and record multimorbidity, age and sex without inventing disease quotas. Preserve counts of eligible visits without app use and reasons for non-use. People declining research can remain in anonymous daily totals; do not create patient records solely to identify decliners. Document participation using the approved protocol's applicable consent or waiver process.

500 is a proposed operational cohort, not a power calculation. Illustratively, a simple independent binomial proportion of 80% at n=500 has a normal-approximation 95% margin of about 3.5 percentage points. This illustration ignores clinician clustering, selection and missingness and must not be presented as the study's guaranteed precision. A statistician should finalize progression thresholds and analysis before recruitment. The definitive comparative evaluation needs its own sample-size calculation using the selected outcome, clustering, repeated measurements and attrition.

The in-app descriptive follow-up convention is a day-30 assessment, accepting completed contacts on days 21–45. It does not prescribe additional clinical tests or appointments. Patients only enter the due denominator when day 30 has elapsed; withdrawn participants are separately counted. The final 30-day follow-up for late recruits extends beyond the eight-week recruitment period. Aim for at least 80% completed follow-up among those due; investigate missingness rather than assuming a missing outcome is normal. This is a proposed operating target, not an observed result.

## What is collected

| Measure | Definition and denominator | Source / responsibility |
|---|---|---|
| Recruitment | Unique currently enrolled patients with index dates in the selected window; pending, declined, ineligible and withdrawn counts separately | Clinician documents enrolment once; status corrections retain the original baseline |
| Clinic adoption | NCDAI-used eligible visits / all eligible adult NCD visits, limited to days with a submitted daily tally | Designated clinic recorder, coordinated by Jane; one whole-clinic tally per day |
| Follow-up completeness | Due active enrollees with a completed day 21–45 contact / all active enrollees due by report end; closest contact to day 30 chosen | Clinician records completed and unsuccessful contacts; Dr Kamau reviews missing follow-up |
| Review completion | Encounters with saved clinician review / encounters created in the report window | Automatic persisted encounter records; status is current when extracted |
| Workflow observation coverage | Encounters with a visit observation / encounters created in the window | Clinician/research observer; measure consultation time independently and label estimates |
| Consultation time | Median minutes and number measured, separately for observed and estimated timings | Visit observation; includes the whole consultation, not browser dwell time |
| Decisions | Counts of accept, modify, defer and reject per recommendation; reported change of decision separately | Saved clinician review and visit observation; acceptance is not clinical correctness |
| Safety | Reported incidents by severity, open/resolved status, and visit-level safety screening coverage | Clinical team; immediately use hospital escalation, then document event/action |
| AI reliability | Persisted briefing requests by status, stored latency, provider/model/prompt versions and token usage in protected activity extract | Automatic only after the server persists the result; excludes unrecorded failures |
| Dosing | Dose-check status counts per assessment event; medicine and version metadata retained | Automatic; repeated assessments are counted as events, not unique patients |
| Equity / case mix | Age bands, sex, consultation language, baseline known-condition flags and missingness | Enrolment snapshot / visit form; exploratory subgroup analyses, not representativeness claims |
| Clinical trajectory | Descriptive paired systolic BP change for due patients with both baseline and qualifying follow-up BP | Baseline frozen at enrolment, follow-up measurement; report paired n and missingness |
| Consultant pathway | Requests, delivery, independent opinions and primary clinician disposition | Existing separate consultant database and Evaluation view; request IDs preserve the linkage |

**Three proposed primary feasibility indicators:** clinic adoption, workflow observation completeness and follow-up completeness. Initial operating targets for discussion: adoption ≥80%, workflow observations ≥90%, due follow-up ≥80%. These targets are not derived from a local baseline. Review weekly and predefine how shortfalls lead to workflow changes before interpreting a final readout.

The current form collects BP and HbA1c when clinically obtained. An eight-week, uncontrolled cohort cannot establish attributable BP/HbA1c benefit, reductions in admissions or rare-event safety. Independent clinical adjudication and comparative workflow timing remain separate evaluation work. The first application review's concern about a live clinical evidence gap cannot be resolved by software regression tests alone.

## Staff workflow and ownership

1. Save the actual clinical encounter. Open **Study observations** and document enrolment at the index visit. Verify the index date and baseline before saving. The index encounter/date are fixed after the first save to prevent accidental baseline changes.
2. Record a brief **visit** observation: time and measurement method, decision change, workflow difficulty, language, helpfulness and whether safety was assessed. Unknown/not recorded remain explicit.
3. Record **follow-up** attempts and outcomes when due under the protocol. Unreachable, missed, declined and deceased are distinct outcomes. Enter measurements only for completed contacts.
4. Record an incident using **safety** after immediate hospital escalation. Saving does not email or page the incident lead. Dr David Kamau oversees clinical adjudication; Jesse remains the incident contact. No notification service is implied.
5. Jane (proposed data coordinator, supported by Jesse) reconciles a **daily clinic tally**, including eligible non-users. Choose the existing day to correct it. All component counts must add up to the eligible total.
6. Jesse or Dr Kamau opens **Study metrics**, selects clinical records and dates, and loads the readout. Download and retain dated aggregate readouts in approved study storage weekly. Dr Kamau's supervisor role can also download the protected patient-level extract.

No email has been sent assigning these duties. Staff must agree the practical rota. The app writes the evidence as staff use it; the coding assistant is not continuously watching the database. On request, authorized aggregate extracts can be checked and analyzed. Database access alone cannot recover unrecorded patient outcomes or missed clinic visits.

## Data handling, integrity and analysis

- `study_events` is written in the same transaction as the clinical action and audit event. It captures future assessments, reviews, AI briefings and referral transitions, with relevant versions. It does not retroactively reconstruct overwritten assessments.
- `study_records` is append-only. Corrections create a new revision linked to its predecessor. Idempotency keys protect retries, and stale corrections are rejected. Reads check stored hashes. PostgreSQL/SQLite migration triggers reject updates/deletes. Hashes do not replace an independently protected backup.
- Clinical and synthetic classifications remain separate. Facility scoping and clinical roles protect case observations. Administrators see aggregate study reporting and clinic totals, not patient-level study exports.
- Supervisor extracts remove names, contact details, local patient identifiers, dates of birth and safety free text; stable facility-specific pseudonyms link patients, encounters and clinicians. Dates and clinical variables mean the extract is **pseudonymised health data, not anonymous**. Do not put exports in GitHub, public reports or unapproved sharing locations. Pseudonyms depend on the application's secret key; coordinate any key rotation with the study lead.
- Retain the generated timestamp, window, metrics version, extraction hash and original exported file for each frozen analysis. The report uses current encounter status, with study revisions/events restricted to the stated cutoff; it is not a historical reconstruction of all mutable clinical tables.
- The report is bounded to a maximum 121-day window and 20,000 source rows per dataset. It fails explicitly rather than silently truncating. Larger evaluations need a governed analytical extract.
- Count missing values explicitly. Do not label accepted recommendations accurate without independent adjudication. Do not infer no harm from zero reported incidents or no AI use from a pre-instrumentation period.
- Monthly API invoices, hosting bills, staff time, training and support costs need a separate approved costing ledger. Stored token usage supports reconciliation but does not constitute a verified total-cost measure.
- External EMR use, a controlled comparison group, automated incident notification, scheduled evidence exports and continuous outcome monitoring are not implemented by this release. The existing backup/operational readiness limitations remain documented separately.

## Evidence package at eight weeks

Provide a recruitment/participation flow, weekly adoption and non-use reasons, completeness table, clinician/time observations, recommendation decisions, versioned AI/dosing activity, consultant response/disposition results, incident adjudication log, subgroup/missingness descriptions, and a cost ledger. Present all denominators and distinguish recruitment from completed follow-up. Preserve the later follow-up extraction for participants not yet due at week eight.

Report live clinical implementation with [DECIDE-AI](https://www.nature.com/articles/s41591-022-01772-9), which addresses clinical performance, safety and human factors. Justify feasibility sample size against its objectives and planned interpretation, as discussed in the [BMJ pilot sample-size tutorial](https://www.bmj.com/content/390/bmj-2024-083405). The proposed 500-patient observational cohort is not itself a randomized pilot trial.
