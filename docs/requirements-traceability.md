# NCDAI 2.0 requirements and evidence ledger

This ledger connects the earlier application review and current product goals to inspectable implementation. It is an engineering response, not a new grant proposal. Private reviewer correspondence, original budget figures and licensed publication PDFs are not reproduced here. The future grant call remains unannounced; historical call requirements are planning inputs only.

| Requirement or prior weakness | Version 2 response | Verification and remaining boundary |
|---|---|---|
| Broader NCD care | Shared adult cardiovascular, diabetes, respiratory, renal, cancer-warning and multimorbidity encounter | Frozen 66-case catalogue across six domains; no claim to cover every NCD, childhood disease or specialist treatment |
| Medication and treatment-planning uncertainty | Deterministic selected medication/renal/pregnancy/allergy checks; no model-generated orders or doses | Rule boundaries and contraindication tests; incomplete drug vocabulary and interaction coverage stated visibly; clinician approval still required |
| Unknown fields becoming negative findings | Nullable measurements, explicit history states and reconciliation flags | Schema, frontend and case tests distinguish empty from assessed-negative |
| Ambiguous BP semantics | Explicit systolic/diastolic values, repeat values, units and observation time | Range/order checks and persistence/export tests; richer posture/device provenance remains future work |
| Unclear evidence grounding | Stable rule IDs with source/version/section metadata; strict provider reference validation | Evidence registry and provenance tests; AI is limited to selecting established actions, not generating unsourced clinical prose |
| Missing complete backend | Transactional facility-scoped database, authentication, patient/encounter/review/referral APIs and migration history | API tests and PostgreSQL migration/recovery verification; hosting configuration tested separately |
| Unclear session ownership | Server-owned opaque sessions, facility-derived authorization and clinical role checks | Cross-facility, revoked/expired-session, CSRF, role and concurrent-update tests |
| Token and clinical-data exposure | HttpOnly cookies, no clinical local-storage drafts, minimized provider inputs and sanitized errors | Secret/input redaction and provider payload tests; infrastructure access policies remain deployment responsibilities |
| Duplicate documentation | Familiar single consultation workflow; reviewed history can be carried forward deliberately without stale observations | Browser workflow verification; actual reduction in EMR double entry is not claimed while standalone |
| Integration portability | Standards-oriented FHIR export and explicit future adapter contract | Structural/unit/reference export tests; Aifya and QAfya integration intentionally deferred by user until APIs arrive |
| Limited clinical follow-through | Referral request, acceptance, completion/cancellation and outcome recording | Full synthetic workflows verify referral transitions and persisted outcome; reminders, longitudinal outcome registry and patient messaging are future modules |
| Unreliable saved assessments | Version checks, mandatory per-action decisions, immutable reviewed snapshots | Stale version, complete decision set, modification rationale and database trigger tests |
| Limited release checks | Layered clinical, API, security, UI, database and provider checks | Reproducible commands and dated results; failures and untested external systems must remain visible |
| Poor-connectivity settings | Core deterministic checks run without an external AI request; provider failure preserves support | Outage tests; browser cannot save offline and says so; encrypted device queue and conflict-resolving offline synchronization remain future work |
| Unproven AI value | Optional short review focus, compared operationally with complete deterministic output | Safety contract tested; clinical usefulness, consultation-time savings and incremental AI value not established |
| Maturity overstated | Synthetic-only software gate and dated verification evidence | Engineering completeness is distinct from clinical authorization, adoption and clinical effectiveness |
| Generalizability and local feasibility | Explicit medicine-availability and referral context; module/localization boundaries | County/formulary/referral ownership and contrasting-site evaluation remain future institutional work |
| Ownership/vendor dependence | Clean implementation, documented APIs/export and provider boundary | Ownership and license decision still requires project owner; no reuse or relicensing claim for old repositories |
| Evaluation/statistical/budget concerns | Retain a versioned evidence ledger and separate product readiness from prospective evaluation | Validation protocol, pilot design, power analysis, grant concept and reconciled budget will be drafted after engineering delivery, as requested |

## Release evidence rules

Each result identifies its version, input cases, database/provider mode and scope. A mocked provider test cannot establish a live connection. A successful FHIR export is not a tested EMR integration. A saved reviewer acceptance is not an independent safety label. Reusing development cases cannot establish held-out clinical accuracy. A vendor capability comparison is not a head-to-head performance ranking. No percentage-of-best-in-world claim is used.

The user confirmed no routine deployment since the original study. This version starts a new evidence chain. Future validation must independently adjudicate clinically meaningful errors, measure user interaction and workload, and track consequences of accepted and overridden support.
