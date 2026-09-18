# Kenya dose-reference release verification

12 September 2026 · Engineering release record

Application change `26de2b6cee2fbc5d3d54e0516181a6fa72e17ced` adds four bounded Kenya oral dose references, contextual withholding, immutable clinician review and source provenance, alongside account password/status operations. Configuration commit `d8cc6e3d246d65fd794494a2b2f77170f703b6d8` pins Frankfurt as the API region; its [full CI run 34713562013](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34713562013) also passed. The original coral and NCDAI logo are retained.

| Verification | Result and scope |
|---|---|
| GitHub release checks | Backend, frontend and PostgreSQL jobs passed on [run 34713293828](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34713293828) |
| Backend CI suite | **351 passed, 10 skipped**, no errors/failures; skipped cases are 8 optional live-AI checks and 2 separately executed PostgreSQL-specific tests |
| New dose checks | **91 passed** locally, including 75 explicit dose scenarios and a complete API lifecycle for every scenario |
| PostgreSQL dose workflows | **75/75 passed**, separately in local native PostgreSQL and the CI PostgreSQL service |
| Original general NCD workflows | **66/66 passed** on SQLite and PostgreSQL; the frozen original case set was not rewritten |
| Database checks | **19/19 passed** in CI, plus transaction timeout and account-concurrency checks |
| Account lifecycle | Password reauthentication, other-session revocation, same-facility administration, self/last-admin safeguards, audit rollback and actual PostgreSQL races verified |
| Frontend components | **27/27 passed**, including new medicine-reference and account forms |
| Browser workflows | **5/5 passed** locally, covering desktop 1366, tablet 768 and mobile 375 pixels, keyboard navigation and administrator boundaries |
| Automated accessibility | **23 current-run scans, zero reported violations**; not a WCAG certificate or substitute for clinician/usability assessment |
| Release build/security | Frontend build, backend package and dependency audits passed in CI; hosted build completed separately |

The 75 dose scenarios include all four starting/ceiling references; excessive, low and unsupported-frequency proposals; incomplete or unreviewed history; allergy and pregnancy contexts; frailty/age, kidney/liver/dialysis and acute-illness exclusions; stale observations/laboratory results; unconfirmed indication; availability; unknown/ambiguous/duplicate current medicines; dual RAS treatment; unsupported insulin/extended-release products; and hostile notes. API verification covers creation, assessment, mandatory decisions for dose-withholding advice, review, retrieval, immutable-record rejection, FHIR document export without a medication order, and facility audit verification. An AI test confirms canonical dose-card selection and rejects a provider-invented dose field.

The full local regression run initially found that Alembic logging configuration could disable an already-created redacted security logger. The migration configuration now preserves existing loggers, and the dedicated migration/security regression and full CI pass. Browser review found a long source identifier expanding the 375px assessment; evidence wrapping now preserves the viewport. Repeated local browser runs also reached the intentional sign-in throttle; the isolated local demo credentials were refreshed, and the final complete run passed without weakening production throttling.

The dose catalogue version at this 12 September release was `ncdai-dose-reference-0.1.0`, manifest SHA256 `903b0947230c11e4555745ac9846130842ff58042c7533ea76a06d005b151aac`. It was superseded on 13 September 2026 by `ncdai-dose-reference-0.1.1`, which withholds a reference unless acute illness and acute kidney injury are both explicitly recorded as absent; see the [dose engine](dosing-engine.md) and [current status](clinical-deployment-status.md). This page remains the record of the earlier release. Evidence version is `ncdai-2026-09-12.2`; dose-card selection uses prompt `ncdai-briefing-select-v1.3`. The [dose engine](dosing-engine.md) documents source hashes, exact pages, excluded formulations and conservative policy controls.

Machine-readable evidence: [release summary](test-results/dose-release-summary.json), [75 PostgreSQL dose workflows](test-results/dose-cases-postgres.json), [66 SQLite general workflows](test-results/dose-release-general-cases.json), [local browser audit summary](quality/dose-browser-summary.json). The [deployment record](deployment.md) identifies the final hosted release. Its live API/dose/DeepSeek acceptance passed, and its five browser workflows completed in 108 seconds with 23 scans reporting zero violations. [Hosted browser report](quality/hosted-dose-browser-summary.json), [hosted acceptance](test-results/hosted-dose-acceptance.json).

These are development-authored synthetic engineering scenarios, not independent clinician-labelled cases or observed patient outcomes. No custom model has been trained, and the existing canonical AI briefing is not presented as a complete RAG service. The owner-confirmed DHA/ethics scope is recorded; independent clinical/pharmacy adjudication and a controlled guideline corpus remain substantive work. The [evaluation package](evaluation/README.md) and [knowledge strategy](knowledge-and-training-strategy.md) define those next steps and the limits of the present evidence.
