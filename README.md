# NCDAI 2.0

**A standalone clinician workspace for coordinated adult NCD care.**

NCDAI 2.0 brings patient history, structured assessment, evidence-linked safety checks, clinician decisions and referral follow-through into one workflow. Its major domains are cardiovascular disease, diabetes, chronic respiratory disease, kidney disease, cancer warning signs and multimorbidity. It preserves the familiar NCDAI consultation sequence with a redesigned responsive interface.

This release is **research software for synthetic cases only**. It is not approved for patient care. It does not autonomously diagnose, prescribe or calculate medication doses. The selected medication checks are not a complete drug-interaction service. Engineering tests do not establish clinical accuracy, effectiveness or adoption.

## What is implemented

- Patient registration and search, encounter history, current observations with explicit units and unknown states.
- Deterministic safety and referral prompts with stable rule IDs and inspectable source/version references.
- Optional DeepSeek-first AI review focus, with an OpenAI adapter option. AI selects established items; it cannot create advice, change urgency or remove critical findings.
- Mandatory clinician review of every action: accept, modify, defer or reject, with rationale for changes.
- Version checks and immutable reviewed records, including exact input and assessment snapshots.
- Referral request, acceptance, completion/cancellation and outcome tracking.
- Facility isolation, clinical/administrative roles, revocable cookie sessions, CSRF protection and hash-linked audit events.
- PostgreSQL-ready schema and migrations, with SQLite for isolated local development.
- FHIR R4-oriented exports. Aifya and QAfya integration is deferred until their APIs are supplied; no live EMR connection is claimed.

## Start a local synthetic demonstration

Use Python 3.11 or newer and Node.js 22 or newer. From the repository root on Windows:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend ci
backend/.venv/Scripts/python.exe scripts/local_demo.py --prepare
backend/.venv/Scripts/python.exe scripts/local_demo.py
```

In a second terminal:

```powershell
npm --prefix frontend run dev -- --port 5173
```

Open `http://127.0.0.1:5173`. The prepare command creates a random local demonstration password in ignored `.runtime/demo-access.json`. No password or default account is shipped in source. That file and the local database must remain private. For standard provisioning and non-Windows commands see [backend setup](backend/README.md).

AI is disabled by default. To explicitly enable DeepSeek in the backend process, configure `NCDAI_AI_PROVIDER=deepseek`, `NCDAI_AI_MODEL=deepseek-v4-pro` and `DEEPSEEK_API_KEY` securely. Never put a key in the frontend or commit it. See [AI assurance](docs/ai-assurance.md) for data minimization, limits and OpenAI configuration.

## Inspect the specifications

- [Product and engineering blueprint](docs/blueprint.md)
- [Current capability benchmarks and limitations](docs/benchmarking.md)
- [Requirements traceability](docs/requirements-traceability.md)
- [Clinical safety rules and source rationale](docs/clinical-safety-spec.md)
- [API and data contract](docs/implementation-contract.md)
- [Database verification](docs/database-verification.md)
- [Security review](docs/security-review.md)
- [Frontend behavior and checks](frontend/README.md)

## Reproduce the engineering checks

```powershell
Push-Location backend
.venv/Scripts/python.exe -m pytest tests -q
Pop-Location
npm --prefix frontend test
npm --prefix frontend run build
backend/.venv/Scripts/python.exe scripts/run_case_workflows.py
```

The frozen [66-case catalogue](tests/cases/clinical_cases.json) exercises the six NCD domains. The full workflow runner registers each synthetic patient, saves and assesses the encounter, verifies expected findings and evidence, reviews every action, checks immutability, completes a referral, exports the record and verifies the audit chain. Live provider and real PostgreSQL checks are explicit opt-in runs; mocks are identified as mocks. Dated results must be interpreted with their documented scope.

## Deployment and governance

Vercel configuration routes the frontend and Python API under one origin. A hosted PostgreSQL database, migrations, secure cookies, a strong session secret and explicitly provisioned clinical accounts are required. SQLite and development seeding are refused in production mode. The mandatory synthetic-only gate remains enabled in hosted demonstrations.

No human clinical approvals, national interoperability certification, independent penetration test or clinical-impact evidence are implied by this repository. Guideline approval, clinical validation, privacy decisions, operational ownership and staff training are prerequisites for patient care. The validation protocol, pilot and grant concept are the next phase, after the engineering delivery, as requested by the project owner.

The code is a new implementation; old NCDAI source and private grant documents are not copied here. A project-owner licensing decision remains pending; no open-source license is granted by this README. Dependency licenses remain applicable.
