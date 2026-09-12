# NCDAI 2.0 engineering verification

12 September 2026. This release is a clinician-supervised, synthetic-only application for adult major NCD workflows. The evidence below establishes specified software behavior; it does not establish clinical effectiveness, completeness of clinical guidance, a superiority ranking or authorization to use real patient records.

## Recorded evidence

| Area | Observed result | Inspectable evidence and limits |
|---|---|---|
| Cloud backend regression | 240 passed, 9 conditional tests skipped; no failures | [Quality run at 9900aca](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34710140027). Eight skips are optional live-provider checks; the PostgreSQL-specific timeout test is skipped in this job and passes separately in the PostgreSQL job. Includes clinical boundaries, security, AI contracts and FHIR export checks; do not add overlapping test subsets to this count. |
| Complete persisted case workflows | 66/66 passed on migrated PostgreSQL; 66/66 on SQLite | [PostgreSQL case report](test-results/ci-cases-postgres.json), [case definitions and independent review](case-review.md). Each workflow registers a patient, persists and assesses an encounter, reviews recommendations, exercises immutable records, completes a referral and exports FHIR. Synthetic expected behavior is not a clinician-adjudicated gold standard. |
| PostgreSQL migrations and recovery | 19/19 checks passed on PostgreSQL 18.4 | [Cloud database report](test-results/ci-postgres-verification.json), [interpretation and reproduction](database-verification.md). Includes logical restore with fingerprints, triggers and chain verification, and restart persistence; no claim of hosted recovery objectives. |
| Live DeepSeek complete workflows | 66/66 workflow contracts passed; 40 AI ready, 25 disabled, 1 unavailable | [Local PostgreSQL live-provider report](test-results/postgres-live-case-workflows.json). Disabled cases had no selectable additional items. One empty/oversized response was safely unavailable. Rules and clinician workflow remained usable; this does not mean all 66 generated an AI response. |
| Provider contract assurance | 50 mocked checks and 8 final live selection tasks passed | [AI assurance](ai-assurance.md). Tests enforce canonical recommendation selection, bounded responses, no model-written clinical orders and retained critical findings. Earlier rejected prompt versions are disclosed. OpenAI has no live-provider verification. |
| Frontend | 21 unit checks and production bundle passed | Quality workflow and [browser verification](browser-verification.md). Actual browser workflows are a separate evidence set from component tests. |
| Browser and accessibility | 5 browser tests passed; 20 automated scans with zero reported violations | [Browser report](browser-verification.md) and [sanitized metrics](quality/browser-accessibility-summary.json). One representative complete scenario at three viewports, plus keyboard and simulated administrator checks. Manual accessibility review items remain; this is not certification. |
| Final session-expiry correction | 10 timezone regressions passed; expired real-PostgreSQL session correctly rejected | [Release audit RA-01](release-audit.md). The correction is included in the successful cloud run at 9900aca. |
| Local concurrency | 40 reads, 32 audited writes, 4 competing updates behaved as expected | [Performance report](performance.md). Exactly one stale-version race winner; chain valid in four database timezones. Local p95: reads 104 ms, writes 223 ms; these are not Vercel capacity claims. |
| Clinical evidence review | Versioned sources and adaptations inspected; clinical release gaps retained | [Evidence review](evidence-review.md), [clinical safety specification](clinical-safety-spec.md). Some exact source anchors, complete pathway mapping and signed local clinical approval remain open. |

The frozen catalogue contains 66 distinct cases across the implemented domains. The baseline HbA1c and minimum-urgency expectations limit its ability to detect false positives alone; the independent normal/boundary tests address that weakness separately. No patient records from the earlier study were transmitted to an AI provider or included in the test catalogue.

## Fifteen review perspectives

The user requested fifteen specialist perspectives. These were delivered as AI-assisted engineering workstreams, with a lead integrating contributions and some agents performing more than one bounded workstream. They are not fifteen licensed humans or independent clinical certification.

| Workstream | Principal output |
|---|---|
| 1 Clinical logic and medication safety | [Clinical safety specification](clinical-safety-spec.md), executable evidence-linked checks |
| 2 Backend architecture | Authenticated, facility-scoped API with atomic writes and immutable reviews |
| 3 Clinician interface | Responsive patient, encounter, assessment, review and referral workspace |
| 4 Database integrity and recovery | Migrations, constraints, tamper guards and [recovery evidence](database-verification.md) |
| 5 Security and privacy | [Security review](security-review.md), authorization and request protections |
| 6 Interoperability and terminology | [FHIR export contract](interoperability.md); vendor adapters remain future work |
| 7 AI assurance | [Provider contract, failure behavior and live checks](ai-assurance.md) |
| 8 Independent case review | [Case critique and boundary regressions](case-review.md) |
| 9 Accessibility and human factors | [Browser/accessibility report](browser-verification.md) |
| 10 Reliability and operations | [Operational runbook](operations.md) |
| 11 Kenya governance | [Deployment and governance requirements](kenya-deployment.md) |
| 12 Evidence provenance | [Independent evidence review](evidence-review.md) |
| 13 Performance and concurrency | [Measured local PostgreSQL behavior](performance.md) |
| 14 Release engineering | [Pinned CI and reproducibility](release-engineering.md) |
| 15 Adversarial release review | [Release audit and finding dispositions](release-audit.md) |

## Release boundary

**Hosted synthetic acceptance passed** at the deployed application commit `4622c43`. The [deployment record](deployment.md) links the public application, actual live DeepSeek workflow, database/role checks and all five hosted browser tests with 20 accessibility scans. The final application CI run also passed. Vercel uses a dedicated PostgreSQL database, applied migrations, restricted application credentials, explicit HTTPS origin, secure session settings and a privately provisioned account. A green CI run alone was not treated as deployment evidence.

Clinical pilot, validation protocol and grant concept drafting follow this engineering delivery, as requested. Real care requires independently adjudicated clinical cases and source approval, local workflow review, governance and security authorization, an operational owner, recovery/monitoring readiness and the applicable Kenyan approvals. The code currently enforces synthetic-only records. Aifya EMR and QAfya integration awaits their actual APIs and sandboxes.
