"""Explicit authorized hospital and separate consultant-database provisioning.

Reads private configuration under .runtime; does not send credentials, overwrite
accounts, relabel patients or enable demo seeding. Run as trusted maintenance.
"""
from pathlib import Path
import json,os,secrets,subprocess,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from dotenv import dotenv_values
from sqlalchemy import create_engine,select,text
from sqlalchemy.engine import make_url
from psycopg import sql
from alembic import command
from alembic.config import Config
from app.models import Facility,User,uid
from app.security import hash_password
from app.audit import append_audit
from app.consultant_migration import migrate_initial
from sqlalchemy.orm import Session


def run():
    config_path=ROOT/'.runtime/mary-help-deployment.json'
    config=json.loads(config_path.read_text(encoding='utf-8'))
    values=dotenv_values(ROOT/'.runtime/vercel-db.env')
    access=json.loads((ROOT/'.runtime/hosted-access.json').read_text(encoding='utf-8'))
    owner=make_url(values['DATABASE_URL_UNPOOLED']).set(drivername='postgresql+psycopg')
    assert owner.host.endswith('.neon.tech') and '-pooler' not in owner.host and owner.database=='neondb'
    assert access['neon_project_id']==values['NEON_PROJECT_ID']
    assert config['facility_name']=='Mary Help Hospital, Thika'
    assert config['owner_confirmed_clinical_and_data_handling'] is True
    config.setdefault('facility_id',uid());config.setdefault('consultant_role_password',secrets.token_urlsafe(36))
    config.setdefault('consultant_database','ncdai_consultant');config.setdefault('consultant_role','ncdai_consult_app')
    for account in config['accounts']:
        account.setdefault('id',uid());account.setdefault('temporary_password',secrets.token_urlsafe(24))
    # Save generated credentials first, so a partial/retried run cannot lose them.
    config_path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    admin=create_engine(owner,isolation_level='AUTOCOMMIT',connect_args={'connect_timeout':10})
    with admin.connect() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',(config['consultant_database'],))
            if cur.fetchone() is None:
                cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(config['consultant_database'])))
    consultant_owner=owner.set(database=config['consultant_database'])
    consultant_engine=create_engine(consultant_owner,connect_args={'connect_timeout':10})
    migrate_initial(consultant_engine)
    with consultant_engine.begin() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(config['consultant_role'],))
            if cur.fetchone() is None:
                cur.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(config['consultant_role']),sql.Literal(config['consultant_role_password'])))
            cur.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(config['consultant_database'])))
            cur.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            cur.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(config['consultant_database']),sql.Identifier(config['consultant_role'])))
            cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(config['consultant_role'])))
            cur.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(config['consultant_role'])))
            cur.execute(sql.SQL('GRANT INSERT ON consultant_cases,consultant_opinions TO {}').format(sql.Identifier(config['consultant_role'])))
    print('Separate consultant database and restricted role provisioned.')
    # Take a retained, consistent logical backup before the primary migration.
    local=json.loads((ROOT/'.runtime/postgres-test.json').read_text(encoding='utf-8'))
    backup=ROOT/'.runtime'/('pre-mary-help-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.dump')
    env={**os.environ,'PGHOST':owner.host,'PGPORT':str(owner.port or 5432),'PGUSER':owner.username,'PGPASSWORD':owner.password,'PGSSLMODE':'require','PGCONNECT_TIMEOUT':'10'}
    proc=subprocess.run([str(Path(local['backup_binary_dir'])/'pg_dump.exe'),'--format=custom','--file='+str(backup),owner.database],env=env,capture_output=True,timeout=180)
    if proc.returncode:
        raise RuntimeError('Pre-migration backup failed; raw diagnostics withheld')
    os.environ['DATABASE_URL']=owner.render_as_string(hide_password=False)
    migration=Config(str(ROOT/'backend/alembic.ini'));migration.set_main_option('script_location',str(ROOT/'backend/migrations'))
    command.upgrade(migration,'head');command.check(migration)
    primary_engine=create_engine(owner,connect_args={'connect_timeout':10})
    with Session(primary_engine,expire_on_commit=False) as db:
        facility=db.get(Facility,config['facility_id'])
        if facility is None:
            facility=Facility(id=config['facility_id'],name=config['facility_name'],record_mode='clinical_testing');db.add(facility);db.flush()
        assert facility.name==config['facility_name'] and facility.record_mode=='clinical_testing'
        for account in config['accounts']:
            existing=db.scalar(select(User).where(User.email==account['email']))
            if existing:
                assert existing.id==account['id'] and existing.facility_id==facility.id and existing.role==account['role']
                continue
            user=User(id=account['id'],facility_id=facility.id,email=account['email'],display_name=account['name'],role=account['role'],password_hash=hash_password(account['temporary_password']),password_change_required=True)
            db.add(user);db.flush();append_audit(db,user,'user.provision_hospital','user',user.id)
        db.commit()
    with primary_engine.begin() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            cur.execute(sql.SQL('GRANT SELECT,INSERT ON consultation_requests,consultation_dispositions TO {}').format(sql.Identifier(access['role'])))
            # PostgreSQL row locks require UPDATE privilege on at least one column.
            # The immutable trigger still rejects every actual UPDATE, including ID.
            cur.execute(sql.SQL('GRANT UPDATE(id) ON consultation_requests TO {}').format(sql.Identifier(access['role'])))
    pooled=make_url(access['database_url']).set(database=config['consultant_database'],username=config['consultant_role'],password=config['consultant_role_password'])
    config['consultant_database_url']=pooled.render_as_string(hide_password=False)
    config['provisioned_at']=datetime.now(timezone.utc).isoformat()
    config_path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    lines=['Mary Help Hospital, Thika — NCDAI 2.0 testing access','Testing date: 14 September 2026','Main application: https://ncdai-2.vercel.app','Consultant workspace: https://ncdai-2.vercel.app/consultant','Each user MUST change their temporary password before record access. Share each credential only with its named recipient using your institution-approved channel. No email has been sent.','']
    for account in config['accounts']:
        lines += [account['name']+' ('+account['role']+')','Email: '+account['email'],'Temporary password: '+account['temporary_password'],'']
    (ROOT/'.runtime/mary-help-access.txt').write_text('\n'.join(lines),encoding='utf-8')
    for engine in [primary_engine,consultant_engine,admin]:engine.dispose()
    print('Mary Help facility and three named accounts provisioned. Private credentials saved; no patient records created and no messages sent.')

if __name__=='__main__':
    try:run()
    except Exception as error:
        print('Hospital provisioning stopped:',type(error).__name__,'(details withheld to protect credentials)')
        sys.exit(1)
