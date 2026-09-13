"""Independent attack-oriented regression checks, using synthetic records only."""
import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from app.middleware import SecurityEnvelope
from app.config import Settings
from app.main import create_app
from app.models import AuthSession, Encounter, LoginAttempt, User
from conftest import login, encounter, assess


@pytest.mark.parametrize("change", ["logout", "expiry", "disabled", "role"])
def test_access_revoked_during_ai_wait_cannot_persist(client, app, monkeypatch, change):
    current = assess(client, encounter(client))

    async def revoke(assessment, *, synthetic, allow_real_patient=False):
        with app.state.session_factory() as db:
            if change == "logout":
                db.execute(delete(AuthSession))
            elif change == "expiry":
                db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
            elif change == "disabled":
                db.execute(update(User).where(User.email == "clinician@example.test").values(active=False))
            else:
                db.execute(update(User).where(User.email == "clinician@example.test").values(role="admin"))
            db.commit()
        return {"status": "ready", "focus": []}

    monkeypatch.setattr("app.ai.build_briefing", revoke)
    response = client.post(f"/api/encounters/{current['id']}/ai-briefing", json={"assessment_id": current["assessment"]["id"], "expected_version": current["version"]})
    assert response.status_code == (403 if change == "role" else 401)
    with app.state.session_factory() as db:
        stored = db.get(Encounter, current["id"])
        assert stored.version == current["version"]
        assert "ai_briefing" not in stored.assessment


def test_administrator_has_no_patient_record_access(client, app):
    current = assess(client, encounter(client))
    with TestClient(app) as admin:
        login(admin, "admin@example.test")
        for path in ["/api/patients", f"/api/patients/{current['patient_id']}", f"/api/patients/{current['patient_id']}/encounters", f"/api/encounters/{current['id']}", "/api/referrals", f"/api/fhir/Patient/{current['patient_id']}", f"/api/fhir/Bundle/{current['id']}"]:
            assert admin.get(path).status_code == 403, path
        assert admin.get("/api/dashboard").status_code == 200
        assert admin.get("/api/audit").status_code == 200
        assert admin.get("/api/users").status_code == 200


def test_validation_and_security_errors_do_not_echo_secrets(client):
    marker = "PRIVATE-INPUT-DO-NOT-REFLECT"
    response = client.post("/api/patients", json={"synthetic": False, "unknown": marker})
    assert response.status_code == 422 and marker not in response.text
    for response in [response, client.post("/api/auth/logout", headers={"Origin": "https://untrusted.example"})]:
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("host", ["good.test/forged", "good.test#fragment", "good.test?path", "good.test@evil.test", "good.test\\path"])
def test_malformed_host_cannot_poison_path(app, host):
    with TestClient(app) as client:
        response = client.get("/api/health/live", headers={"Host": host})
        assert response.status_code == 400


@pytest.mark.parametrize("declared", [False, True])
def test_streamed_body_limit_is_enforced_before_app_runs(declared):
    called = False
    messages = []

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    chunks = iter([{ "type": "http.request", "body": b"a" * 600, "more_body": True},
                   { "type": "http.request", "body": b"b" * 600, "more_body": False}])

    async def receive():
        return next(chunks)

    async def send(message):
        messages.append(message)

    headers = [(b"host", b"testserver")]
    if declared:
        headers.append((b"content-length", b"1200"))
    asyncio.run(SecurityEnvelope(downstream, max_body_bytes=1000)({"type": "http", "method": "POST", "headers": headers}, receive, send))
    assert called is False
    assert messages[0]["status"] == 413
    assert (b"cache-control", b"no-store") in messages[0]["headers"]


def test_rotating_accounts_cannot_bypass_source_rate_limit(app, monkeypatch):
    monkeypatch.setattr("app.main.verify_password", lambda *args: False)
    with TestClient(app) as client:
        for n in range(100):
            assert client.post("/api/auth/login", json={"email": f"absent{n}@example.test", "password": "wrong"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "another@example.test", "password": "wrong"}).status_code == 429
    with app.state.session_factory() as db:
        keys = list(db.scalars(select(LoginAttempt.key)))
        assert keys and all(len(key) == 64 and "@" not in key for key in keys)


def test_account_bucket_applies_without_a_matching_source_bucket(app):
    key = hmac.new(app.state.settings.secret_key.encode(), b"account:clinician@example.test", hashlib.sha256).hexdigest()
    with app.state.session_factory() as db:
        db.add_all([LoginAttempt(key=key) for _ in range(30)])
        db.commit()
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": "clinician@example.test", "password": "irrelevant"})
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "600"


def test_unexpected_failure_redacts_response_and_logs(app, caplog):
    marker = "SYNTHETIC-PRIVATE-SQL-PARAMETER"

    @app.get("/api/test-failure")
    def fail():
        raise RuntimeError(marker)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/test-failure")
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert marker not in response.text and marker not in caplog.text
    assert "details withheld" in caplog.text


def test_explicit_public_origin_survives_proxy_and_cannot_be_spoofed(monkeypatch):
    monkeypatch.setattr("app.main.verify_password", lambda *args: False)
    application = create_app(Settings(environment="test", database_url="sqlite://", auto_create_schema=True,
                                      public_origin="http://127.0.0.1:5173"))
    with TestClient(application, base_url="http://upstream.internal:8010") as client:
        payload = {"email": "absent@example.test", "password": "wrong"}
        permitted = client.post("/api/auth/login", json=payload, headers={"Origin": "http://127.0.0.1:5173"})
        assert permitted.status_code == 401  # Request reaches authentication.
        for origin in ["https://attacker.example", "http://127.0.0.1:5174", "null"]:
            denied = client.post("/api/auth/login", json=payload, headers={"Origin": origin,
                                "X-Forwarded-Host": "127.0.0.1:5173", "X-Forwarded-Proto": "http"})
            assert denied.status_code == 403


@pytest.mark.parametrize("origin", ["*", "https://*.example", "https://user:password@example.test", "https://example.test/path", "https://example.test?x=1", "https://example.test#fragment", "file:///tmp/file", "https://example.test:invalid"])
def test_public_origin_requires_exact_valid_authority(origin):
    with pytest.raises(ValueError):
        Settings(public_origin=origin).validate()
