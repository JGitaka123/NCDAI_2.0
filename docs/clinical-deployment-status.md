# Clinical deployment release record

12 September 2026. **Status: clinical deployment preparation; patient-care activation incomplete.**

The owner confirms DHA and ethics approvals, held in office files, cover NCDAI 2.0 care and medication recommendations and authorizes deployment. No further permission request is being imposed. This record distinguishes that confirmation from evidence about the implemented release and the operational details needed to configure its first care facility.

## Completed in this release

- Rules `ncdai-2-rules-0.1.2`, evidence `ncdai-2026-09-12.3`, dose references `ncdai-dose-reference-0.1.1`, constrained AI prompt `ncdai-briefing-select-v1.4`.
- Explicit acute-illness and suspected/confirmed acute kidney injury fields. New encounters do not inherit these findings from prior encounters. Unknown is never converted to a negative finding.
- Potassium follow-up deadlines and same-day hospital assessment advice when acute illness or kidney injury is recorded; severe results retain immediate escalation. Contradictory negative dose-context entries cannot override a positive acute finding. Elective starting-dose references require explicit negatives for both new acute fields.
- Read-only snapshot of the current hosted synthetic database restored to a new local PostgreSQL database. All eight application tables matched by count and SHA256; all facility audit chains, required triggers and schema revision verified. Copied sessions were revoked, and application readiness, sign-in, record access and logout passed. Measured execution: **44.188 seconds**. [Rehearsal evidence](test-results/hosted-recovery-rehearsal.json).

This recovery exercise used fictional records. It did not switch the public service, certify RPO/RTO, establish automatic backup retention or test regional cloud failover. Raw dumps and account material remain private and are not release artifacts.

## Patient-care activation dependencies

| Item | Current evidence / next action |
|---|---|
| DHA and ethics authorization | Owner-confirmed, including medication recommendations. Reference identifiers may be recorded from office files without publishing the files. |
| First facility and accountable operators | Facility name/county, clinical lead, administrator work emails and incident contact requested. Do not invent identities or use the shared demonstration account for care. |
| Hosting and AI data handling | Current app/database compute is Frankfurt; DeepSeek receives constrained health-context identifiers. Confirmation of the approved arrangement for these services is requested. Real-patient AI processing remains disabled. |
| Exact clinical implementation acceptance | Kenya primary-care dose pages verified; broad source licensing/supersession and independent clinical/pharmacy adjudication of the actual rules and exclusions remain unfinished. Institutional approval and engineering tests do not constitute the missing adjudication results. |
| Operational monitoring and recovery | Hosted snapshot recovery now demonstrated. Scheduled encrypted backups/PITR retention, delivered alerts, incident rota and cloud recovery/downtime exercise remain to be verified with the responsible operator. |
| Real-record mode and separation | Current database, API and UI deliberately permit fictional records only. Implement and test isolated clinical-facility configuration, real-record registration, appropriately bounded provider access and operational accounts before activation; never relabel existing demonstration records as real. |
| Intended use and staff onboarding | Selected adult NCD decision support and four bounded dose references. No comprehensive NCD coverage, general prescribing, insulin/oncology dosing, paediatric or obstetric treatment claim. Staff must be able to identify unsupported cases and follow the facility referral/downtime process. |
| Independent validation | The existing 66 general and 75 dose workflow suites are engineering evidence. No blinded clinical adjudication or live-patient outcome study is claimed. The evaluation package provides the proposed next stage. |

The public application's technical readiness endpoint is not a clinical readiness certificate. Removing the research label or setting production environment variables cannot close these dependencies. The current fictional-record restriction remains in effect while deployment preparation continues.

## Potassium source and implementation choice

[UK Kidney Association, July 2026 guideline](https://www.ukkidney.org/health-professionals/guidelines/treatment-acute-hyperkalaemia-adults-0), sections 1.2.1–1.2.3 and 4.1–4.2, rechecked on 12 September 2026: unexpected mild hyperkalaemia calls for repeat testing within three days; moderate elevations within one day; severe elevations require urgent hospital assessment. Acute illness or kidney injury changes hospital-referral consideration at lower concentrations. This is an international supplement, not a claim that it is Kenya national policy.

NCDAI uses contiguous numeric intervals 5.5 to <6, 6 to <6.5 and >=6.5 mmol/L. Same-day routing for recorded acute illness or suspected AKI is a conservative implementation choice for local clinical acceptance. Unknown acute context is explicitly flagged for assessment, not assumed absent. These are referral/assessment prompts, with no electrolyte-treatment dosing generated.


## Published verification result

The update is live at [NCDAI 2.0](https://ncdai-2.vercel.app), commit `dac1187d76238368a71c1a5bb7c11b23cfe52c6b`, deployment `dpl_EcgLxsryt2z2wTsEYGonTUXSyS4B`, with the API function confirmed in Frankfurt. All three cloud jobs passed: 381 backend tests, 28 frontend tests, 19 database checks, both complete-case sets on both database engines. Five public-browser workflows and 23 accessibility scans passed with zero reported violations. Live DeepSeek and the new acute-potassium review workflow passed. See [the release summary](test-results/clinical-readiness-release-summary.json) for skips and limits. These completed engineering checks do not change the activation dependencies above.
