# Final independent engineering release audit

Reviewed 12 September 2026 · Workstream 15 · Working-tree source inspection plus focused regression testing.

**Release verdict: suitable to proceed to a controlled, account-protected synthetic demonstration after the hosting acceptance checks below; hosted release is not yet verified. Real-patient clinical release is NO-GO.** This audit found and corrected one additional high-priority session-expiry defect. No other newly demonstrated source defect remains a blocker for the restricted synthetic demonstration in the inspected scope. This is a bounded AI-assisted engineering audit, not a penetration-test certification, licensed clinical adjudication or claim of worldwide ranking.

The source tree was changing during coordinated release work. The final release owner must link this report and passing CI to the actual released commit; earlier test reports describe their recorded execution state and are not retroactive proof of every later change. The Vercel database integration was awaiting owner completion of provider terms during this review. This workstream did not alter Vercel settings, accept terms or claim a live deployment.

**CI update:** [run 34709332691](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34709332691) passed all three jobs at commit `6415fed`: backend **228 passed, 8 skipped**; frontend **21 passed**, production build and dependency audit passed; PostgreSQL **19 integrity/recovery checks and 66 full-case workflows passed**. The downloaded sanitized database reports were inspected for this update. That commit predates this audit's session-expiry correction, so a passing final-head run including its ten regression cases remains required.

## Actionable findings and disposition

| ID | Severity / disposition | Finding and evidence | Required action |
|---|---|---|---|
| RA-01 | **High — fixed and rechecked** | Session authentication replaced an aware PostgreSQL timestamp's offset with UTC, changing its represented instant. In a real PostgreSQL `Africa/Nairobi` session, a token expired one hour earlier incorrectly returned HTTP 200. [Authentication implementation](../backend/app/main.py), [regression tests](../backend/tests/test_session_timezone.py). | Implemented `astimezone(UTC)` for aware values, assigning UTC only to naive SQLite values. The same real PostgreSQL scenario now returns 401. Ten regression cases passed for valid/expired values in naive UTC, UTC, UTC+3, UTC−5 and UTC+5:30. Include these in final CI. |
| RA-02 | **High — hosted acceptance pending** | Source has production configuration validation, same-origin CSRF, API rewrites, migration readiness, security headers and bounded PostgreSQL connections. Those controls have not been demonstrated through the final Vercel domain and selected hosted database. [Configuration](../backend/app/config.py), [database](../backend/app/db.py), [routing](../vercel.json), [operations](operations.md). | Before sharing the hosted demo, verify migrated database/least-privilege application role, server-only secrets, exact HTTPS origin, sign-in/session/logout, persisted review/referral/export, immutable review rejection and API errors under the public route. Complete the provider setup through its owner. |
| RA-03 | **Medium — operating control required** | AI requests are authenticated, single-shot, bounded by time/bytes and omit clinical free text/identifiers; the endpoint does not impose a per-user spend quota. Repeated authorized requests can consume the provider account's budget. [AI implementation](../backend/app/ai.py), [AI endpoint](../backend/app/main.py). | Restrict demo accounts, configure the provider's spending controls and monitor request/rate/usage errors. Disable AI through server configuration when necessary. Add application-level quotas before broad access. No anonymous AI endpoint was found. |
| RA-04 | **CI recovery closed — hosted recovery pending** | CI run 34709332691 completed all 19 PostgreSQL checks, including logical dump/restore with record fingerprints, audit chain/triggers/migration checks, and service restart persistence. It then passed all 66 workflows on a separate migrated database. This supersedes the incomplete local run for those engineering checks. [CI recovery result](test-results/ci-postgres-verification.json), [CI cases](test-results/ci-cases-postgres.json), [database verification](database-verification.md). | Preserve the successful CI evidence and repeat at final head after the session fix. Separately verify the hosted backup configuration and perform a hosted restore drill before relying on retained data. CI recovery does not establish hosted recovery or an achieved RPO/RTO. |
| RA-05 | **Medium — identity operations incomplete for broad use** | Accounts have facility scope, roles, active flags and revocable opaque sessions. Initial provisioning is explicit; account creation requires an administrator. Self-service recovery, MFA/SSO and a full access-revocation administration interface are absent. [Models](../backend/app/models.py), [account endpoints](../backend/app/main.py), [security review](security-review.md). | Use named invited accounts and controlled operator administration for the demonstration. Establish supported recovery/revocation and stronger institutional authentication before clinical or broad multi-facility access. |
| RA-06 | **Medium — scale and availability boundaries** | The app intentionally has no offline save, broad create-request idempotency, longitudinal reminder delivery or horizontally validated capacity. A timed-out create can have an uncertain outcome; the browser instructs users to reload before retrying. The two-connection per-instance pool was tested locally, not on the final serverless pooler. [Browser request handling](../frontend/src/api.ts), [performance report](performance.md). | Retain the explicit offline/uncertain-save messaging and modest demonstration scope. Validate the selected pooled database's timeout options, connection limits and concurrent transactions. Add idempotency and a clinically governed downtime workflow before operational reliance. |

## Clinical-release gates

These are **blocking for real-care use** and are not waived by synthetic tests or deployment authorization:

