# Release engineering and reproducible checks

The quality workflow runs on pushes, pull requests and manual dispatch. Its jobs
have read-only repository permissions and do not deploy. Checkout does not retain
Git credentials. Third-party actions are pinned to complete commits verified
against the official repositories on 12 September 2026:

| Action | Verified tag | Commit |
|---|---|---|
| actions/checkout | v6 | d23441a48e516b6c34aea4fa41551a30e30af803 |
| actions/setup-node | v6 | 249970729cb0ef3589644e2896645e5dc5ba9c38 |
| actions/setup-python | v6 | ece7cb06caefa5fff74198d8649806c4678c61a1 |
| actions/upload-artifact | v4 | ea165f8d65b6e75b540449e92b4886f43607fa02 |

References: [checkout](https://github.com/actions/checkout),
[setup-node](https://github.com/actions/setup-node),
[setup-python](https://github.com/actions/setup-python),
[upload-artifact](https://github.com/actions/upload-artifact).
Review action release notes and commit changes before updating pins.

## Automated evidence

1. Backend behavior, security, interoperability, AI-contract and audit-timezone
   regression tests; a dependency vulnerability audit; all frozen synthetic case
   workflows using an isolated SQLite database.
2. Frontend unit tests, TypeScript checks, production bundle and dependency audit
   at high severity. `npm ci` enforces the committed package lock.
3. An ephemeral PostgreSQL 18.4 service: migration/schema agreement; database
   rejection of cross-facility writes, real records, audit tampering, reviewed
   record mutation and invalid referral transitions; transaction rollback;
   32 audit appends using eight workers; audit integrity in four timezones;
   migration downgrade/re-upgrade in a separate database; logical dump and restore
   to another database with table fingerprints, audit chain, triggers and migration
   revision checked; service restart persistence; then all 66 full case workflows
   on a separate, migrated PostgreSQL database.

The database script accepts only its dedicated Actions service. It uses matching
PostgreSQL client binaries inside that container. It never drops a database,
and it never touches the deployment database. GitHub removes the ephemeral
container after the job. Logical dumps remain in process memory and are not
uploaded. Artifacts contain sanitized verification summaries and synthetic case
results, retained for 14 days. Service credentials are deliberately public,
ephemeral test fixtures and must never become deployment credentials.

The [quality run at 9900aca](https://github.com/JGitaka123/NCDAI_2.0/actions/runs/34710140027) passed all three jobs, including backend package construction for Vercel and the PostgreSQL transaction-timeout regression. The package explicitly discovers `app*`; migrations remain deployment source files rather than an accidentally discovered second Python distribution.

CI workflow files and syntax checks are not evidence of a completed CI run.
Only a successful run and its artifacts establish those checks passed at its
recorded commit. Browser and accessibility testing are separately reported;
the quality workflow does not currently launch the full browser harness.

## Explicit live AI evaluation

`live-ai.yml` runs only by manual dispatch with `live_ai` selected. It maps the
repository secret `NCDAI2_0_DEEPSEEK` to the server-only `DEEPSEEK_API_KEY` variable
for the evaluation step. It is never triggered by pull requests or pushes, and
does not print or write the key. No operational patient data is used. This run
can incur provider charges. Its report distinguishes ready responses from
blocked, unavailable or disabled fallbacks. A successful workflow therefore
means the safety/workflow contract passed; it does not imply every provider
request succeeded. Review the status counts before claiming live-provider coverage.

## Reproduction and remaining limits

Run backend checks with `PYTHONPATH=backend python -m pytest backend/tests
tests/database/test_audit_timezone.py -q`. Run the full API cases with
`python scripts/run_case_workflows.py`. In `frontend`, run `npm ci`, `npm test`,
`npm run build`, and `npm audit --audit-level=high`. On Windows, set the environment
variable using PowerShell syntax before running Python. PostgreSQL cloud checks
are reproduced by dispatching the quality workflow, which creates their isolated
service automatically.

The backend requirements pin direct dependencies; a complete transitive Python
hash lock is still required for bit-for-bit dependency reproduction. The
PostgreSQL image pins a patch version rather than an immutable image digest;
runner images and the Python 3.12 patch release can advance. Vulnerability audits
depend on current advisory databases. Passing synthetic tests does not establish
clinical effectiveness, regulatory approval, production load capacity, independent
penetration testing, high availability, or achieved recovery objectives.

Before publishing, inspect the exact staged files. Keep `.env` files, runtime
directories, databases, private source documents, local hosting credentials and
keys out of Git. Do not upload broad runtime directories as CI artifacts. Keep
provider credentials exclusively in server environments or repository secrets.
The repository workflow cannot retrieve a GitHub secret value for local use.
