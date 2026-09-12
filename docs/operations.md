# NCDAI 2.0 operations runbook

This runbook covers the standalone, synthetic-record engineering release. Hosting it with production security settings does not authorize clinical use or establish service availability, recovery objectives, or regulatory compliance. The application does not permit real patient records. Aifya and QAfya integration remains a later, separately tested option.

## Deployment identity and release record

Use a dedicated NCDAI project in the authorized Vercel account. The existing `aifya-web` application is a separate product; do not replace its domain or deployments while publishing NCDAI. For each release record the Git commit, Vercel deployment ID and canonical HTTPS origin, database branch/region, Alembic revision, evidence version, provider/model, test-report locations, operator and time. Do not include passwords or connection URLs in that record. Configuration files alone do not prove a deployment succeeded.

The repository configuration builds Vite in `frontend/` and FastAPI in `backend/`, exposing `app.main:app`. Set the project framework to **Services**. The `/api/(.*)` rewrite precedes the frontend catch-all and preserves the `/api` prefix expected by FastAPI. Both services share the public domain. This matches the newer June 2026 [Vercel Services guide](https://vercel.com/kb/guide/vercel-services); verify the actual build because Services remains a beta feature.

The `.vercelignore` excludes local environments, runtime files, databases, documents, tests and scripts from CLI upload. Inspect the final upload/build contents, including any generated files, before release. Git-connected builds use committed files; `.gitignore` is not a secret scanner. Never commit credentials or private proposal documents. The backend environment template contains empty secret values and must remain a template.

## Configuration and first startup

Create a separate hosted database for the application and separate databases/branches for preview and automated tests. Never point destructive tests at the hosted application database. Prefer application compute near the database; record the selected region rather than treating a provider default as a residency guarantee. A Frankfurt database, if selected for this synthetic demonstration, is outside Kenya.

Set server-side environment values shown in [the template](../backend/.env.example). Production requires PostgreSQL, an explicit strong `NCDAI_SECRET_KEY`, secure cookies, disabled demo seed and an exact HTTPS `NCDAI_PUBLIC_ORIGIN`. Use a stable secret shared by all instances. Set `NCDAI_AI_PROVIDER=deepseek`, the tested explicit model name and `DEEPSEEK_API_KEY` to enable the selected provider. A GitHub Actions secret supplies workflows only; configure the Vercel runtime separately. Do not use a `VITE_` prefix or place credentials in the frontend. Application code reads process environment variables and does not automatically load `.env`.

Only one public origin is allowed for browser mutations. Use the canonical domain for routine access. A preview needs its own exact origin and isolated database, or it cannot be used for write testing. Do not resolve an origin failure using wildcard CORS or trusting arbitrary forwarded headers. Changing a custom domain requires an environment update and a new deployment. Verify HTTPS, cookie scope `/api`, HttpOnly, Secure and SameSite Strict through the browser.

Install the pinned dependencies in a trusted maintenance environment, set `DATABASE_URL` there to the **direct migration-owner** connection, then from `backend/` run:

```text
python -m alembic current
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Record the before/after revisions and compare the new revision to `python -m alembic heads`. Migrations run once as an explicit release step, not on every function startup. Keep automatic schema creation disabled. Preserve a recoverable pre-migration snapshot and inspect the migration before running it on a database containing retained records.

The public web runtime uses a separate least-privilege application role: required table/sequence access, no schema ownership, no superuser and no ability to disable integrity triggers. Administrative migration credentials must not be supplied to the web process. Verify effective privileges and the immutable audit/review triggers on the selected host.

The seed CLI is deliberately local-only. For an empty synthetic deployment, provision initial named accounts through a trusted, temporary maintenance process before public access. Keep the web runtime stopped or protected; use `app.seed.provision_user` with an explicit facility and prompted password in that process, recording the audited account creation. This function rejects duplicate emails and does not overwrite an account. Do not change the hosted web environment to `local` or enable its demo seed flag. The local demonstration procedure is documented in [backend setup](../backend/README.md). Subsequent accounts can use the administrator-only `/api/users` endpoint; administrative access alone does not grant clinical review rights. No shared/default password is supplied. Password rotation/deactivation presently needs controlled administration; there is no self-service recovery interface.

## PostgreSQL connections on serverless hosting

Every function instance can create its own SQLAlchemy connection pool. Size the combined maximum across concurrent instances against the database connection allowance, rather than sizing only one process. The engine permits two pooled connections per instance, no overflow, a five-second pool wait and recycling after 300 seconds; hosted measurements must be confirmed before increasing traffic. `pool_pre_ping` checks reused connections. A PostgreSQL connection has a five-second connection timeout, fifteen-second statement timeout and five-second lock timeout in the application engine.

A provider's pooled application connection can reduce direct-connection pressure. Neon's pooler uses transaction pooling, which restricts session-dependent features; use the direct endpoint for migrations, dump/restore and administrative work. Audit appends use transaction-level advisory locks. The engine disables psycopg automatic prepared statements and applies statement/lock limits using `SET LOCAL` at each transaction begin, rather than unsupported startup options. Administrative autocommit is excluded. A regression confirms that the limits return after commit and rollback. The dedicated hosted Neon pooled connection also passed schema, timeout and restricted-role checks. Keep transactions short and do not retain one while waiting for AI. See [Neon connection pooling](https://neon.com/docs/connect/connection-pooling) and [unsupported startup options](https://neon.com/docs/connect/connection-errors).

## Smoke check and restart

After every deployment, check the root page, bundled scripts/styles and both `/api/health/live` and `/api/health/ready` over the canonical HTTPS domain. Liveness identifies the running process; readiness checks database access, clinical evidence and the expected migration revision on migrated deployments. Keep the explicit release migration check as well. API failures must return API errors rather than the frontend HTML page.

Use an explicitly synthetic account to sign in, create a synthetic patient and encounter, assess, finalize all recommendation decisions, open the saved review, create/complete a referral and export FHIR. Confirm an attempted change to the reviewed encounter is rejected. Check logout invalidates the session. Inspect browser console/network errors, CSP violations and response cache headers; verify no protected record is served through a public cache. The CSP permits bundled same-origin scripts and forbids third-party execution; production smoke testing is still required. Do not relax it to accommodate development tooling.

On Vercel, a new deployment/redeployment creates the running version; data remains in external PostgreSQL. Never rely on function-local files or SQLite for persistence. Restart local development by stopping only its known process and relaunching with the same database and configured secret. Changing the secret invalidates existing CSRF tokens; users should sign in again. A suspected session compromise also requires revoking affected sessions in the database, because secret rotation alone does not remove session rows.

## Monitoring and downtime response

Assign an accountable operator before inviting users. The following are proposed alert rules to tune after baseline measurement, not evidence that monitoring or SLOs are already deployed:

| Signal | Initial action threshold | Operator response |
|---|---|---|
| HTTPS readiness | Three failures one minute apart | Check deployment, database reachability and migration/evidence state; protect access if inconsistent. |
| API server errors | Above 1% for five minutes, with at least 20 requests | Compare with last deployment and database health; investigate sanitized error classes. |
| Core API latency | p95 above one second for 15 minutes, excluding provider calls | Check cold starts, network latency, pool waits and queries; measure before resizing. |
| AI availability | Above 10% unavailable/blocked across at least 20 requests | Check provider quota/status and model contract; disable AI if necessary while retaining deterministic assessment. |
| Audit integrity | Any failed chain verification | Restrict mutations, preserve evidence and escalate to security/clinical owners. |
| Database | Sustained pool saturation, storage below 20% free, repeated locks/timeouts | Investigate workload and provider capacity without bypassing transaction safeguards. |
| Backup age | More than 24 hours since a verified successful backup | Repair backup flow and record the actual exposed recovery interval. |

Log request class, sanitized error code, status, duration, deployment revision and aggregate provider usage. Do not log request/response bodies, notes, patient names, passwords, cookies, CSRF tokens or database/provider secrets. Redact URL query strings and avoid patient identifiers in telemetry labels. Check hosting access logs and log-drain settings as well as application logging. Audit logs remain access-controlled application data. External anchoring of audit head hashes is required to strengthen detection of entire-history replacement or deletion; it is not configured by the in-database chain alone.

During database or network failure, show the failure and keep users from assuming a save succeeded. Reload the encounter before retrying a timed-out write; optimistic concurrency prevents silently overwriting a newer version, but not every create request has an idempotency key. Do not click repeatedly or reconstruct a finalized review by editing database rows. There is no offline record store or automatic offline reconciliation in this release. In a later approved care setting, follow the institution's documented downtime clinical workflow; this demonstration must not become an improvised clinical fallback.

The AI call is optional and bounded to twenty seconds by default. A timeout, rejection or invalid output leaves the deterministic assessment available and visibly records the AI state. An AI outage does not justify suppressing a critical recommendation or substituting another provider without configuration and evaluation.

## Rollback and recovery

For a faulty code deployment, select a previously verified deployment only after confirming it supports the current database schema, evidence state and environment configuration. Vercel supports production rollback; it does not roll back an external database or change its data. Check the selected deployment's environment values and canonical origin, then repeat the smoke workflow. Review [Vercel rollback behavior](https://vercel.com/docs/deployments/rollback-production-deployment) before promotion.

Prefer a forward corrective migration when retained data exists. Do not run `alembic downgrade` on the application database as a routine rollback. A downgrade can discard data or remove safeguards, and a code rollback may still require a compatible database. Capture the incident and the selected release explicitly.

Maintain encrypted, access-restricted backups outside the application's credentials and verify the hosted provider's retention/PITR configuration. A plan name or database connection does not prove backups are enabled. For a logical rehearsal, use matching PostgreSQL clients, a direct administrative connection and custom-format `pg_dump`; restore with `pg_restore --exit-on-error` into a **new isolated database**. Supply passwords through protected environment/credential files, not command arguments or logs. Do not use `--clean` against the source application database.

Before switching to a restored database, compare migration revision, table counts and canonical row fingerprints; verify all facility audit chains, reviewed encounter snapshots, synthetic-only constraints, referral state constraints and roles/triggers. Test sign-in and a new synthetic workflow. Preserve the original database and stop writes during final reconciliation; do not combine histories by rewriting review/audit rows. Revoke restored sessions before exposing a recovered instance. Record backup time, restored-through time, observed data gap, start/end recovery times and validation evidence. RPO of at most 24 hours and RTO of at most four hours remain proposed targets until measured in the hosted environment.

The repository's isolated recovery harness and current execution limitations are documented in [database verification](database-verification.md) and [release engineering](release-engineering.md). A local/CI recovery rehearsal is distinct from a completed drill on the eventual hosted service.

## Retention and operating boundary

Retain only deliberately synthetic records in this deployment. Choose and record an operational retention schedule before a shared demonstration; no automatic patient/review deletion job is included. Dispose of a retired demonstration database and its backups through the responsible operator's recorded retention process, with attention to audit history and exported copies. Accidental real data requires access restriction and a documented incident response; never send it to the provider for troubleshooting.

Before any later real-care release, require institution-approved data handling, lawful hosting/transfer decisions, clinical governance, approved evidence, verified provider terms, independent validation, account lifecycle controls, operational monitoring, tested recovery and a support/downtime agreement. These are future release gates, not accomplished by selecting production environment variables. The validation/pilot protocol and grant concept remain subsequent work requested by the owner.
