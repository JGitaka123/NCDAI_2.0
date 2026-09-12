# NCDAI backend

This release implements a **synthetic-only adult NCD clinical workflow**. It is not authorized for live clinical use. Deterministic advice requires independent clinical signoff. Authentication, review and integration tests do not establish clinical efficacy.

## Local setup (PowerShell)

Run from `backend` using Python 3.11 or newer:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
$env:NCDAI_ENV = 'local'
$env:DATABASE_URL = 'sqlite:///./ncdai.db'
# Generate once and retain securely in local environment configuration.
$env:NCDAI_SECRET_KEY = .venv/Scripts/python.exe -c 'import secrets; print(secrets.token_urlsafe(48))'
.venv/Scripts/python.exe -m alembic upgrade head
$env:NCDAI_ALLOW_DEMO_SEED = 'true'
.venv/Scripts/python.exe -m app.seed --email clinician@example.test --name 'Synthetic Clinician'
.venv/Scripts/python.exe -m app.seed --email supervisor@example.test --name 'Synthetic Supervisor' --role supervisor
$env:NCDAI_ALLOW_DEMO_SEED = 'false'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Provisioning prompts for a new password of at least 14 characters. No default accounts, password, patient data or external model keys are shipped. For noninteractive local setup, supply `NCDAI_SEED_PASSWORD` temporarily in the process environment and remove it afterward. Every account is scoped to its facility. Same `--facility-name` shares a facility; provisioning never overwrites an existing account. Do not commit local database or configuration files. A generated development secret invalidates CSRF tokens after restart unless explicitly retained; using the same configured secret avoids that.

The frontend uses same-origin `/api` requests and the Vite development proxy. The server issues an opaque random HttpOnly, SameSite Strict session cookie. Session credentials are stored as SHA-256 digests. Mutations require the session-bound `X-CSRF-Token`; cross-origin mutations are rejected. PBKDF2-SHA256 passwords use unique 24-byte salts and 600,000 iterations. A database-backed ten-attempt/ten-minute limit applies per email/IP pair; production ingress must also apply distributed IP and account abuse controls. Configure trusted proxy handling explicitly at deployment; arbitrary forwarded headers must not establish security context.

## Run checks

```powershell
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m alembic check
```

Workflow tests use synthetic data and an isolated database. Application tests create SQLAlchemy metadata for speed; migration tests separately verify the deployed database triggers. Do not direct tests at a populated database. PostgreSQL migration and concurrency verification are separate deployment gates where no PostgreSQL service is available.

## Data and review guarantees

- All record reads/writes derive facility from the authenticated user. Composite foreign keys prevent encounter and referral references crossing facilities at database level.
- Clinicians and supervisors perform clinical mutations. Administrators manage users and read/audit their facility; administrative role alone cannot finalize clinical care.
- Nullable observations retain unknown status. Explicit `medications_reviewed`, `allergies_reviewed` and `symptoms_reviewed` distinguish empty lists from completed reconciliation. Naive/future timestamps, invalid units, out-of-range/nonfinite measurements, extra fields, and pediatric registration are rejected.
- Conditional updates enforce expected encounter versions. Editing removes the old assessment. Reassessment replaces assessment identity and increments version. Finalization requires exactly one accountable decision per current recommendation and records the clinician, timestamp, inputs and assessment snapshot.
- Reviewed encounters are immutable via API and migration-installed database triggers. Corrections require a new encounter in this release; linked addenda are a planned extension.
- Referrals follow requested → accepted → completed, or requested/accepted → cancelled. Completion requires an outcome. Referrals may be opened during a draft encounter so review does not delay escalation.
- Every mutation and FHIR export adds an audit event in the same transaction. Audit events omit free text and secrets. PostgreSQL advisory transaction locks serialize facility hash-chain appends; SQLite writes serialize within the single local application process. SQLite is not supported for multiprocess deployment.
- Audit database triggers block update/delete. Hash verification detects changes against retained history; an administrator with database ownership could remove triggers and rewrite history or delete a tail. Independent signed/WORM anchoring, retention/backup and restricted database ownership remain deployment requirements.

## FHIR and production boundary

`GET /api/fhir/Patient/{id}` and `GET /api/fhir/Bundle/{encounter_id}` export R4 resources with LOINC/UCUM measurements and a clinician-reviewed decision document where available. eGFR calculation method is not captured, so export uses a clearly identified local code instead of claiming a specific formula. Synthetic resources carry a synthetic tag. `ncdai.example` is a reserved demonstration base URL, not a live HIE endpoint. Bidirectional Aifya/QAfya adapters and Kenya profile certification require agreed contracts/sandboxes and separate validation.

Production configuration refuses SQLite, weak/unconfigured secrets, insecure cookies, automatic schema creation, and enabled demo provisioning. Set `NCDAI_ENV=production`, `DATABASE_URL=postgresql+psycopg://...`, an explicit strong `NCDAI_SECRET_KEY`, and `NCDAI_SECURE_COOKIES=true`. Apply migrations with a separate database owner before starting the least-privilege application role. Enforce HTTPS at ingress and database transport/storage encryption; maintain tested backups/restores, access review, key rotation, observability, incident response, and institutional approvals. Synthetic-only enforcement remains active even under production configuration until a separately reviewed release enables live data.
