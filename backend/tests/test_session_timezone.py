"""Expiry means the same instant for SQLite and offset-aware PostgreSQL rows."""
from datetime import timedelta, timezone
import secrets

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select

from app.models import AuthSession, User, utcnow
from app.security import token_hash


@pytest.mark.parametrize("database_offset_hours", [None, 0, 3, -5, 5.5])
@pytest.mark.parametrize("expires_in_minutes,expected_status", [(-60, 401), (60, 200)])
def test_session_expiry_preserves_instant(app, database_offset_hours, expires_in_minutes, expected_status):
    token = secrets.token_urlsafe(48)
    with app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.email == "clinician@example.test"))
        db.add(AuthSession(id=token_hash(token), user_id=user.id,
                           expires_at=utcnow() + timedelta(minutes=expires_in_minutes)))
        db.commit()

    def as_postgresql_timestamp(session, context):
        # SQLite removes timezone information; mimic the offset-aware timestamp
        # PostgreSQL returns without changing the represented expiration instant.
        if database_offset_hours is not None:
            session.expires_at = session.expires_at.replace(tzinfo=timezone.utc).astimezone(
                timezone(timedelta(hours=database_offset_hours)))

    event.listen(AuthSession, "load", as_postgresql_timestamp)
    try:
        with TestClient(app) as client:
            client.cookies.set(app.state.settings.cookie_name, token)
            response = client.get("/api/auth/session")
            assert response.status_code == expected_status
    finally:
        event.remove(AuthSession, "load", as_postgresql_timestamp)
