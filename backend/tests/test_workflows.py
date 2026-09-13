import json
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from app.models import AuditEvent, AuthSession, Encounter, Referral, User
from app.audit import verify_chain
from app.security import verify_password
from app.config import Settings
from conftest import login, patient, encounter, assess, review_payload, PASSWORD
import pytest


def test_unauthenticated_access_and_opaque_cookie(app):
    with TestClient(app) as client:
        assert client.get("/api/patients").status_code == 401
        response = login(client)
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
        assert '"password":' not in response.text and '"password_hash":' not in response.text and PASSWORD not in response.text
        assert client.get("/api/auth/session").json()["user"]["role"] == "clinician"
        raw = client.cookies.get("ncdai_session")
        with app.state.session_factory() as db:
            assert raw not in [s.id for s in db.scalars(select(AuthSession))]


def test_csrf_and_cross_origin_rejected(client):
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/auth/logout").status_code == 403
    login(client)
    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/auth/session").status_code == 200


def test_logout_revokes_session(client):
    cookie = client.cookies.get("ncdai_session")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("ncdai_session", cookie, path="/api")
    assert client.get("/api/patients").status_code == 401


def test_expired_and_disabled_accounts(client, app):
    with app.state.session_factory() as db:
        db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    assert client.get("/api/patients").status_code == 401
    login(client)
    with app.state.session_factory() as db:
        db.execute(update(User).where(User.email == "clinician@example.test").values(active=False))
        db.commit()
    assert client.get("/api/patients").status_code == 401


def test_login_throttle_and_generic_errors(app):
    with TestClient(app) as client:
        for _ in range(10):
            response = client.post("/api/auth/login", json={"email": "absent@example.test", "password": "wrong"})
            assert response.status_code == 401
            assert response.json()["detail"] == "Email or password is incorrect"
        assert client.post("/api/auth/login", json={"email": "absent@example.test", "password": "wrong"}).status_code == 429


def test_tenant_isolation_every_record_route(client, app):
    item = assess(client, encounter(client))
    referral = client.post(f"/api/encounters/{item['id']}/referrals", json={"reason": "Synthetic review", "destination": "Test facility", "urgency": "soon"}).json()
    with TestClient(app) as other:
        login(other, "other@example.test")
        paths = [f"/api/patients/{item['patient_id']}", f"/api/patients/{item['patient_id']}/encounters", f"/api/encounters/{item['id']}", f"/api/fhir/Patient/{item['patient_id']}", f"/api/fhir/Bundle/{item['id']}"]
        for path in paths:
            assert other.get(path).status_code == 404
        assert other.post("/api/encounters", json={"patient_id": item["patient_id"], "data": {}}).status_code == 404
        assert other.patch(f"/api/encounters/{item['id']}", json={"expected_version": item["version"], "data": {}}).status_code == 404
        assert other.post(f"/api/encounters/{item['id']}/review", json=review_payload(item)).status_code == 404
        assert other.patch(f"/api/referrals/{referral['id']}", json={"status": "accepted"}).status_code == 404
        assert other.get("/api/patients").json() == []
        assert other.get("/api/referrals").json() == []
        assert other.get("/api/dashboard").json()["patients"] == 0


def test_roles_and_no_client_selected_facility(client, app):
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/users").status_code == 403
    item = assess(client, encounter(client))
    with TestClient(app) as admin:
        login(admin, "admin@example.test")
        assert admin.get("/api/audit").status_code == 200
        assert admin.post(f"/api/encounters/{item['id']}/review", json=review_payload(item)).status_code == 403
        response = admin.post("/api/users", json={"email": "new@example.test", "password": "new-test-password-99!", "display_name": "Test user", "role": "clinician"})
        assert response.status_code == 201
        assert '"password":' not in response.text and '"password_hash":' not in response.text and PASSWORD not in response.text
    record = {"external_id": "SYN-002", "given_name": "Test", "family_name": "Patient", "date_of_birth": "1975-01-02", "sex": "female", "synthetic": True, "facility_id": "fake"}
    assert client.post("/api/patients", json=record).status_code == 422


def test_stale_update_and_assessment_invalidation(client):
    item = encounter(client)
    first = client.patch(f"/api/encounters/{item['id']}", json={"expected_version": 1, "data": {"systolic_bp": 140}})
    assert first.status_code == 200
    assert client.patch(f"/api/encounters/{item['id']}", json={"expected_version": 1, "data": {}}).status_code == 409
    assessed = assess(client, first.json())
    stale_review = review_payload(assessed)
    changed = client.patch(f"/api/encounters/{item['id']}", json={"expected_version": assessed["version"], "data": {"systolic_bp": 160}})
    assert changed.json()["assessment"] is None
    assert client.post(f"/api/encounters/{item['id']}/review", json=stale_review).status_code == 409


def test_reassessment_replaces_identity_and_review_version(client):
    first = assess(client, encounter(client))
    second = assess(client, first)
    assert first["assessment"]["id"] != second["assessment"]["id"]
    assert second["version"] == first["version"] + 1
    assert client.post(f"/api/encounters/{first['id']}/review", json=review_payload(first)).status_code == 409


