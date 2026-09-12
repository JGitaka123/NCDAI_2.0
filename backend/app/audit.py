"""Transactional hash-linked audit events. See README for integrity limits."""
import hashlib
import json
from datetime import timezone
from sqlalchemy import select, text
from .models import AuditEvent, utcnow, uid


def audit_payload(event):
    # Canonical UTC text is stable across SQLite/PostgreSQL.
    # PostgreSQL returns timestamptz in the session timezone. Normalize before
    # dropping the offset; SQLite's naive stored timestamps are already UTC.
    created_at = event.created_at
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc)
    return {"id": event.id, "facility_id": event.facility_id, "sequence": event.sequence,
            "action": event.action, "entity_type": event.entity_type, "entity_id": event.entity_id,
            "actor_id": event.actor_id, "created_at": created_at.replace(tzinfo=None).isoformat(timespec="microseconds"),
            "previous_hash": event.previous_hash}


def event_digest(event):
    return hashlib.sha256(json.dumps(audit_payload(event), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def append_audit(db, user, action, entity_type, entity_id):
    # PostgreSQL serializes each facility's append within the enclosing transaction.
    # SQLite writes serialize at database level; UNIQUE protects against chain forks.
    if db.bind.dialect.name == "postgresql":
        lock_key = int.from_bytes(hashlib.sha256(user.facility_id.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    previous = db.scalar(select(AuditEvent).where(AuditEvent.facility_id == user.facility_id).order_by(AuditEvent.sequence.desc()).limit(1))
    event = AuditEvent(id=uid(), facility_id=user.facility_id, sequence=previous.sequence + 1 if previous else 1,
                       action=action, entity_type=entity_type, entity_id=entity_id, actor_id=user.id,
                       created_at=utcnow(), previous_hash=previous.chain_hash if previous else "0" * 64)
    event.chain_hash = event_digest(event)
    db.add(event)
    db.flush()


def verify_chain(events):
    previous, expected = "0" * 64, 1
    for event in events:
        if event.sequence != expected or event.previous_hash != previous or event.chain_hash != event_digest(event):
            return False
        previous, expected = event.chain_hash, expected + 1
    return True
