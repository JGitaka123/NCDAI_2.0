"""Account lifecycle integration: credentials, scope, audit and revocation."""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.models import AuditEvent, AuthSession, User, uid
from app.security import token_hash, verify_password
from conftest import PASSWORD, login

NEW_PASSWORD = "A new synthetic password 84!"


def account(app, email):
    with app.state.session_factory() as db:
        return db.scalar(select(User).where(User.email == email))


def test_password_change_revokes_other_sessions_and_preserves_current(app):
    with TestClient(app) as current, TestClient(app) as other, TestClient(app) as unrelated:
        login(current)
        login(other)
        login(unrelated, "other@example.test")
        current_token = current.cookies.get(app.state.settings.cookie_name)
        old_hash = account(app, "clinician@example.test").password_hash
        response = current.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        assert response.status_code == 200
        assert response.json() == {"status": "password_changed", "other_sessions_revoked": 1}
        assert current.get("/api/auth/session").status_code == 200
        assert other.get("/api/auth/session").status_code == 401
        assert unrelated.get("/api/auth/session").status_code == 200
        user = account(app, "clinician@example.test")
        assert user.password_hash != old_hash
        assert verify_password(NEW_PASSWORD, user.password_hash)
        assert not verify_password(PASSWORD, user.password_hash)
        with app.state.session_factory() as db:
            assert db.get(AuthSession, token_hash(current_token)) is not None
            actions = list(db.scalars(select(AuditEvent).where(AuditEvent.actor_id == user.id)))
            assert sum(e.action == "user.password_change" for e in actions) == 1
            assert all(NEW_PASSWORD not in str(e.__dict__) and PASSWORD not in str(e.__dict__) for e in actions)
        assert other.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 401
        assert other.post("/api/auth/login", json={"email": user.email, "password": NEW_PASSWORD}).status_code == 200


def test_wrong_current_password_does_not_change_hash_or_revoke_sessions(app):
    with TestClient(app) as current, TestClient(app) as other:
        login(current)
        login(other)
        before = account(app, "clinician@example.test").password_hash
        response = current.post("/api/auth/change-password", json={"current_password": "incorrect", "new_password": NEW_PASSWORD})
        assert response.status_code == 400
        assert account(app, "clinician@example.test").password_hash == before
        assert other.get("/api/auth/session").status_code == 200
        with app.state.session_factory() as db:
            assert db.scalar(select(AuditEvent).where(AuditEvent.action == "user.password_change_failed")) is not None


def test_password_reauthentication_throttle(client):
    for _ in range(5):
        assert client.post("/api/auth/change-password", json={"current_password": "incorrect", "new_password": NEW_PASSWORD}).status_code == 400
    response = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 429 and response.headers["Retry-After"] == "600"
    assert client.get("/api/auth/session").status_code == 200


@pytest.mark.parametrize("new_password", ["too short", " " * 14, PASSWORD, "x" * 257])
def test_invalid_new_password_rejected_without_echo(client, new_password):
    response = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": new_password})
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert new_password not in response.text


def test_password_whitespace_is_preserved(client, app):
    password = "  synthetic padded password 87!  "
    assert client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": password}).status_code == 200
    stored = account(app, "clinician@example.test").password_hash
    assert verify_password(password, stored)
    assert not verify_password(password.strip(), stored)


def test_password_change_authentication_and_csrf(app):
    with TestClient(app) as client:
        body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        assert client.post("/api/auth/change-password", json=body).status_code == 401
        login(client)
        client.headers.pop("X-CSRF-Token")
        assert client.post("/api/auth/change-password", json=body).status_code == 403