- The rules are proposed decision support across selected adult cardiovascular, diabetes, respiratory, renal, cancer-warning and multimorbidity pathways. They do not cover every NCD, paediatric care, full diagnostic workup, specialist treatment or comprehensive prescribing. Local clinicians must approve scope, adaptations, vocabulary, critical boundaries and referral timing. [Clinical safety specification](clinical-safety-spec.md).
- Evidence IDs, source sections and versions exist, but an approved, reproducible clinical evidence manifest and local sign-off are incomplete. The independent evidence review identifies specific unresolved source anchors and potassium timing/context limitations. A technical metadata readiness check is not clinical evidence approval. [Evidence review](evidence-review.md).
- AI selects existing rule references and checklist items; it cannot create a new treatment order or remove deterministic critical recommendations. This narrow capability improves containment but does not establish incremental clinical value, consultation-time benefit or patient outcomes. [AI assurance](ai-assurance.md).
- Institution-approved identity, clinical governance, data handling, hosting/transfer decisions, retention/correction processes, provider arrangements, monitoring and recovery remain necessary. The `synthetic` marker is an explicit input restriction, not automatic detection or de-identification of real patient content. [Kenya deployment governance](kenya-deployment.md).
- The 66 synthetic cases are engineering fixtures, not a held-out clinical validation cohort. The validation/pilot protocol and grant concept remain subsequent deliverables requested by the owner.

## Inspected controls and evidence limits

The inspected code derives facility and role from the server session, scopes patient/encounter/referral access, uses parameterized SQL and requires session-bound CSRF for authenticated mutations. Clinical review requires exactly one decision for each current recommendation; non-acceptance requires an explanation. Encounter updates compare the expected version and reviewed snapshots are protected by application checks and database triggers. Referral transitions use a conditional update and database guard. Audit append and clinical mutation share a transaction, with a PostgreSQL transaction advisory lock per facility. The hash chain still requires independent anchoring to strengthen detection of full-history replacement or tail deletion.

Provider destinations are fixed HTTPS URLs. Credentials remain backend-only, redirects/environment proxies are disabled, input is minimized, output references are allowlisted and invalid responses become visible fallbacks. Provider calls do not retain an open clinical transaction; the endpoint reauthenticates after provider latency before persisting. The reviewed UI retains all deterministic recommendations and does not offer model-generated prescribing. The production frontend/API routes share an origin and retain `/api`; runtime acceptance must establish those behaviors on Vercel.

Observed evidence reviewed for this verdict:

| Evidence | Recorded outcome | Interpretation |
|---|---|---|
| [PostgreSQL full-case report](test-results/postgres-live-case-workflows.json) | 66 of 66 persisted synthetic workflows passed; 40 AI-ready responses, 25 intentionally disabled and one unavailable fallback; 596 audit events verified | Complete application workflows and provider containment were exercised. This is not 66 successful model responses. |
| [SQLite full-case report](test-results/case-workflows.json) | 66 of 66 workflows passed, no external AI calls | Separate local-mode engineering evidence; do not add its cases to claim 132 distinct clinical cases. |
| [Concurrency report](test-results/performance-check.json) | 40 reads, 32 audited writes and four competing updates; one winning update; four database timezone checks passed | Modest local ASGI/real-PostgreSQL consistency and latency rehearsal, not public-network capacity. |
| [Browser verification](browser-verification.md) | Five browser tests, one complete representative scenario at three viewports, 20 automated accessibility audits with zero reported violations | Additional UI evidence; not 50 distinct browser cases or complete accessibility certification. Manual-review items remain visible. |
| [CI recovery](test-results/ci-postgres-verification.json) and [CI PostgreSQL cases](test-results/ci-cases-postgres.json) at `6415fed` | 19 checks passed with zero failures, including dump/restore and restart; 66 of 66 workflows passed with no external model calls | Executed Linux/PostgreSQL engineering evidence closes the previous CI recovery gap; hosted recovery remains separate. |
| Session-expiry regression performed in this audit | 10 tests passed; real PostgreSQL expired-session response changed from 200 before the fix to 401 after | Targeted regression evidence for RA-01. Two upstream test-client deprecation warnings were observed. |

The quality workflow was inspected for isolated databases, pinned actions, minimal repository permissions, secret handling and bounded artifact publication. Its recovery checks use an ephemeral service and write sanitized summaries; no operational dump is uploaded. The live AI workflow is manual and separate from normal pushes/PRs. The initial workflow-context error was corrected at `6415fed`, and run 34709332691 successfully executed all three jobs. A further final-head run is needed to include the subsequently corrected session handling. The Python dependency set lacks a complete transitive hash lock and the database container uses a patch tag rather than a digest, so bit-for-bit reproducibility is not established.

## Fifteen workstream perspectives

The development effort applied the following perspectives through coordinated AI workstreams and shared evidence. This list is not a claim that fifteen licensed human specialists signed off, that every review was institutionally independent, or that any percentile ranking was measured.

| Perspective | Reviewable output |
|---|---|
| 1. Clinical pathways and medication safety | [Clinical specification](clinical-safety-spec.md) |
| 2. Backend workflow and transactional behavior | [Implementation contract](implementation-contract.md) |
| 3. Clinician interface and workflow | [Frontend implementation](../frontend/src/App.tsx) |
| 4. Database integrity and recovery | [Database verification](database-verification.md) |
| 5. Security and privacy engineering | [Security review](security-review.md) |
| 6. Interoperability and future EMR adapters | [Interoperability contract](interoperability.md) |
| 7. AI containment and provider assurance | [AI assurance](ai-assurance.md) |
| 8. Clinical scenario engineering | [Case review](case-review.md) |
| 9. Accessibility and browser behavior | [Browser verification](browser-verification.md) |
| 10. Reliability and operations | [Runbook](operations.md) |
| 11. Kenyan institutional deployment | [Governance](kenya-deployment.md) |
| 12. Evidence provenance review | [Evidence review](evidence-review.md) |
| 13. Concurrency and measured performance | [Performance report](performance.md) |
| 14. Release engineering and supply chain | [Release engineering](release-engineering.md) |
| 15. Independent final engineering audit | This document |

The release owner should append the actual hosted acceptance outcome and final CI/deployment identifiers when available, preserving this report's explicit distinction between implemented controls, measured engineering behavior and uncompleted clinical/operational gates.
