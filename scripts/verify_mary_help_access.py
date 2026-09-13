"""Verify provisioned hospital accounts without changing their initial passwords."""
import json
from pathlib import Path
from datetime import datetime, timezone
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]

def run():
    config = json.loads((ROOT / '.runtime/mary-help-deployment.json').read_text(encoding='utf-8'))
    demo = json.loads((ROOT / '.runtime/hosted-access.json').read_text(encoding='utf-8'))
    origin = 'https://ncdai-2.vercel.app'
    checks = []
    for account in config['accounts']:
        with httpx.Client(base_url=origin, headers={'Origin': origin}, timeout=30, trust_env=False) as client:
            response = client.post('/api/auth/login', json={'email': account['email'], 'password': account['temporary_password']})
            assert response.status_code == 200
            auth = response.json()
            user = auth['user']
            assert user['facility_id'] == config['facility_id'] and user['role'] == account['role']
            assert user['clinical_testing'] and user['consultant_enabled'] and user['password_change_required']
            client.headers['X-CSRF-Token'] = auth['csrf_token']
            assert client.get('/api/patients').status_code == 403
            assert client.post('/api/auth/logout').status_code in {200, 204}
            assert client.get('/api/auth/session').status_code == 401
    checks.append('three_named_accounts_correct_facility_role_and_mandatory_password_change; sessions_revoked')
    engine = create_engine(make_url(config['consultant_database_url']).set(drivername='postgresql+psycopg'))
    with engine.connect() as conn:
        assert conn.connection.driver_connection.pgconn.ssl_in_use
        assert conn.scalar(text('SELECT version FROM consultant_schema')) == 'consultant-20260913-1'
        assert not conn.scalar(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')"))
        for table in ('consultant_cases', 'consultant_opinions'):
            for privilege in ('SELECT', 'INSERT'):
                assert conn.scalar(text('SELECT has_table_privilege(current_user, :t, :p)'), {'t':table, 'p':privilege})
            for privilege in ('UPDATE', 'DELETE', 'TRUNCATE'):
                assert not conn.scalar(text('SELECT has_table_privilege(current_user, :t, :p)'), {'t':table, 'p':privilege})
        assert not conn.scalar(text("SELECT has_database_privilege('ncdai_app', current_database(), 'CONNECT')"))
    engine.dispose()
    checks.append('consultant_database_TLS_version_and_least_privilege; primary_role_cannot_connect')
    engine = create_engine(make_url(demo['database_url']).set(drivername='postgresql+psycopg'))
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT record_mode FROM facilities WHERE id=:f'), {'f':config['facility_id']}) == 'clinical_testing'
        assert conn.scalar(text('SELECT count(*) FROM patients WHERE facility_id=:f'), {'f':config['facility_id']}) == 0
    engine.dispose()
    checks.append('Mary_Help_configured_for_clinical_testing; no_patient_records_created_during_provisioning')
    with httpx.Client(base_url=origin, headers={'Origin': origin}, timeout=30, trust_env=False) as client:
        response = client.post('/api/auth/login', json={'email':demo['email'], 'password':demo['password']})
        assert response.status_code == 200
        auth = response.json()
        assert not auth['user']['clinical_testing']
        client.headers['X-CSRF-Token'] = auth['csrf_token']
        assert client.post('/api/patients', json={'external_id':'REJECT-REAL-TEST', 'given_name':'Fictional', 'family_name':'Boundary', 'date_of_birth':'1970-01-01', 'sex':'male', 'synthetic':False}).status_code == 422
        assert client.post('/api/auth/logout').status_code in {200,204}
    checks.append('synthetic_facility_still_rejects_real_record_classification')
    report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'status':'passed', 'checks':checks,
              'passwords_changed':False, 'messages_sent':False, 'real_patient_data_created':False}
    (ROOT / 'docs/test-results/mary-help-access-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('Access verification failed: '+type(error).__name__+'; private diagnostics suppressed.')
        raise SystemExit(1)