def test_review_completeness_duplicate_and_reason_enforcement(client):
    item = assess(client, encounter(client))
    payload = review_payload(item)
    assert payload["decisions"]
    original = payload["decisions"][:]
    payload["decisions"] = []
    assert client.post(f"/api/encounters/{item['id']}/review", json=payload).status_code == 422
    payload["decisions"] = original + [original[0]]
    assert client.post(f"/api/encounters/{item['id']}/review", json=payload).status_code == 422
    payload["decisions"] = original
    payload["decisions"][0]["action"] = "modify"
    assert client.post(f"/api/encounters/{item['id']}/review", json=payload).status_code == 422
    payload["decisions"][0].update(reason="Synthetic clinical rationale", modified_text="Synthetic alternative recommendation")
    response = client.post(f"/api/encounters/{item['id']}/review", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["review"]["reviewer_name"] == "Clinician"
    assert response.json()["review"]["assessment_snapshot"] == item["assessment"]
    assert response.json()["review"]["input_snapshot"] == item["data"]


def test_reviewed_encounter_immutable_and_retry_safe(client):
    item = assess(client, encounter(client))
    payload = review_payload(item)
    finalized = client.post(f"/api/encounters/{item['id']}/review", json=payload)
    assert finalized.status_code == 200
    assert client.post(f"/api/encounters/{item['id']}/review", json=payload).status_code == 409
    assert client.post(f"/api/encounters/{item['id']}/assess").status_code == 409
    assert client.patch(f"/api/encounters/{item['id']}", json={"expected_version": finalized.json()["version"], "data": {}}).status_code == 409
    assert client.get(f"/api/encounters/{item['id']}").json() == finalized.json()


def test_referral_strict_transition_and_required_outcome(client):
    item = encounter(client)
    response = client.post(f"/api/encounters/{item['id']}/referrals", json={"reason": "Synthetic acute assessment", "destination": "Synthetic receiving team", "urgency": "urgent"})
    assert response.status_code == 201
    url = f"/api/referrals/{response.json()['id']}"
    assert client.patch(url, json={"status": "completed", "outcome": "Already completed"}).status_code == 409
    assert client.patch(url, json={"status": "accepted"}).status_code == 200
    assert client.patch(url, json={"status": "accepted"}).status_code == 409
    assert client.patch(url, json={"status": "completed"}).status_code == 422
    assert client.patch(url, json={"status": "completed", "outcome": "Synthetic receiving assessment recorded"}).status_code == 200
    assert client.patch(url, json={"status": "cancelled"}).status_code == 409
    assert client.get("/api/dashboard").json()["open_referrals"] == 0


def test_audit_atomicity_and_no_clinical_text(client, app):
    item = encounter(client, {"notes": "secret-synthetic-note-52"})
    client.patch(f"/api/encounters/{item['id']}", json={"expected_version": 999, "data": {}})
    with app.state.session_factory() as db:
        events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.sequence)))
        assert verify_chain(events)
        assert not any(e.action == "encounter.update" for e in events)
        assert all("secret-synthetic-note-52" not in json.dumps(e.__dict__, default=str) for e in events)
        events[-1].action = "tampered"
        assert not verify_chain(events)


def test_patient_external_id_uniqueness_and_synthetic_only(client):
    patient(client)
    record = {"external_id": "SYN-001", "given_name": "Test", "family_name": "Patient", "date_of_birth": "1975-01-02", "sex": "female", "synthetic": True}
    assert client.post("/api/patients", json=record).status_code == 409
    record["external_id"] = "NEW"
    record["synthetic"] = False
    assert client.post("/api/patients", json=record).status_code == 422
    record["synthetic"] = True
    record["date_of_birth"] = "2020-01-01"
    assert client.post("/api/patients", json=record).status_code == 422


@pytest.mark.parametrize("data", [
    {"systolic_bp": 80, "diastolic_bp": 100}, {"glucose": 300, "glucose_unit": "mmol/L"},
    {"glucose": 7, "glucose_unit": "mg/L"}, {"oxygen_saturation": 101}, {"respiratory_rate": 0},
    {"observed_at": "2099-01-01T00:00:00Z"}, {"observed_at": "2025-01-01T00:00:00"},
    {"known_ckd": False}, {"symptoms": ["unspecified"]}, {"unknown_extra": "untrusted"},
    {"medications": [{"name": "Example", "code": "Not-Normalized"}]},
])
def test_invalid_measurements_and_unknown_states_rejected(client, data):
    record = patient(client)
    assert client.post("/api/encounters", json={"patient_id": record["id"], "data": data}).status_code == 422


def test_nonfinite_measurements_rejected_without_value_reflection(client):
    record = patient(client)
    response = client.post("/api/encounters", content=json.dumps({"patient_id": record["id"], "data": {"hba1c": float("nan"), "notes": "do-not-reflect-me"}}), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "do-not-reflect-me" not in response.text


def test_fhir_export_references_units_review_and_audit(client, app):
    item = assess(client, encounter(client, {"systolic_bp": 150, "diastolic_bp": 95, "glucose": 180, "glucose_unit": "mg/dL", "egfr": 45}))
    client.post(f"/api/encounters/{item['id']}/review", json=review_payload(item))
    response = client.get(f"/api/fhir/Bundle/{item['id']}")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/fhir+json")
    bundle = response.json()
    resources = [e["resource"] for e in bundle["entry"]]
    assert {"Patient", "Encounter", "Observation", "DocumentReference"} <= {r["resourceType"] for r in resources}
    assert all(r["subject"]["reference"] == f"Patient/{item['patient_id']}" for r in resources if "subject" in r)
    glucose = next(r for r in resources if r["id"].endswith("-glucose"))
    assert glucose["valueQuantity"]["code"] == "mg/dL"
    with app.state.session_factory() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "export.fhir_bundle"))


def test_production_refuses_insecure_settings():
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(environment="production").validate()
    with pytest.raises(ValueError, match="strong"):
        Settings(environment="production", database_url="postgresql://example", secret_key="weak").validate()
