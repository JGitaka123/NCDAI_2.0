# PostgreSQL verification and recovery

The reproducible database checks use an isolated, loopback-only PostgreSQL instance and synthetic records. Results belong to this local engineering environment; they do not establish clinical validity, national deployment capacity, or a certified recovery objective.

**Cloud verification passed: 19/19 checks, plus 66/66 complete case workflows.** The isolated PostgreSQL 18.4 job at commit `9900aca900e8285e7280c0e768e8e45cbee07d0c` verified migrations, constraints, atomic rollback, concurrent audit writes, four database timezones, bounded waits, logical backup/restore and restart persistence. See the [successful GitHub run](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34710140027), [database result](test-results/ci-postgres-verification.json) and [case results](test-results/ci-cases-postgres.json). A separate PostgreSQL regression also passed, confirming transaction limits are restored after commit/rollback with the transaction-pooler compatible engine. These are ephemeral CI recovery checks, not recovery measurements for the hosted Vercel/Neon deployment.

The initial Windows run remains honestly recorded as incomplete in its original result: it exposed an audit timestamp canonicalization defect and encountered host Python failures during recovery work. A later [local PostgreSQL performance check](performance.md) separately verified 40 reads, 32 audited writes, a four-way stale-update race and audit integrity across four timezones after the fix. The cloud evidence completes the engineering recovery checks without rewriting the earlier failed/incomplete history.

## Reproduce on Windows

From the repository root, with backend dependencies installed:

```powershell
.\backend\.venv\Scripts\python.exe scripts\setup_test_postgres.py
.\backend\.venv\Scripts\python.exe scripts\setup_postgres_backup_tools.py
.\backend\.venv\Scripts\python.exe scripts\verify_postgres.py
$testDatabase = Get-Content .runtime\postgres-test.json | ConvertFrom-Json
$env:NCDAI_CASE_DATABASE_URL = $testDatabase.NCDAI_CASE_DATABASE_URL
.\backend\.venv\Scripts\python.exe scripts\run_case_workflows.py
Remove-Item Env:\NCDAI_CASE_DATABASE_URL
```

Run recovery verification before concurrent application tests: the backup comparison intentionally requires a stable database snapshot. The verifier never deletes a database and refuses hosts, ports, or database names other than its dedicated test target. Repeat runs add uniquely named synthetic facilities and restore databases.

The setup pins `@embedded-postgres/windows-x64` at `18.4.0-beta.17` and verifies the archive's SHA512 integrity before extraction. This package is a distribution of PostgreSQL binaries, not an application dependency or a selected production delivery method. Backup client tools are extracted from the version-pinned PostgreSQL 18.4 Windows binary archive served over HTTPS by EnterpriseDB, the PostgreSQL Windows distributor. That archive is approximately 337 MB; its locally calculated SHA256 is recorded in the ignored runtime configuration and is not presented as an independently published vendor checksum. The actual server version is recorded in the result JSON. The native test runtime was selected after Docker Desktop returned startup errors; unrelated Docker applications are not modified.

Random credentials, initialized database files, server logs and logical backups stay in ignored `.runtime`. PostgreSQL binds only to `127.0.0.1:15432` and requires SCRAM authentication. Do not publish the runtime directory or echo the connection URL. The local Windows account and its filesystem access controls remain the trust boundary for these synthetic test artifacts.

## Checks and evidence

The Windows verifier writes [its machine-readable result](../tests/database/postgres-verification.json); the initial file is a manually recorded incomplete status based on observed tool outputs. The successful cloud verifier writes [a separate result](test-results/ci-postgres-verification.json) with server version, migration revision, named checks, timings and table fingerprints. It emits success only after every required assertion succeeds and exits with an error on failure. Preserve each result's environment and commit when assessing coverage.

- Upgrade to Alembic head and verify no difference from SQLAlchemy metadata.
- Upgrade, downgrade, and re-upgrade in a separate uniquely named database.
- Reject updates and deletion of append-only audit events.
- Reject updates and deletion of reviewed encounters.
- Reject cross-facility encounter/patient and referral/encounter references through composite foreign keys.
- Reject non-synthetic patient records at the database boundary.
- Reject an invalid referral transition and exercise the valid requested → accepted → completed path.
- Roll back a clinical record and its audit append together, leaving neither committed.
- Append 32 audit events across eight concurrent workers, preserving sequence and hash linkage without forks.
- Verify the audit chain under UTC, Nairobi, New York and Kolkata PostgreSQL session timezones. This exposed and corrected an actual timezone canonicalization defect: timestamps must be converted to UTC before removing their offset for hashing.
- Confirm application connections use a 15-second statement timeout and a 5-second lock timeout. Connection establishment is bounded to 5 seconds.
- Create a custom-format logical backup, restore into a separate database, and compare exact row fingerprints for all eight application tables, including facilities, users, sessions, login attempts, patients, encounters, referrals and audit events.
- Verify the restored audit chain and immutable-record triggers.
- Restart only the dedicated native test server and verify persisted row fingerprints.

The separate full-case runner tests the clinical application through its API using the migrated PostgreSQL schema. Its case report distinguishes those full workflows from this lower-level database exercise.

## Deployment requirements remaining

Production deployment needs a database administrator to provision separate migration and application roles. The application role should have only the required table and sequence privileges and no ability to disable triggers, change schema, or act as superuser. These tests use an isolated privileged test account; the existence of a trigger does not protect against a database administrator who can disable it. Facility filters in application queries and composite relationship constraints complement each other; database row-level security has not been claimed.

Logical backup and restore here is a functional recovery rehearsal. Operational recovery requires encrypted offsite backups, restricted keys, point-in-time recovery/WAL retention, backup monitoring, independent integrity checking, and documented recurring restore drills. RPO ≤24 hours and RTO ≤4 hours in the blueprint are proposed targets requiring measurement in the eventual hosted infrastructure, not achievements from this local test.

Production monitoring should cover availability, connection pool saturation, lock waits, query latency, storage headroom, migration state, backup age, replication lag where applicable, and audit-chain verification failures. Failures must reach an accountable operator without patient information in notification payloads.

Database encryption at rest, TLS transport, restricted network access, retention decisions, audit export to separately controlled storage, data residency, and disaster recovery infrastructure must be verified in the selected Kenyan deployment environment. None is inferred from this local synthetic test.