def test_admin_deactivation_revokes_sessions_reactivation_requires_login(app):
    with TestClient(app) as admin, TestClient(app) as target_client:
        login(admin, "admin@example.test")
        login(target_client)
        target = account(app, "clinician@example.test")
        response = admin.patch(f"/api/users/{target.id}/status", json={"active": False})
        assert response.status_code == 200 and response.json()["active"] is False
        assert "password_hash" not in response.json()
        assert target_client.get("/api/auth/session").status_code == 401
        assert target_client.post("/api/auth/login", json={"email": target.email, "password": PASSWORD}).status_code == 401
        assert admin.patch(f"/api/users/{target.id}/status", json={"active": True}).status_code == 200
        assert target_client.get("/api/auth/session").status_code == 401
        assert target_client.post("/api/auth/login", json={"email": target.email, "password": PASSWORD}).status_code == 200
        with app.state.session_factory() as db:
            actions = list(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == target.id)))
            assert actions.count("user.deactivate") == actions.count("user.reactivate") == 1


@pytest.mark.parametrize("email", ["clinician@example.test", "supervisor@example.test"])
def test_only_admin_can_change_status(app, email):
    with TestClient(app) as client:
        login(client, email)
        target = account(app, "admin@example.test")
        assert client.patch(f"/api/users/{target.id}/status", json={"active": False}).status_code == 403
        assert account(app, target.email).active


def test_admin_cannot_change_other_facility_account(app):
    with TestClient(app) as client:
        login(client, "admin@example.test")
        target = account(app, "other@example.test")
        assert client.patch(f"/api/users/{target.id}/status", json={"active": False}).status_code == 404
        assert account(app, target.email).active


def test_last_active_admin_is_protected(app):
    with TestClient(app) as client:
        login(client, "admin@example.test")
        admin = account(app, "admin@example.test")
        response = client.patch(f"/api/users/{admin.id}/status", json={"active": False})
        assert response.status_code == 409 and "last active administrator" in response.json()["detail"]
        assert account(app, admin.email).active


def test_self_deactivation_blocked_with_multiple_administrators(app, test_password_hash):
    admin = account(app, "admin@example.test")
    with app.state.session_factory() as db:
        db.add(User(id=uid(), facility_id=admin.facility_id, email="second-admin@example.test", display_name="Second admin",
                    password_hash=test_password_hash, role="admin"))
        db.commit()
    with TestClient(app) as client:
        login(client, admin.email)
        response = client.patch(f"/api/users/{admin.id}/status", json={"active": False})
        assert response.status_code == 409 and "own account" in response.json()["detail"]


def test_admin_can_deactivate_second_admin_without_losing_own_access(app, test_password_hash):
    admin = account(app, "admin@example.test")
    with app.state.session_factory() as db:
        second = User(id=uid(), facility_id=admin.facility_id, email="second-admin@example.test", display_name="Second admin",
                      password_hash=test_password_hash, role="admin")
        db.add(second)
        db.commit()
        second_id = second.id
    with TestClient(app) as client:
        login(client, admin.email)
        assert client.patch(f"/api/users/{second_id}/status", json={"active": False}).status_code == 200
        assert client.get("/api/users").status_code == 200
        assert account(app, admin.email).active


def test_account_status_auth_csrf_and_strict_boolean(app):
    target = account(app, "clinician@example.test")
    path = f"/api/users/{target.id}/status"
    with TestClient(app) as client:
        assert client.patch(path, json={"active": False}).status_code == 401
        login(client, "admin@example.test")
        assert client.patch(path, json={"active": "false"}).status_code == 422
        client.headers.pop("X-CSRF-Token")
        assert client.patch(path, json={"active": False}).status_code == 403


def test_unchanged_status_is_idempotent_without_duplicate_audit(app):
    target = account(app, "clinician@example.test")
    with TestClient(app) as client:
        login(client, "admin@example.test")
        for _ in range(2):
            assert client.patch(f"/api/users/{target.id}/status", json={"active": True}).status_code == 200
        with app.state.session_factory() as db:
            assert db.scalar(select(AuditEvent).where(AuditEvent.action == "user.reactivate")) is None


