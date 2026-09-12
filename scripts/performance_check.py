"""Bounded local PostgreSQL concurrency rehearsal; no listener or live AI calls.

Uses only the dedicated loopback test database, creates a unique synthetic facility,
does not delete data, and reports measured ASGI client latency rather than network SLOs.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import secrets
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from app.audit import verify_chain
from app.config import Settings
from app.main import create_app
from app.models import AuditEvent
from app.seed import provision_user


def latency(rows):
    values = sorted(row["milliseconds"] for row in rows)
    return {"requests": len(rows), "p50_ms": round(values[math.ceil(len(values) * .5) - 1], 2),
            "p95_ms": round(values[math.ceil(len(values) * .95) - 1], 2),
            "maximum_ms": round(values[-1], 2),
            "status_counts": {str(s): sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})}}


def run():
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "run_status": "incomplete",
              "synthetic_only": True, "workers": 4, "transport": "in-process Starlette TestClient ASGI; real PostgreSQL TCP",
              "database_target": "dedicated loopback PostgreSQL test service", "checks": [], "measurements": {}}
    output = ROOT / "docs/test-results/performance-check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    phase = "configuration"
    app = None
    try:
        url = json.loads((ROOT / ".runtime/postgres-test.json").read_text())["NCDAI_CASE_DATABASE_URL"]
        parsed = make_url(url)
        if not (parsed.drivername == "postgresql+psycopg" and parsed.host == "127.0.0.1"
                and parsed.port == 15432 and parsed.database == "ncdai2_test"):
            raise ValueError("Dedicated test target required")
        app = create_app(Settings(environment="test", database_url=url, auto_create_schema=False))
        with app.state.session_factory() as db:
            report["server_version"] = db.execute(text("SHOW server_version")).scalar_one()
            report["migration"] = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            report["statement_timeout"] = db.execute(text("SHOW statement_timeout")).scalar_one()
            report["lock_timeout"] = db.execute(text("SHOW lock_timeout")).scalar_one()
        run_id = uuid4().hex[:12]
        password, email = secrets.token_urlsafe(32), f"perf-{run_id}@example.invalid"
        with app.state.session_factory() as db:
            user = provision_user(db, email=email, password=password, display_name="Synthetic performance reviewer",
                                  role="supervisor", facility_name=f"Synthetic performance {run_id}")
            facility_id = user.facility_id

        def events():
            with app.state.session_factory() as db:
                return list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility_id).order_by(AuditEvent.sequence)))

        with TestClient(app, raise_server_exceptions=False) as client:
            phase = "setup"
            assert client.get("/api/health/ready").status_code == 200
            auth = client.post("/api/auth/login", json={"email": email, "password": password})
            assert auth.status_code == 200
            client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]

            def patient_payload(i):
                return {"external_id": f"PERF-{run_id}-{i}", "given_name": "Synthetic", "family_name": "Performance",
                        "date_of_birth": "1970-01-01", "sex": "male", "synthetic": True}

            response = client.post("/api/patients", json=patient_payload("initial"))
            assert response.status_code == 201
            patient = response.json()
            response = client.post("/api/encounters", json={"patient_id": patient["id"], "data": {"systolic_bp": 125, "diastolic_bp": 80}})
            assert response.status_code == 201
            encounter = response.json()

            def timed(method, path, **kwargs):
                start = time.perf_counter()
                response = client.request(method, path, **kwargs)
                return {"status": response.status_code, "milliseconds": (time.perf_counter() - start) * 1000}

            phase = "40_concurrent_reads"
            paths = ["/api/dashboard", "/api/patients", f"/api/encounters/{encounter['id']}", "/api/health/ready"]
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = list(pool.map(lambda i: timed("GET", paths[i % len(paths)]), range(40)))
            report["measurements"][phase] = latency(rows)
            assert all(r["status"] == 200 for r in rows)
            report["checks"].append(phase)
            print("Completed 40 concurrent reads", flush=True)

            phase = "32_concurrent_audited_patient_creates"
            before = len(events())
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = list(pool.map(lambda i: timed("POST", "/api/patients", json=patient_payload(i)), range(32)))
            report["measurements"][phase] = latency(rows)
            assert all(r["status"] == 201 for r in rows)
            after = events()
            assert len(after) - before == 32 and verify_chain(after)
            report["checks"].append(phase)
            print("Completed 32 audited writes with an intact audit chain", flush=True)

            phase = "four_competing_updates_one_winner"
            barrier = threading.Barrier(4, timeout=10)

            def compete(i):
                barrier.wait()
                return {**timed("PATCH", f"/api/encounters/{encounter['id']}", json={
                    "expected_version": encounter["version"], "data": {"systolic_bp": 125, "diastolic_bp": 80, "notes": f"Synthetic winner {i}"}}), "candidate": i}

            before = len(events())
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = list(pool.map(compete, range(4)))
            report["measurements"][phase] = latency(rows)
            assert sorted(r["status"] for r in rows) == [200, 409, 409, 409]
            winner = next(r["candidate"] for r in rows if r["status"] == 200)
            saved = client.get(f"/api/encounters/{encounter['id']}").json()
            assert saved["version"] == encounter["version"] + 1
            assert saved["data"]["notes"] == f"Synthetic winner {winner}"
            after = events()
            assert len(after) - before == 1 and verify_chain(after)
            report["checks"].append(phase)
            print("Completed stale-version race: one saved update and three conflicts", flush=True)

            phase = "audit_chain_across_four_database_timezones"
            for zone in ["UTC", "Africa/Nairobi", "America/New_York", "Asia/Kolkata"]:
                with app.state.session_factory() as db:
                    db.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})
                    chain = list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility_id).order_by(AuditEvent.sequence)))
                    assert verify_chain(chain)
            report["checks"].append(phase)
            report["final_audit_events"] = len(events())
            report["run_status"] = "passed"
    except Exception as exc:
        report.update(run_status="failed", failed_check=phase, error_class=type(exc).__name__)
        raise RuntimeError(f"Performance rehearsal failed at {phase} ({type(exc).__name__}); no secret details emitted") from None
    finally:
        if app:
            app.state.engine.dispose()
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    run()
