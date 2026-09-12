"""Read-only recovery rehearsal of the owner's synthetic hosted database.

Restores only to a fresh loopback PostgreSQL database. Never use with real patient
records. Source credentials and the dump stay private; reports contain counts and
hashes only. This is not an automated backup service or a cloud failover drill.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import dotenv_values
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.audit import verify_chain
from app.models import AuditEvent, Facility
from app.db import SCHEMA_REVISION

TABLES = ('facilities', 'users', 'auth_sessions', 'login_attempts', 'patients', 'encounters', 'referrals', 'audit_events')


def fingerprints(connection):
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    result = {}
    for table in TABLES:
        rows = connection.execute(text(f'SELECT row_to_json(t)::text FROM (SELECT * FROM {table} ORDER BY id) t')).scalars().all()
        result[table] = dict(count=len(rows), sha256=hashlib.sha256('\n'.join(rows).encode()).hexdigest())
    return result


def run():
    runtime = ROOT / '.runtime'
    config = json.loads((runtime / 'postgres-test.json').read_text(encoding='utf-8'))
    access = json.loads((runtime / 'hosted-access.json').read_text(encoding='utf-8'))
    owner_values = dotenv_values(runtime / 'vercel-db.env')
    source = make_url(owner_values['DATABASE_URL_UNPOOLED']).set(drivername='postgresql+psycopg')
    assert access['url'] == 'https://ncdai-2.vercel.app'
    assert access['neon_project_id'] == owner_values['NEON_PROJECT_ID']
    assert source.host.endswith('.neon.tech') and '-pooler' not in source.host and source.database == 'neondb'
    assert source.query.get('sslmode') == 'require'
    local = make_url(config['NCDAI_CASE_DATABASE_URL'])
    assert local.host == '127.0.0.1' and local.port == 15432 and local.database == 'ncdai2_test'
    target = local.set(database='ncdai2_hosted_restore_' + uuid4().hex[:12])
    binaries = Path(config['backup_binary_dir'])
    dump = runtime / (target.database + '.dump')
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), status='failed',
                  kind='Hosted synthetic snapshot restored to isolated local PostgreSQL',
                  real_patient_data=False, source_mutations=False, checks=[],
                  limitations=['No cloud failover, automated backup retention, offsite encryption or production RPO/RTO certification.',
                               'Owner and ACL are deliberately not restored; production application grants need separate verification.',
                               'Restored database remains local and is not served over the network.'])
    started = time.perf_counter()

    def pg(tool, url, *args):
        env = {**os.environ, 'PGHOST': url.host, 'PGPORT': str(url.port or 5432),
               'PGUSER': url.username, 'PGPASSWORD': url.password or '',
               'PGSSLMODE': url.query.get('sslmode', 'disable'), 'PGCONNECT_TIMEOUT': '10',
               'PGOPTIONS': '-c timezone=UTC'}
        proc = subprocess.run([str(binaries / (tool + '.exe')), *args], env=env,
                              capture_output=True, timeout=180,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode:
            raise RuntimeError(tool + ' failed; private diagnostics suppressed')

    source_engine = create_engine(source, connect_args={'connect_timeout': 10})
    target_engine = None
    try:
        with source_engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            assert conn.connection.driver_connection.pgconn.ssl_in_use
            assert conn.scalar(text('SELECT count(*) FROM patients WHERE synthetic IS NOT TRUE')) == 0
            assert conn.scalar(text('SELECT version_num FROM alembic_version')) == SCHEMA_REVISION
            report['server_version'] = conn.scalar(text('SHOW server_version'))
            report['migration'] = SCHEMA_REVISION
            snapshot = conn.scalar(text('SELECT pg_export_snapshot()'))
            report['snapshot_at'] = datetime.now(timezone.utc).isoformat()
            before = fingerprints(conn)
            pg('pg_dump', source, '--format=custom', '--no-owner', '--no-acl',
               '--snapshot=' + snapshot, '--file=' + str(dump), source.database)
        report['checks'].append('read_only_consistent_hosted_snapshot_over_tls')
        pg('createdb', local, target.database)
        pg('pg_restore', target, '--exit-on-error', '--no-owner', '--no-acl', '--dbname=' + target.database, str(dump))
        target_engine = create_engine(target)
        with target_engine.connect() as conn:
            assert fingerprints(conn) == before
            assert conn.scalar(text('SELECT version_num FROM alembic_version')) == SCHEMA_REVISION
            names = set(conn.execute(text('SELECT tgname FROM pg_trigger WHERE NOT tgisinternal')).scalars())
            assert {'audit_immutable', 'reviewed_immutable', 'referral_transition'} <= names
        report['checks'].append('all_table_counts_and_hashes_match_snapshot')
        with Session(target_engine) as db:
            facilities = list(db.scalars(select(Facility.id)))
            for facility in facilities:
                assert verify_chain(list(db.scalars(select(AuditEvent).where(AuditEvent.facility_id == facility).order_by(AuditEvent.sequence))))
        report['checks'].append('all_facility_audit_chains_and_required_triggers_present')
        # Invalidate copied sessions before any isolated sign-in verification.
        with target_engine.begin() as conn:
            conn.execute(text('DELETE FROM auth_sessions'))
        report['checks'].append('restored_sessions_revoked')
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.config import Settings
        app = create_app(Settings(environment='test', database_url=target.render_as_string(hide_password=False)))
        try:
            with TestClient(app) as client:
                assert client.get('/api/health/ready').status_code == 200
                response = client.post('/api/auth/login', json={'email': access['email'], 'password': access['password']})
                assert response.status_code == 200
                client.headers['X-CSRF-Token'] = response.json()['csrf_token']
                assert client.get('/api/patients').status_code == 200
                assert client.post('/api/auth/logout').status_code in {200, 204}
        finally:
            app.state.engine.dispose()
        report['checks'].append('restored_application_ready_sign_in_read_and_logout')
        report['tables'] = before
        report['facility_chains_verified'] = len(facilities)
        report['status'] = 'passed'
    finally:
        report['elapsed_seconds'] = round(time.perf_counter() - started, 3)
        source_engine.dispose()
        if target_engine is not None:
            target_engine.dispose()
        (ROOT / 'docs/test-results/hosted-recovery-rehearsal.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status', 'checks', 'elapsed_seconds')}))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('Hosted recovery rehearsal failed: ' + type(error).__name__ + '; no secret diagnostics emitted.')
        sys.exit(1)
