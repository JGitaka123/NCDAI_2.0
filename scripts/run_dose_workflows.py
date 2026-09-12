"""Run the same explicit dose challenges against a migrated isolated PostgreSQL DB.

Creates one new fictional facility per run. Never deletes schemas or prints URLs.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.seed import provision_user
from app.dosing import DOSING_VERSION, MANIFEST_SHA256, KENYA_PDF_SHA256
from test_dosing_safety import CASES, test_full_dose_case_workflows

if __name__ == "__main__":
    database_url = os.environ.get("NCDAI_CASE_DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        raise SystemExit("A dedicated migrated NCDAI_CASE_DATABASE_URL PostgreSQL test database is required.")
    start = time.perf_counter()
    app = create_app(Settings(environment="test", database_url=database_url, auto_create_schema=False))
    run_id = secrets.token_hex(8)
    email, password = f"dose-{run_id}@example.invalid", secrets.token_urlsafe(30)
    with app.state.session_factory() as db:
        provision_user(db, email=email, password=password, display_name="Synthetic dose reviewer", role="supervisor", facility_name=f"Synthetic dose {run_id}")
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        test_full_dose_case_workflows(client, app)
        assert client.post("/api/auth/logout").status_code == 204
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs/test-results/dose-cases-postgres.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = dict(checked_on=datetime.now(timezone.utc).isoformat(), backend="PostgreSQL", cases=len(CASES), passed=len(CASES), failed=0,
        seconds=round(time.perf_counter()-start, 2), dosing_version=DOSING_VERSION, manifest_sha256=MANIFEST_SHA256,
        source_pdf_sha256=KENYA_PDF_SHA256, case_definitions_sha256=hashlib.sha256(json.dumps(CASES, sort_keys=True).encode()).hexdigest(),
        scope="Engineering scenarios; no independent clinical adjudication or patient evaluation", case_ids=[c["id"] for c in CASES],
        steps=["registration", "persist structured context", "assessment and expected dose result", "reject incomplete review", "review and lock", "retrieve snapshot", "reject post-review mutation", "FHIR decision document without medication order", "facility audit verification"])
    output.write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(f"PostgreSQL dose workflows: {len(CASES)} passed. No live AI requests.")
