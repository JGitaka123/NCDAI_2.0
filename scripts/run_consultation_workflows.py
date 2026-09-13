"""Create fresh loopback PostgreSQL databases for two-store workflow verification."""
from pathlib import Path
import json,os,sys,time,secrets
from uuid import uuid4
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
from app.models import Facility,User
from app.security import hash_password
from app.consultant_migration import migrate_initial
from test_consultations import test_fifty_full_consultation_scenarios, exercise_postgres_consultation_races
from conftest import PASSWORD,login


def run():
    raw=os.getenv('NCDAI_CI_DATABASE_URL') or json.loads((ROOT/'.runtime/postgres-test.json').read_text(encoding='utf-8'))['NCDAI_CASE_DATABASE_URL']
    source=make_url(raw)
    assert source.host in {'localhost','127.0.0.1'} and source.database in {'ncdai2_test','ncdai_ci_checks'}
    token=uuid4().hex[:10]
    primary=source.set(database='ncdai_consult_main_'+token)
    consultant=source.set(database='ncdai_consult_review_'+token)
    admin=create_engine(source,isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        for url in [primary,consultant]:
            with conn.connection.driver_connection.cursor() as cur:
                cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(url.database)))
    admin.dispose()
    os.environ['DATABASE_URL']=primary.render_as_string(hide_password=False)
    config=Config(str(ROOT/'backend/alembic.ini'));config.set_main_option('script_location',str(ROOT/'backend/migrations'))
    command.upgrade(config,'head');command.check(config)
    app=create_app(Settings(environment='test',database_url=primary.render_as_string(hide_password=False),consultant_database_url=consultant.render_as_string(hide_password=False)))
    migrate_initial(app.state.consultant_engine)
    hashed=hash_password(PASSWORD)
    with app.state.session_factory() as db:
        db.add(Facility(id='facility-a',name='Fictional dual database evaluation'));db.flush()
        for email,role in [('clinician@example.test','clinician'),('supervisor@example.test','supervisor')]:
            db.add(User(id=email,facility_id='facility-a',email=email,display_name=role,role=role,password_hash=hashed))
        db.commit()
    # Exercise the web workflow with the same restricted privileges as hosting.
    # Owner-only tests would miss PostgreSQL's column UPDATE requirement for row locks.
    main_role='consult_main_'+token; review_role='consult_review_'+token
    main_password=secrets.token_urlsafe(32); review_password=secrets.token_urlsafe(32)
    admin=create_engine(source,isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            for role,password in [(main_role,main_password),(review_role,review_password)]:
                cur.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
    admin.dispose()
    for engine,role,is_main in [(app.state.engine,main_role,True),(app.state.consultant_engine,review_role,False)]:
        with engine.begin() as conn:
            with conn.connection.driver_connection.cursor() as cur:
                cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
                cur.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(role)))
                if is_main:
                    cur.execute(sql.SQL('GRANT INSERT ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(role)))
                    cur.execute(sql.SQL('GRANT UPDATE ON facilities,users,auth_sessions,login_attempts,patients,encounters,referrals TO {}').format(sql.Identifier(role)))
                    cur.execute(sql.SQL('GRANT DELETE ON auth_sessions,login_attempts TO {}').format(sql.Identifier(role)))
                    cur.execute(sql.SQL('GRANT UPDATE(id) ON consultation_requests TO {}').format(sql.Identifier(role)))
                else:
                    cur.execute(sql.SQL('GRANT INSERT ON consultant_cases,consultant_opinions TO {}').format(sql.Identifier(role)))
    app.state.engine.dispose();app.state.consultant_engine.dispose()
    app=create_app(Settings(environment='test',
        database_url=primary.set(username=main_role,password=main_password).render_as_string(hide_password=False),
        consultant_database_url=consultant.set(username=review_role,password=review_password).render_as_string(hide_password=False)))
    started=time.perf_counter()
    with TestClient(app) as client:
        login(client)
        test_fifty_full_consultation_scenarios(client,app)
    exercise_postgres_consultation_races(app)
    report={'restricted_runtime_roles':True,'concurrency_checks':2,'cases':50,'passed':50,'failed':0,'database':'Two isolated PostgreSQL databases','seconds':round(time.perf_counter()-started,2),
            'scope':'Fictional workflow verification; not independent clinical adjudication',
            'checks':['request and immutable snapshot','idempotent delivery','independent opinion','primary disposition','unchanged original assessment','FHIR traceability','aggregate evaluation','facility audit']}
    path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'docs/test-results/mary-help-consultant-postgres.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':
    run()
