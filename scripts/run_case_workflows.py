"""Run every frozen synthetic case through the full persisted API workflow.

Use an isolated temporary database by default. NCDAI_CASE_DATABASE_URL can point
to a dedicated migrated test database; this runner never drops existing tables.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.seed import provision_user

PRIORITY = {"routine": 0, "soon": 1, "urgent": 2, "emergency": 3}


def run(output: Path):
    catalogue = json.loads((ROOT / "tests/cases/clinical_cases.json").read_text())
    started = datetime.now(timezone.utc)
    run_id = uuid4().hex[:10]
    rows = []
    live_ai = os.getenv("NCDAI_CASE_LIVE_AI") == "1"
    if live_ai:
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise RuntimeError("Explicit live run requires configured DEEPSEEK_API_KEY")
        os.environ["NCDAI_AI_PROVIDER"] = "deepseek"
        os.environ["NCDAI_AI_MODEL"] = "deepseek-v4-pro"
    with tempfile.TemporaryDirectory(prefix="ncdai-cases-") as tmp:
        database = os.getenv("NCDAI_CASE_DATABASE_URL") or f"sqlite:///{Path(tmp) / 'cases.db'}"
        app = create_app(Settings(environment="test", database_url=database,
                                  auto_create_schema=not bool(os.getenv("NCDAI_CASE_DATABASE_URL"))))
        password = uuid4().hex + "-Test!"
        email = f"synthetic-{run_id}@example.invalid"
        with app.state.session_factory() as db:
            provision_user(db, email=email, password=password, display_name="Synthetic case reviewer",
                           role="supervisor", facility_name=f"Case test {run_id}")
        with TestClient(app) as client:
            auth = client.post("/api/auth/login", json={"email": email, "password": password})
            assert auth.status_code == 200, auth.text
            client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]

            def request(method, path, expected_status=200, **kwargs):
                response = client.request(method, "/api" + path, **kwargs)
                assert response.status_code == expected_status, f"{method} {path}: {response.status_code} {response.text[:500]}"
                return response.json() if response.content else None

            for case in catalogue["cases"]:
                begin = time.perf_counter()
                row = {"id": case["id"], "domain": case["domain"], "title": case["title"], "steps": []}
                try:
                    today = date.today()
                    patient = request("POST", "/patients", 201, json={
                        "external_id": f"{run_id}-{case['id']}", "given_name": "Synthetic", "family_name": case["id"],
                        "date_of_birth": date(today.year - case["age"], 1, 1).isoformat(), "sex": case["sex"], "synthetic": True})
                    row["steps"].append("register patient")
                    data = {**case["data"], "observed_at": datetime.now(timezone.utc).isoformat()}
                    encounter = request("POST", "/encounters", 201, json={"patient_id": patient["id"], "data": data})
                    row["steps"].append("persist encounter")
                    encounter = request("POST", f"/encounters/{encounter['id']}/assess")
                    assessment = encounter["assessment"]
                    actual = {r["rule_id"] for r in assessment["recommendations"]}
                    expected = case["expected"]
                    assert set(expected["required_rules"]) <= actual, f"Missing rules: {set(expected['required_rules']) - actual}"
                    assert not (set(expected["forbidden_rules"]) & actual), f"Forbidden rules: {set(expected['forbidden_rules']) & actual}"
                    assert PRIORITY[assessment["urgency"]] >= PRIORITY[expected["minimum_urgency"]], "Under-triage against test expectation"
                    assert len(actual) == len(assessment["recommendations"]), "Duplicate rule IDs"
                    for rec in assessment["recommendations"]:
                        assert rec["evidence"], f"No evidence for {rec['rule_id']}"
                        for source in rec["evidence"]:
                            assert source["source_id"] and source["url"].startswith("https://") and source["section"]
                    row.update(urgency=assessment["urgency"], rules=sorted(actual), recommendation_count=len(actual))
                    row["steps"].append("assess expected safety findings and evidence")
                    if live_ai:
                        original = assessment
                        encounter = request("POST", f"/encounters/{encounter['id']}/ai-briefing", json={
                            "assessment_id": original["id"], "expected_version": encounter["version"]})
                        assessment = encounter["assessment"]
                        assert {k: v for k, v in assessment.items() if k != "ai_briefing"} == original
                        briefing = assessment["ai_briefing"]
                        assert briefing["status"] in {"ready", "disabled", "unavailable", "blocked"}
                        assert briefing["urgency"] == original["urgency"]
                        assert all(r in briefing["focus"] for r in original["recommendations"] if r["severity"] == "critical")
                        assert all(r in original["recommendations"] for r in briefing["focus"])
                        row["ai"] = {k: briefing.get(k) for k in ["status", "reason_code", "provider", "model", "prompt_version", "usage", "latency_ms"]}
                        row["steps"].append("request live AI review focus; verify safety-preserving success or fallback")
                    # Exercise every decision type across cases; these are workflow tests,
                    # not human endorsement of clinical content.
                    decisions = []
                    for i, rec in enumerate(assessment["recommendations"]):
                        action = ["accept", "modify", "defer", "reject"][i % 4]
                        decisions.append({"recommendation_id": rec["id"], "action": action,
                                          "reason": "Synthetic workflow test decision; not a clinical endorsement." if action != "accept" else None,
                                          "modified_text": rec["detail"] + " Synthetic reviewer annotation." if action == "modify" else None})
                    reviewed = request("POST", f"/encounters/{encounter['id']}/review", json={
                        "assessment_id": assessment["id"], "expected_version": encounter["version"],
                        "decisions": decisions, "note": "Synthetic complete case workflow."})
                    assert reviewed["status"] == "reviewed"
                    restored = request("GET", f"/encounters/{encounter['id']}")
                    assert restored["review"]["assessment_snapshot"] == assessment
                    assert restored["review"]["input_snapshot"] == encounter["data"]
                    assert restored["review"]["decisions"] == decisions
                    request("PATCH", f"/encounters/{encounter['id']}", 409,
                            json={"expected_version": restored["version"], "data": data})
                    row["steps"].append("review every action; retrieve immutable decisions")
                    # Follow a referral through completion for every case to exercise
                    # continuity of care even where referral is optional clinically.
                    referral = request("POST", f"/encounters/{encounter['id']}/referrals", 201, json={
                        "reason": "Synthetic referral workflow test", "destination": "Synthetic receiving facility",
                        "urgency": assessment["urgency"]})
                    request("PATCH", f"/referrals/{referral['id']}", json={"status": "accepted"})
                    referral = request("PATCH", f"/referrals/{referral['id']}", json={"status": "completed", "outcome": "Synthetic assessment completed; returned to follow-up."})
                    assert referral["status"] == "completed" and referral["outcome"]
                    row["steps"].append("request, accept and complete referral")
                    bundle = request("GET", f"/fhir/Bundle/{encounter['id']}")
                    types = {e["resource"]["resourceType"] for e in bundle["entry"]}
                    assert {"Patient", "Encounter", "DocumentReference"} <= types
                    resource_patient = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Patient")
                    assert resource_patient["id"] == patient["id"]
                    row["steps"].append("export reviewed FHIR document")
                    audit = request("GET", "/audit/verify")
                    assert audit["valid"]
                    row["steps"].append("verify audit integrity")
                    row["status"] = "passed"
                except Exception as exc:
                    row.update(status="failed", error=str(exc))
                row["duration_seconds"] = round(time.perf_counter() - begin, 3)
                rows.append(row)
                print(f"{case['id']} {row['status']}" + (f" AI={row['ai']['status']}" if "ai" in row else ""), flush=True)
            dashboard = request("GET", "/dashboard")
            final_audit = request("GET", "/audit/verify")
    report = {"run_id": run_id, "started_at": started.isoformat(), "completed_at": datetime.now(timezone.utc).isoformat(),
              "kind": "Synthetic API workflow engineering verification, not clinical validation",
              "database": "PostgreSQL" if database.startswith("postgresql") else "SQLite",
              "live_ai_enabled": live_ai,
              "ai_statuses": {status: sum(r.get("ai", {}).get("status") == status for r in rows) for status in ["ready", "disabled", "unavailable", "blocked"]},
              "emr_connections": 0, "total": len(rows),
              "passed": sum(r["status"] == "passed" for r in rows), "failed": sum(r["status"] != "passed" for r in rows),
              "dashboard": dashboard, "audit": final_audit, "cases": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["database", "total", "passed", "failed"]}))
    for row in rows:
        if row["status"] != "passed":
            print(row["id"], row["error"])
    return int(report["failed"] > 0)


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/test-results/case-workflows.json"))
