"""Verify an explicitly isolated synthetic PostgreSQL database and recovery.

Never point this at operational data. Setup is in setup_test_postgres.py. This
script does not delete databases. It creates a uniquely named restore database.
"""
from __future__ import annotations

import concurrent.futures
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url
from app.db import make_engine, make_sessions
from app.models import Facility, Patient, Encounter, Referral, AuditEvent, uid
from app.seed import provision_user
from app.audit import append_audit, verify_chain


def verify():
    runtime = ROOT / ".runtime"
    settings = json.loads((runtime / "postgres-test.json").read_text())
    url = settings["NCDAI_CASE_DATABASE_URL"]
    parsed = make_url(url)
    assert parsed.host == "127.0.0.1" and parsed.port == 15432
    assert parsed.database == "ncdai2_test", "Only the dedicated test database is accepted"
    os.environ["DATABASE_URL"] = url
    os.environ["PGCONNECT_TIMEOUT"] = "10"
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    results = []

    def record(name, fn):
        start = time.perf_counter()
        fn()
        results.append({"check": name, "passed": True, "seconds": round(time.perf_counter()-start, 3)})

    record("migration_upgrade_head", lambda: command.upgrade(config, "head"))
    record("migration_metadata_no_drift", lambda: command.check(config))
    engine = make_engine(url)
    factory = make_sessions(engine)
    run = uuid4().hex[:10]
    with factory() as db:
        server_version = db.scalar(text("SHOW server_version"))
        migration = db.scalar(text("SELECT version_num FROM alembic_version"))
        user = provision_user(db, email=f"database-{run}@example.invalid", password=uuid4().hex + "Test!", display_name="Synthetic database verifier", role="supervisor", facility_name=f"Database verification {run}")
        user_id, facility_id = user.id, user.facility_id
        other = Facility(id=uid(), name=f"Other synthetic facility {run}")
        patient = Patient(id=uid(), facility_id=facility_id, external_id=f"SYN-DB-{run}", given_name="Synthetic", family_name="Database", date_of_birth=date(1968, 1, 1), sex="female", synthetic=True)
        db.add_all([other, patient]); db.flush()
        patient_id, other_id = patient.id, other.id
        enc = Encounter(id=uid(), facility_id=facility_id, patient_id=patient_id, created_by=user_id, data={"synthetic": True}, assessment={"id": "synthetic-assessment"}, review={"reviewer_id": user_id}, status="reviewed")
        db.add(enc); db.flush()
        encounter_id = enc.id
        referral = Referral(id=uid(), facility_id=facility_id, patient_id=patient_id, encounter_id=encounter_id, destination="Synthetic receiving facility", reason="Synthetic recovery verification", urgency="soon")
        db.add(referral); db.flush()
        referral_id = referral.id
        append_audit(db, user, "test.database", "encounter", encounter_id)
        db.commit()
        event_id = db.scalar(select(AuditEvent.id).where(AuditEvent.facility_id == facility_id))

    def configured_timeouts():
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW statement_timeout")) == "15s"
            assert connection.scalar(text("SHOW lock_timeout")) == "5s"
    record("postgres_sessions_have_bounded_statement_and_lock_waits", configured_timeouts)

    def rejects(statement, values):
        with factory() as db:
            try:
                db.execute(text(statement), values)
                db.commit()
            except DBAPIError:
                db.rollback()
                return
            raise AssertionError("Expected database constraint to reject mutation")

    for name, sql, parameters in [
        ("audit_update_blocked", "UPDATE audit_events SET action='tamper' WHERE id=:id", {"id": event_id}),
        ("audit_delete_blocked", "DELETE FROM audit_events WHERE id=:id", {"id": event_id}),
        ("reviewed_update_blocked", "UPDATE encounters SET version=version+1 WHERE id=:id", {"id": encounter_id}),
        ("reviewed_delete_blocked", "DELETE FROM encounters WHERE id=:id", {"id": encounter_id}),
        ("referral_invalid_transition_blocked", "UPDATE referrals SET status='completed', outcome='test' WHERE id=:id", {"id": referral_id}),
        ("encounter_cross_facility_foreign_key", "INSERT INTO encounters (id,facility_id,patient_id,created_by,data,version,status,created_at,updated_at) VALUES (:id,:facility,:patient,:actor,'{}',1,'draft',now(),now())", {"id":uid(),"facility":other_id,"patient":patient_id,"actor":user_id}),
        ("referral_cross_facility_foreign_key", "INSERT INTO referrals (id,facility_id,patient_id,encounter_id,destination,reason,urgency,status,created_at) VALUES (:id,:facility,:patient,:encounter,'synthetic','synthetic','soon','requested',now())", {"id":uid(),"facility":other_id,"patient":patient_id,"encounter":encounter_id}),
        ("real_record_database_guard", "UPDATE patients SET synthetic=false WHERE id=:id", {"id":patient_id}),
    ]:
        record(name, lambda s=sql,p=parameters: rejects(s,p))

    def rollback_atomicity():
        with factory() as db:
            user = db.get(__import__("app.models", fromlist=["User"]).User, user_id)
            before = db.scalar(text("SELECT count(*) FROM audit_events WHERE facility_id=:id"), {"id":facility_id})
            draft = Encounter(id=uid(), facility_id=facility_id, patient_id=patient_id, created_by=user_id, data={"rollback":True})
            draft_id = draft.id
            db.add(draft); db.flush()
            append_audit(db,user,"test.rollback","encounter",draft_id)
            db.rollback()
            assert db.get(Encounter,draft_id) is None
            assert before == db.scalar(text("SELECT count(*) FROM audit_events WHERE facility_id=:id"), {"id":facility_id})
    record("transactional_record_and_audit_rollback",rollback_atomicity)

    def concurrent_audit():
        def write(i):
            from app.models import User
            with factory() as db:
                user = db.get(User,user_id)
                append_audit(db,user,"test.concurrent","synthetic",str(i))
                db.commit()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write,range(32)))
        with factory() as db:
            events=list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id==facility_id).order_by(AuditEvent.sequence)))
            assert len(events)==34 and verify_chain(events)
    record("32_concurrent_audit_appends_no_fork", concurrent_audit)

    def timezone_invariant():
        with factory() as db:
            for zone in ("UTC", "Africa/Nairobi", "America/New_York", "Asia/Kolkata"):
                db.execute(text("SELECT set_config('TimeZone',:zone,true)"),{"zone":zone})
                db.expire_all()
                events=list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id==facility_id).order_by(AuditEvent.sequence)))
                assert verify_chain(events), f"Audit chain changed in {zone}"
    record("audit_hashes_invariant_across_four_postgres_timezones",timezone_invariant)

    def legal_referral():
        with factory() as db:
            db.execute(text("UPDATE referrals SET status='accepted' WHERE id=:id"),{"id":referral_id})
            db.execute(text("UPDATE referrals SET status='completed',outcome='Synthetic verified' WHERE id=:id"),{"id":referral_id})
            db.commit()
    record("referral_valid_lifecycle",legal_referral)

    def database_fingerprint(db_engine):
        snapshot={}
        with db_engine.connect() as conn:
            for table in ("facilities","users","auth_sessions","login_attempts","patients","encounters","referrals","audit_events"):
                rows=conn.execute(text(f"SELECT row_to_json(t)::text FROM (SELECT * FROM {table} ORDER BY id) t")).scalars().all()
                snapshot[table]={"count":len(rows),"sha256":hashlib.sha256("\n".join(rows).encode()).hexdigest()}
        return snapshot

    # pg_dump/restore use inherited PGPASSWORD, never credentials in argv/output.
    binaries=Path(settings["binary_dir"])
    backup_binaries=Path(settings.get("backup_binary_dir",settings["binary_dir"]))
    env={**os.environ,"PGPASSWORD":parsed.password}
    connection_args=["--host=127.0.0.1","--port=15432",f"--username={parsed.username}"]
    def pg(tool,*args):
        proc=subprocess.run([str(backup_binaries/(tool+".exe")),*connection_args,*args],env=env,capture_output=True,text=True,timeout=90,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if proc.returncode:
            raise RuntimeError(f"{tool} failed (output suppressed to avoid accidental credentials)")
    def migration_round_trip():
        from sqlalchemy import inspect
        temporary_name=f"ncdai2_migration_{run}"
        pg("createdb",temporary_name)
        temporary_url=parsed.set(database=temporary_name).render_as_string(hide_password=False)
        try:
            os.environ["DATABASE_URL"]=temporary_url
            command.upgrade(config,"head")
            command.check(config)
            command.downgrade(config,"base")
            temporary_engine=make_engine(temporary_url)
            assert set(inspect(temporary_engine).get_table_names()) <= {"alembic_version"}
            temporary_engine.dispose()
            command.upgrade(config,"head")
            command.check(config)
        finally:
            os.environ["DATABASE_URL"]=url
    record("isolated_migration_upgrade_downgrade_reupgrade",migration_round_trip)
    dump=runtime/f"ncdai2-{run}.dump"
    restored_database=f"ncdai2_restore_{run}"
    before=database_fingerprint(engine)
    record("pg_dump_custom_backup",lambda:pg("pg_dump","--format=custom",f"--file={dump}",parsed.database))
    pg("createdb",restored_database)
    record("pg_restore_separate_database",lambda:pg("pg_restore","--exit-on-error",f"--dbname={restored_database}",str(dump)))
    restored_engine=make_engine(parsed.set(database=restored_database).render_as_string(hide_password=False))
    def compare_restore():
        assert database_fingerprint(restored_engine)==before
        with make_sessions(restored_engine)() as db:
            events=list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id==facility_id).order_by(AuditEvent.sequence)))
            assert verify_chain(events)
            names=set(db.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())
            assert {"audit_immutable","reviewed_immutable","referral_transition"}<=names
            assert db.scalar(text("SELECT version_num FROM alembic_version"))==migration
    record("restored_record_hashes_audit_chain_and_triggers",compare_restore)
    restored_engine.dispose(); engine.dispose()
    def restart():
        data_dir=Path(settings["data_dir"]).resolve()
        assert data_dir.is_relative_to(runtime.resolve())
        proc=subprocess.run([str(binaries/"pg_ctl.exe"),"restart","-D",str(data_dir),"-m","fast","-w","-t","30","-l",str(runtime/"postgres-server.log")],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        assert proc.returncode==0, "Dedicated PostgreSQL restart failed"
        assert database_fingerprint(engine)==before
    record("server_restart_persistence",restart)
    engine.dispose()
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"database":"PostgreSQL","server_version":server_version,"migration":migration,"synthetic_only":True,"checks":results,"passed":len(results),"failed":0,"backup_snapshot":before,"limits":["Single local PostgreSQL instance, synthetic records; not production-scale validation.","Backup is a local recovery exercise, not encrypted offsite backup or RPO/RTO certification.","Database superuser can bypass database triggers; production privileges must be restricted."]}
    output=ROOT/"tests/database/postgres-verification.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(f"PostgreSQL {server_version}: {len(results)} checks passed; sanitized report: {output.relative_to(ROOT)}")


if __name__=="__main__":
    verify()
