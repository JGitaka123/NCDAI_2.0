"""Fifty fictional study workflows on fresh, restricted-role PostgreSQL."""
from pathlib import Path
import json, os, secrets, sys, time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from psycopg import sql
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.models import Facility,User,uid
from app.security import hash_password
from conftest import PASSWORD,login
from test_study import test_fifty_study_workflows, submit
from app.study_schemas import today


def run():
    source=make_url(os.getenv('NCDAI_CI_DATABASE_URL') or json.loads((ROOT/'.runtime/postgres-test.json').read_text())['NCDAI_CASE_DATABASE_URL'])
    assert source.host in {'localhost','127.0.0.1'} and source.database in {'ncdai2_test','ncdai_ci_checks'}
    token=uuid4().hex[:10]; target=source.set(database='ncdai_study_'+token)
    role='study_runtime_'+token; password=secrets.token_urlsafe(32)
    admin=create_engine(source,isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target.database)))
            cur.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
    admin.dispose()
    os.environ['DATABASE_URL']=target.render_as_string(hide_password=False)
    config=Config(str(ROOT/'backend/alembic.ini'));config.set_main_option('script_location',str(ROOT/'backend/migrations'))
    command.upgrade(config,'head');command.check(config)
    app=create_app(Settings(environment='test',database_url=target.render_as_string(hide_password=False)))
    hashed=hash_password(PASSWORD)
    with app.state.session_factory() as db:
        facility=Facility(id=uid(),name='Fictional study verification');db.add(facility);db.flush()
        for email,kind in [('clinician@example.test','clinician'),('supervisor@example.test','supervisor')]:
            db.add(User(id=uid(),facility_id=facility.id,email=email,display_name=kind,role=kind,password_hash=hashed))
        db.commit()
    with app.state.engine.begin() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            for statement in ['GRANT USAGE ON SCHEMA public TO {}','GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {}',
                              'GRANT UPDATE ON facilities,users,auth_sessions,login_attempts,patients,encounters,referrals TO {}',
                              'GRANT DELETE ON auth_sessions,login_attempts TO {}']:
                cur.execute(sql.SQL(statement).format(sql.Identifier(role)))
    app.state.engine.dispose()
    app=create_app(Settings(environment='test',database_url=target.set(username=role,password=password).render_as_string(hide_password=False)))
    started=time.perf_counter()
    with TestClient(app) as client:
        login(client);test_fifty_study_workflows(client,app)
    def competing_tally(email):
        with TestClient(app) as client:
            login(client,email)
            return submit(client,{}, {'kind':'daily_tally','clinic_date':str(today()),'eligible_visits':50,'app_used_visits':50}).status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(competing_tally,['clinician@example.test','supervisor@example.test']))
    assert sorted(results)==[201,409],results
    for table in ('study_events','study_records'):
        for action in ('UPDATE','DELETE'):
            with app.state.engine.connect() as conn:
                try:
                    conn.execute(text(f"UPDATE {table} SET payload_hash='tamper'" if action=='UPDATE' else f'DELETE FROM {table}'))
                except Exception:
                    conn.rollback()
                else: raise AssertionError('Runtime role must not modify retained study evidence')
    owner=create_engine(target)
    for table in ('study_events','study_records'):
        with owner.connect() as conn:
            try: conn.execute(text(f"UPDATE {table} SET payload_hash='tamper'"))
            except Exception: conn.rollback()
            else: raise AssertionError('Migration trigger must reject evidence rewrite')
    owner.dispose();app.state.engine.dispose()
    report={'cases':50,'passed':50,'failed':0,'restricted_runtime_role':True,'immutable_checks':6,'concurrent_revision_checks':1,
            'database':'Fresh isolated PostgreSQL','seconds':round(time.perf_counter()-started,2),
            'scope':'Fictional engineering verification, not clinical validation',
            'checks':['clinical encounter and review','enrolment baseline','visit observation','due and late follow-up denominators','withdrawals','safety reports','audit chain','restricted role and immutable triggers']}
    out=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'docs/test-results/study-postgres.json'
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__': run()
