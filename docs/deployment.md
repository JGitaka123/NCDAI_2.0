# Hosted NCDAI 2.0 release

12 September 2026 · Controlled synthetic demonstration · Application version 0.1

**Open the application: [https://ncdai-2.vercel.app](https://ncdai-2.vercel.app).** The original coral `#FF5757` and unchanged NCDAI logo are restored. Sign-in is required for clinical records. Private account details are delivered separately and are not in this repository.

## Deployed identity

| Item | Recorded value |
|---|---|
| Vercel account/project | `jessegitaka-7527s-projects / ncdai-2` |
| Deployed application commit | `dac1187d76238368a71c1a5bb7c11b23cfe52c6b` |
| Deployment | `dpl_EcgLxsryt2z2wTsEYGonTUXSyS4B` |
| Vercel inspection | [Deployment details](https://vercel.com/jessegitaka-7527s-projects/ncdai-2/EcgLxsryt2z2wTsEYGonTUXSyS4B) |
| Runtime | Vite frontend and Python 3.12 FastAPI services; API function inspected in `fra1` |
| Database | Dedicated Neon `ncdai-2-db`, Free plan, Frankfurt requested at provisioning; server reports PostgreSQL `18.6 (2078fcb)` |
| Schema revision | `20260912_guards` |
| Application database role | `ncdai_app`, separate from the migration owner |
| Clinical rules | `ncdai-2-rules-0.1.2` |
| AI provider/model | DeepSeek / `deepseek-v4-pro` |
| Prompt contract | `ncdai-briefing-select-v1.4` |

The existing `aifya-web` project was not replaced. NCDAI has its own project, database and canonical domain. Repository changes were pushed to `codex/ncdai-2-platform`; deployment is explicit through the Vercel CLI, rather than automatically publishing every push.

## Current clinical-deployment preparation release

The latest release corrects potassium follow-up and acute kidney injury escalation, requires explicit acute negatives for dose references, and verifies a read-only snapshot recovery from the hosted database. **Clinical care activation remains incomplete**, with first-facility and operating details requested; see [the status and remaining dependencies](clinical-deployment-status.md).

Verification on the deployed application commit passed: **381 backend tests**, **28 frontend tests**, **66 general cases and 75 dosing cases on SQLite and PostgreSQL**, **19 database checks**, and **5 hosted browser workflows with 23 accessibility scans and zero reported violations**. Ten backend skips are documented separately from the successful PostgreSQL and live-provider checks. All three [cloud jobs passed](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34714529987).

The [hosted acceptance](test-results/hosted-clinical-readiness-acceptance.json) passed emergency and eligible-dose workflows plus the new suspected-AKI/potassium case. DeepSeek returned a constrained response in 1.606 seconds using 384 tokens. The [hosted browser result](test-results/clinical-readiness-browser.json) covers desktop, tablet, phone, keyboard and administrator navigation. [Machine-readable release evidence](test-results/clinical-readiness-release-summary.json).

## Prior dose-reference release (historical)

The prior version added four bounded Kenya medicine references and contextual withholding, account password/status operations and a pinned Frankfurt API region. The new [release verification](dose-release-verification.md) records 351 passing backend CI tests, 27 frontend tests, 75 full dose-case workflows and the 66 general NCD workflows. Both case sets pass PostgreSQL and SQLite. The application remains a synthetic engineering preview under the owner-confirmed DHA/ethics scope.

That prior Frankfurt deployment passed [hosted API/dose/AI acceptance](test-results/hosted-dose-acceptance.json): emergency dose withheld, eligible amlodipine reference preserved through review, FHIR export and immutable-record controls, valid audit and secure session lifecycle. Its DeepSeek request returned ready with 379 tokens in 1.341 seconds; this is transport/contract evidence, not clinical accuracy.

The region is now declared as `fra1` in `vercel.json`; use `vercel deploy --prod --yes --regions fra1` and inspect the resulting function location. Build machines may still be in `iad1`, which is separate from the verified API execution region. The initial update used the default US API region for fictional acceptance records before this configuration correction. The current deployment uses Frankfurt. No patient-care data was introduced during these checks.

That prior hosted browser verification passed all five workflows in 108 seconds, with 23 accessibility scans reporting zero violations. Desktop, tablet and 375px phone layouts passed, along with keyboard and administrator boundaries. [Hosted browser report](quality/hosted-dose-browser-summary.json). All three jobs also passed on the [exact deployed configuration commit](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34713562013).

## Baseline hosted acceptance (prior branded release)

- Public HTTPS readiness returned 200 with the database connected and rules loaded; patient access without a session returned 401.
- An actual hosted consultation registered a fictional patient, saved and assessed an encounter, retained emergency findings and evidence, requested a live DeepSeek briefing, recorded all clinician decisions, retrieved the immutable review, rejected alteration, completed an identified referral and exported reviewed FHIR resources.
- The live hosted DeepSeek request returned `ready`, using 347 tokens in approximately 3.1 seconds. All deterministic findings and urgency remained unchanged. This single request is additional hosted transport/contract evidence, not a clinical-effectiveness result.
- Secure, HttpOnly, SameSite Strict session cookies were checked; sign-out revoked access and the audit chain verified.
- All five hosted browser tests passed in approximately two minutes. One representative full clinical scenario passed at desktop, tablet and mobile sizes, with keyboard and simulated administrator-interface checks. Twenty automated accessibility scans reported zero violations; manual-review items remain in the report.
- The hosted pooled connection applied the 15-second statement and 5-second lock limits, used the expected migration and restricted role, and denied schema creation and audit-update privileges. Client TLS was verified directly with libpq. The pooler's backend `pg_stat_ssl` observation describes a different connection segment and is recorded separately.

Evidence: [hosted API/AI workflow](test-results/hosted-acceptance.json), [hosted database checks](test-results/hosted-database.json), [hosted browser summary](quality/hosted-browser-summary.json), [hosted desktop screenshot](images-hosted/desktop-dashboard.png), [hosted mobile screenshot](images-hosted/mobile-dashboard.png). Detailed local browser artifacts remain private because diagnostics can contain session-related material; published screenshots contain fictional records only.

The [quality workflow at the prior branded application commit](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34710484479) passed all three jobs. Broader evidence includes 240 backend tests, 21 frontend tests, 19 PostgreSQL recovery/integrity checks, a separate transaction-pooling regression, and all 66 complete synthetic cases on both PostgreSQL and SQLite. Counts and conditional skips are explained in [engineering verification](verification.md); repeated runs do not increase the number of distinct clinical cases.

## Deployment protections and operations

The account owner completed Neon marketplace terms before provisioning. A trusted maintenance process applied migrations and created the initial synthetic supervisor account. The web environment remains `production` with secure cookies, a fixed HTTPS origin, automatic schema creation off and demo seeding disabled.

The automatic Neon project connection was then detached so migration-owner URLs/passwords would not remain in the web runtime. The database resource remains active in the account. Its restricted pooled application URL was installed as the server-only `DATABASE_URL` secret. Provider and session credentials are also server-only. The source tree and built browser bundle were scanned against known application credentials without finding them.

Initial deployment uncovered two packaging/runtime issues that were corrected: explicit Python package discovery was needed to avoid accidentally treating migrations as a second distribution; the pooled database required transaction-local timeouts instead of unsupported connection startup options. Both have reproducible checks in CI. A local build attempt also encountered a Windows dependency file lock; the isolated Vercel build and restored local installation subsequently succeeded.

Use the [operations runbook](operations.md) for migrations, account administration, monitoring and rollback. Changes to application environment variables require redeployment. Keep the private access file private. Provider spend controls, supported identity recovery, hosted backup/restore drills, alerts and scale testing remain operational work before broader reliance.

## Release boundary

The owner confirms DHA and ethics approvals held in office files cover care and medication recommendations. This hosted build remains a **synthetic engineering preview** with selected adult pathways and four bounded medicine references. Independent clinical/pharmacy adjudication, broader source and medicine coverage and operational evaluation remain evidence work. The [validation, pilot and grant package](evaluation/README.md) is drafted; the study has not been conducted or submitted. Aifya EMR and QAfya integration awaits their APIs. The model has not been fine-tuned, and complete guideline RAG remains to be implemented and evaluated as described in the [knowledge strategy](knowledge-and-training-strategy.md).
