from pathlib import Path
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from app.db import make_engine, make_sessions
from app.models import Facility, User, Patient, Encounter, AuditEvent, uid
from app.seed import provision_user
from datetime import date


def test_migration_database_guards(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(config, "head")
    engine = make_engine(url)
    factory = make_sessions(engine)
    with factory() as db:
        user = provision_user(db, email="migration@example.test", password="migration-synthetic-77!", display_name="Migration test")
        event_id = db.scalar(select(AuditEvent.id))
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE audit_events SET action = 'tamper' WHERE id = :id"), {"id": event_id})
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id})
        db.rollback()
        patient = Patient(id=uid(), facility_id=user.facility_id, external_id="SYN-MIGRATION", given_name="Synthetic", family_name="Migration", date_of_birth=date(1970, 1, 1), sex="male", synthetic=True)
        db.add(patient)
        db.flush()
        encounter = Encounter(id=uid(), facility_id=user.facility_id, patient_id=patient.id, created_by=user.id, data={}, assessment={"id": "test"}, review={"reviewer_id": user.id}, status="reviewed")
        db.add(encounter)
        db.commit()
        encounter_id = encounter.id
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE encounters SET version = version + 1 WHERE id = :id"), {"id": encounter_id})
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("DELETE FROM encounters WHERE id = :id"), {"id": encounter_id})
        db.rollback()
        other = Facility(id=uid(), name="Other synthetic facility")
        db.add(other)
        db.flush()
        invalid = Encounter(id=uid(), facility_id=other.id, patient_id=patient.id, created_by=user.id, data={})
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    engine.dispose()
    command.check(config)
    command.downgrade(config, "base")
