"""Regression for PostgreSQL timestamptz returned in session-local time."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.audit import event_digest


def test_audit_digest_is_invariant_to_database_session_timezone():
    instant = datetime(2026, 9, 12, 15, 20, 30, 123456, tzinfo=timezone.utc)
    fields = {"id": "event", "facility_id": "facility", "sequence": 1,
              "action": "test", "entity_type": "synthetic", "entity_id": "record",
              "actor_id": "clinician", "previous_hash": "0" * 64}
    expected = event_digest(SimpleNamespace(**fields, created_at=instant))
    for offset in (3, -5, 5.5):
        local = instant.astimezone(timezone(timedelta(hours=offset)))
        assert event_digest(SimpleNamespace(**fields, created_at=local)) == expected
    assert event_digest(SimpleNamespace(**fields, created_at=instant.replace(tzinfo=None))) == expected
