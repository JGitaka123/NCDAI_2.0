"""Read-only hosted consultant snapshot restored to a fresh loopback database.

Refuses any non-fictional consultation. Dumps and credentials remain private.
This exercises logical recovery, not managed cloud retention or regional failover.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.consultant_models import CONSULTANT_SCHEMA
from app.consultations import digest

def fingerprints(conn):
    conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    return {table: {'count':len(rows), 'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
            for table, key in [('consultant_schema','version'), ('consultant_cases','id'), ('consultant_opinions','case_id')]
            for rows in [conn.execute(text(f'SELECT row_to_json(t)::text FROM (SELECT * FROM {table} ORDER BY {key}) t')).scalars().all()]}

def run():
    runtime = ROOT / '.runtime'
    local_config = json.loads((runtime / 'postgres-test.json').read_text(encoding='utf-8'))
    deployment = json.loads((runtime / 'mary-help-deployment.json').read_text(encoding='utf-8'))
    owner = dotenv_values(runtime / 'vercel-db.env')
    source = make_url(owner['DATABASE_URL_UNPOOLED']).set(drivername='postgresql+psycopg', database=deployment['consultant_database'])
    assert source.database == 'ncdai_consultant' and source.host.endswith('.neon.tech') and '-pooler' not in source.host
    assert source.query.get('sslmode') == 'require'
    local = make_url(local_config['NCDAI_CASE_DATABASE_URL'])
    assert local.host == '127.0.0.1' and local.port == 15432 and local.database == 'ncdai2_test'
    target = local.set(database='ncdai2_consult_restore_' + uuid4().hex[:12])
    dump = runtime / (target.database + '.dump')
    binaries = Path(local_config['backup_binary_dir'])
    def pg(tool, url, *args):
        env = {**os.environ, 'PGHOST':url.host, 'PGPORT':str(url.port or 5432), 'PGUSER':url.username,
               'PGPASSWORD':url.password or '', 'PGSSLMODE':url.query.get('sslmode','disable'), 'PGCONNECT_TIMEOUT':'10', 'PGOPTIONS':'-c timezone=UTC'}
        proc = subprocess.run([str(binaries / (tool+'.exe')), *args], env=env, capture_output=True, timeout=180,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode:
            raise RuntimeError(tool+' failed; private diagnostics suppressed')
    report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'status':'failed', 'real_patient_data':False,
              'source_mutations':False, 'checks':[], 'limitations':['Logical snapshot recovery only; no certified RPO/RTO or cloud failover.', 'Primary and consultant snapshots are taken separately; reconcile requests/opinions by stable ID and hash.', 'No new automatic backup retention or notification delivery is claimed.']}
    started = time.perf_counter()
    src = create_engine(source)
    dst = None
    try:
        with src.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            assert conn.connection.driver_connection.pgconn.ssl_in_use
            assert conn.scalar(text("SELECT count(*) FROM consultant_cases WHERE snapshot->>'synthetic' IS DISTINCT FROM 'true'")) == 0
            assert conn.scalar(text('SELECT version FROM consultant_schema')) == CONSULTANT_SCHEMA
            before = fingerprints(conn)
            assert before['consultant_cases']['count'] > 0 and before['consultant_opinions']['count'] > 0
            snapshot = conn.scalar(text('SELECT pg_export_snapshot()'))
            pg('pg_dump', source, '--format=custom', '--no-owner', '--no-acl', '--snapshot='+snapshot, '--file='+str(dump), source.database)
        report['checks'].append('consistent_read_only_fictional_consultant_snapshot_over_TLS')
        pg('createdb', local, target.database)
        pg('pg_restore', target, '--exit-on-error', '--no-owner', '--no-acl', '--dbname='+target.database, str(dump))
        dst = create_engine(target)
        with dst.connect() as conn:
            assert fingerprints(conn) == before
            triggers = set(conn.execute(text('SELECT tgname FROM pg_trigger WHERE NOT tgisinternal')).scalars())
            assert {'consultant_cases_immutable','consultant_opinions_immutable'} <= triggers
            for row in conn.execute(text('SELECT snapshot, snapshot_hash FROM consultant_cases')):
                assert digest(row.snapshot) == row.snapshot_hash
            for row in conn.execute(text('SELECT opinion, opinion_hash FROM consultant_opinions')):
                assert digest(row.opinion) == row.opinion_hash
            assert conn.scalar(text('SELECT count(*) FROM consultant_opinions o LEFT JOIN consultant_cases c ON o.case_id=c.id WHERE c.id IS NULL')) == 0
        report['checks'] += ['three_table_counts_and_SHA256_match', 'immutable_history_triggers_restored', 'all_case_and_opinion_hashes_valid; no_orphan_opinions']
        report['tables'] = before
        report['status'] = 'passed'
    finally:
        src.dispose()
        if dst is not None:
            dst.dispose()
        report['elapsed_seconds'] = round(time.perf_counter()-started,3)
        (ROOT / 'docs/test-results/consultant-recovery-rehearsal.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','checks','elapsed_seconds')}))

if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('Consultant recovery failed: '+type(error).__name__+'; private diagnostics suppressed.')
        raise SystemExit(1)