@pytest.mark.parametrize("operation", ["password", "deactivate"])
def test_account_change_rolls_back_if_audit_fails(app, monkeypatch, operation):
    with TestClient(app) as actor, TestClient(app) as target_client:
        login(actor, "admin@example.test" if operation == "deactivate" else "clinician@example.test")
        login(target_client)
        target = account(app, "clinician@example.test")
        before = target.password_hash

        def unavailable_audit(*args, **kwargs):
            raise RuntimeError("Synthetic audit storage failure")

        monkeypatch.setattr("app.main.append_audit", unavailable_audit)
        if operation == "password":
            response = actor.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        else:
            response = actor.patch(f"/api/users/{target.id}/status", json={"active": False})
        assert response.status_code == 500
        saved = account(app, target.email)
        assert saved.active and saved.password_hash == before
        assert target_client.get("/api/auth/session").status_code == 200
        assert NEW_PASSWORD not in response.text


def test_postgres_password_and_administrator_races():
    """Two critical races on an opt-in isolated PostgreSQL test service."""
    from concurrent.futures import ThreadPoolExecutor
    import os
    import secrets
    import threading
    from uuid import uuid4
    from sqlalchemy import func
    from sqlalchemy.engine import make_url
    from app.audit import verify_chain
    from app.config import Settings
    from app.main import create_app
    from app.seed import provision_user

    url = os.getenv("NCDAI_DATABASE_TEST_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test database not configured")
    target = make_url(url)
    assert target.host in {"127.0.0.1", "localhost"}
    assert target.database in {"ncdai2_test", "ncdai_ci_checks"}
    application = create_app(Settings(environment="test", database_url=url))
    suffix = uuid4().hex
    password, updated_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    with application.state.session_factory() as db:
        a = provision_user(db, email=f"race-a-{suffix}@example.invalid", password=password,
                           display_name="Synthetic race administrator A", role="admin")
        from app.models import Facility
        b = provision_user(db, email=f"race-b-{suffix}@example.invalid", password=password,
                           display_name="Synthetic race administrator B", role="admin", facility=db.get(Facility, a.facility_id))
        a_id, b_id, facility_id = a.id, b.id, a.facility_id
        a_email, b_email = a.email, b.email
    try:
        with TestClient(application) as primary, TestClient(application) as racing_login, TestClient(application) as second_admin:
            def sign_in(client, email, supplied_password):
                response = client.post("/api/auth/login", json={"email": email, "password": supplied_password})
                if response.status_code == 200:
                    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
                return response

            assert sign_in(primary, a_email, password).status_code == 200
            barrier = threading.Barrier(2, timeout=10)

            def change():
                barrier.wait()
                return primary.post("/api/auth/change-password", json={"current_password": password, "new_password": updated_password})

            def old_sign_in():
                barrier.wait()
                return sign_in(racing_login, a_email, password)

            with ThreadPoolExecutor(max_workers=2) as pool:
                changed, attempted = pool.submit(change), pool.submit(old_sign_in)
                assert changed.result().status_code == 200
                assert attempted.result().status_code in {200, 401}
            # If old-password login won the lock first, its issued session was
            # revoked by the password change; if it lost, credentials failed.
            assert racing_login.get("/api/auth/session").status_code == 401
            assert primary.get("/api/auth/session").status_code == 200
            assert sign_in(second_admin, b_email, password).status_code == 200
            barrier = threading.Barrier(2, timeout=10)

            def deactivate(client, other_id):
                barrier.wait()
                return client.patch(f"/api/users/{other_id}/status", json={"active": False}).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(deactivate, primary, b_id)
                second = pool.submit(deactivate, second_admin, a_id)
                assert sorted([first.result(), second.result()]) == [200, 401]
            with application.state.session_factory() as db:
                assert db.scalar(select(func.count()).select_from(User).where(
                    User.facility_id == facility_id, User.role == "admin", User.active.is_(True))) == 1
                assert verify_chain(list(db.scalars(select(AuditEvent).where(
                    AuditEvent.facility_id == facility_id).order_by(AuditEvent.sequence))))
    finally:
        application.state.engine.dispose()
