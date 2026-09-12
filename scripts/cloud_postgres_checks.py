"""CI-only isolated PostgreSQL durability checks; never target operational data.

Uses PostgreSQL's own client binaries inside the GitHub Actions service container.
Only sanitized summaries are written; dumps and connection strings are not artifacts.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from app.audit import append_audit, verify_chain
from app.db import make_engine, make_sessions
from app.models import AuditEvent, Encounter, Facility, Patient, Referral, User, uid
from app.seed import provision_user


def run():
    assert os.getenv("GITHUB_ACTIONS") == "true", "This script is restricted to ephemeral Actions jobs"
    parsed = make_url(os.environ["NCDAI_CI_DATABASE_URL"])
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert parsed.database == "ncdai_ci_checks" and parsed.username == "ncdai_ci"
    container = os.environ["NCDAI_CI_POSTGRES_CONTAINER"]
    assert re.fullmatch(r"[a-f0-9]{12,64}", container), "Expected the CI service container ID"
    url = parsed.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "synthetic_only": True,
              "kind": "Isolated CI database engineering checks, not clinical validation", "checks": [],
              "limits": ["Single ephemeral PostgreSQL service; no production-scale or high-availability claim.",
                         "Logical recovery and one restart do not certify RPO, RTO or offsite backup.",
                         "Superusers can bypass database triggers; production privileges must be restricted."]}

    def check(name, action):
        started = time.perf_counter()
        row = {"check": name, "passed": False}
        try:
            action()
            row["passed"] = True
        except Exception as error:
            row["error_type"] = type(error).__name__
            raise
        finally:
            row["seconds"] = round(time.perf_counter() - started, 3)
            report["checks"].append(row)
            print(f"{name}: {'passed' if row['passed'] else 'failed'}", flush=True)

    def pg(tool, *args, payload=None):
        result = subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD", container,
                                 tool, "--host=127.0.0.1", f"--username={parsed.username}", *args],
                                env={**os.environ, "PGPASSWORD": parsed.password or ""},
                                input=payload, capture_output=True, timeout=90)
        if result.returncode:
            raise RuntimeError(f"{tool} failed; raw output deliberately suppressed")
        return result.stdout

    engine = None
    try:
        check("migration_upgrade_head", lambda: command.upgrade(config, "head"))
        check("migration_metadata_no_drift", lambda: command.check(config))
        engine = make_engine(url)
        factory = make_sessions(engine)
        def bounded_waits():
            with engine.connect() as connection:
                assert connection.scalar(text("SHOW statement_timeout")) == "15s"
                assert connection.scalar(text("SHOW lock_timeout")) == "5s"
        check("bounded_statement_and_lock_waits", bounded_waits)
        token = uuid4().hex[:10]
        with factory() as db:
            report["server_version"] = db.scalar(text("SHOW server_version"))
            report["migration"] = db.scalar(text("SELECT version_num FROM alembic_version"))
            user = provision_user(db, email=f"ci-{token}@example.invalid", password=uuid4().hex + "Test!",
                                  display_name="Synthetic CI verifier", role="supervisor", facility_name="Synthetic CI facility")
            actor, facility = user.id, user.facility_id
            other = Facility(id=uid(), name="Other synthetic CI facility")
            patient = Patient(id=uid(), facility_id=facility, external_id=f"SYN-{token}", given_name="Synthetic",
                              family_name="CI", date_of_birth=date(1968, 1, 1), sex="female", synthetic=True)
            db.add_all([other, patient]); db.flush()
            patient_id, other_id = patient.id, other.id
            encounter = Encounter(id=uid(), facility_id=facility, patient_id=patient_id, created_by=actor,
                                  data={"synthetic": True}, assessment={"id": "synthetic"},
                                  review={"reviewer_id": actor}, status="reviewed")
            db.add(encounter); db.flush()
            encounter_id = encounter.id
            referral = Referral(id=uid(), facility_id=facility, patient_id=patient_id, encounter_id=encounter_id,
                                destination="Synthetic CI receiver", reason="Synthetic recovery", urgency="soon")
            db.add(referral); db.flush()
            referral_id = referral.id
            append_audit(db, user, "test.database", "encounter", encounter_id)
            db.commit()
            event_id = db.scalar(select(AuditEvent.id).where(AuditEvent.facility_id == facility))

        def rejects(sql, params):
            with factory() as db:
                try:
                    db.execute(text(sql), params); db.commit()
                except DBAPIError:
                    db.rollback()
                    return
                raise AssertionError("Expected database constraint rejection")

        for name, sql, params in [
            ("audit_update_blocked", "UPDATE audit_events SET action='tamper' WHERE id=:id", {"id": event_id}),
            ("audit_delete_blocked", "DELETE FROM audit_events WHERE id=:id", {"id": event_id}),
            ("reviewed_update_blocked", "UPDATE encounters SET version=version+1 WHERE id=:id", {"id": encounter_id}),
            ("reviewed_delete_blocked", "DELETE FROM encounters WHERE id=:id", {"id": encounter_id}),
            ("invalid_referral_transition_blocked", "UPDATE referrals SET status='completed',outcome='synthetic' WHERE id=:id", {"id": referral_id}),
            ("real_record_blocked", "UPDATE patients SET synthetic=false WHERE id=:id", {"id": patient_id}),
            ("cross_facility_encounter_blocked", "INSERT INTO encounters (id,facility_id,patient_id,created_by,data,version,status,created_at,updated_at) VALUES (:id,:facility,:patient,:actor,'{}',1,'draft',now(),now())", {"id": uid(), "facility": other_id, "patient": patient_id, "actor": actor}),
            ("cross_facility_referral_blocked", "INSERT INTO referrals (id,facility_id,patient_id,encounter_id,destination,reason,urgency,status,created_at) VALUES (:id,:facility,:patient,:encounter,'synthetic','synthetic','soon','requested',now())", {"id": uid(), "facility": other_id, "patient": patient_id, "encounter": encounter_id}),
        ]:
            check(name, lambda s=sql, p=params: rejects(s, p))

        def rollback():
            with factory() as db:
                before = len(list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility))))
                draft = Encounter(id=uid(), facility_id=facility, patient_id=patient_id, created_by=actor, data={"synthetic": True})
                draft_id = draft.id
                db.add(draft); db.flush()
                append_audit(db, db.get(User, actor), "test.rollback", "encounter", draft_id)
                db.rollback()
                assert db.get(Encounter, draft_id) is None
                assert len(list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility)))) == before
        check("record_and_audit_rollback_atomicity", rollback)

        def concurrent():
            with factory() as db:
                before = len(list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility))))
            def append(index):
                with factory() as db:
                    append_audit(db, db.get(User, actor), "test.concurrent", "synthetic", str(index))
                    db.commit()
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(append, range(32)))
            with factory() as db:
                events = list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility).order_by(AuditEvent.sequence)))
                assert len(events) == before + 32 and verify_chain(events)
        check("32_concurrent_audit_appends_without_forks", concurrent)

        def zones():
            with factory() as db:
                for zone in ("UTC", "Africa/Nairobi", "America/New_York", "Asia/Kolkata"):
                    db.execute(text("SELECT set_config('TimeZone',:zone,true)"), {"zone": zone})
                    db.expire_all()
                    assert verify_chain(list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility).order_by(AuditEvent.sequence))))
        check("audit_integrity_across_four_timezones", zones)

        def lifecycle():
            with factory() as db:
                db.execute(text("UPDATE referrals SET status='accepted' WHERE id=:id"), {"id": referral_id})
                db.execute(text("UPDATE referrals SET status='completed',outcome='Synthetic verification' WHERE id=:id"), {"id": referral_id})
                db.commit()
        check("valid_referral_lifecycle", lifecycle)

        def fingerprint(target):
            snapshot = {}
            with target.connect() as connection:
                connection.execute(text("SET TIME ZONE 'UTC'"))
                for table in ("facilities", "users", "auth_sessions", "login_attempts", "patients", "encounters", "referrals", "audit_events"):
                    rows = connection.execute(text(f"SELECT row_to_json(t)::text FROM (SELECT * FROM {table} ORDER BY id) t")).scalars().all()
                    snapshot[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
            return snapshot

        def roundtrip():
            name = f"ncdai_ci_migration_{token}"
            pg("createdb", name)
            temporary_url = parsed.set(database=name).render_as_string(hide_password=False)
            try:
                os.environ["DATABASE_URL"] = temporary_url
                command.upgrade(config, "head"); command.check(config)
                command.downgrade(config, "base")
                temporary = make_engine(temporary_url)
                try:
                    assert set(inspect(temporary).get_table_names()) <= {"alembic_version"}
                finally:
                    temporary.dispose()
                command.upgrade(config, "head"); command.check(config)
            finally:
                os.environ["DATABASE_URL"] = url
        check("isolated_migration_upgrade_downgrade_reupgrade", roundtrip)

        before = fingerprint(engine)
        def recovery():
            dump = pg("pg_dump", "--format=custom", parsed.database)
            name = f"ncdai_ci_restore_{token}"
            pg("createdb", name)
            pg("pg_restore", "--exit-on-error", f"--dbname={name}", payload=dump)
            restored = make_engine(parsed.set(database=name).render_as_string(hide_password=False))
            try:
                assert fingerprint(restored) == before
                with make_sessions(restored)() as db:
                    assert verify_chain(list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility).order_by(AuditEvent.sequence))))
                    assert {"audit_immutable", "reviewed_immutable", "referral_transition"} <= set(db.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())
                    assert db.scalar(text("SELECT version_num FROM alembic_version")) == report["migration"]
            finally:
                restored.dispose()
        check("logical_dump_restore_records_chain_triggers_migration", recovery)

        def restart():
            engine.dispose()
            result = subprocess.run(["docker", "restart", "--time=15", container], capture_output=True, timeout=45)
            assert result.returncode == 0, "CI service restart failed"
            deadline = time.monotonic() + 30
            while True:
                try:
                    assert fingerprint(engine) == before
                    break
                except DBAPIError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(1)
        check("service_restart_record_persistence", restart)

        def case_database():
            pg("createdb", "ncdai_ci_cases")
            try:
                os.environ["DATABASE_URL"] = parsed.set(database="ncdai_ci_cases").render_as_string(hide_password=False)
                command.upgrade(config, "head"); command.check(config)
            finally:
                os.environ["DATABASE_URL"] = url
        check("separate_migrated_database_for_full_case_workflows", case_database)
        report["snapshot"] = before
    except Exception as error:
        report["fatal_error_type"] = type(error).__name__
    finally:
        if engine is not None:
            engine.dispose()
        report["passed"] = sum(item["passed"] for item in report["checks"])
        report["failed"] = sum(not item["passed"] for item in report["checks"])
        output = ROOT / "docs/test-results/ci-postgres-verification.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return int("fatal_error_type" in report)


if __name__ == "__main__":
    sys.exit(run())
