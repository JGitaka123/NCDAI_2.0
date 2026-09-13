from uuid import uuid4
from datetime import date
import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings
from app.main import create_app
from app.models import Facility, User, Patient
from app.ai import build_briefing, AISettings
from app.clinical import assess
from app.security import hash_password
from conftest import PASSWORD, login
from test_consultations import consult_app


@pytest.fixture
def hospital(tmp_path,test_password_hash):
    facility_id=str(uuid4())
    app=create_app(Settings(environment='test',database_url=f"sqlite:///{tmp_path/'mary.db'}",synthetic_only=False,clinical_facility_id=facility_id,auto_create_schema=True))
    with app.state.session_factory() as db:
        db.add_all([Facility(id=facility_id,name='Fictional hospital test',record_mode='clinical_testing'),Facility(id='demo',name='Fictional demo')]);db.flush()
        db.add_all([User(id='lead',facility_id=facility_id,email='clinician@example.test',display_name='Test lead',role='supervisor',password_hash=test_password_hash),
                    User(id='demo-user',facility_id='demo',email='other@example.test',display_name='Demo',role='clinician',password_hash=test_password_hash)])
        db.commit()
    yield app
    app.state.engine.dispose()


def patient_payload(synthetic):
    return {'external_id':str(uuid4()),'given_name':'Fictional','family_name':'Engineering test','date_of_birth':'1970-01-01','sex':'female','synthetic':synthetic}


def test_real_record_mode_is_explicit_and_facility_scoped(hospital):
    with TestClient(hospital) as client:
        login(client)
        assert client.get('/api/auth/session').json()['user']['clinical_testing'] is True
        created=client.post('/api/patients',json=patient_payload(False))
        assert created.status_code==201 and created.json()['synthetic'] is False
        fhir=client.get(f"/api/fhir/Patient/{created.json()['id']}").json()
        assert fhir['meta']['tag'][0]['code']=='clinical-testing'
        login(client,'other@example.test')
        assert client.get('/api/auth/session').json()['user']['clinical_testing'] is False
        assert client.post('/api/patients',json=patient_payload(False)).status_code==422
        assert client.get(f"/api/patients/{created.json()['id']}").status_code==404
        assert client.post('/api/patients',json=patient_payload(True)).status_code==201


@pytest.mark.parametrize('marker',[None,1,'false','true'])
def test_record_classification_cannot_be_coerced(hospital,marker):
    with TestClient(hospital) as client:
        login(client)
        assert client.post('/api/patients',json=patient_payload(marker)).status_code==422


def test_first_login_password_change_is_enforced_by_server(hospital):
    with hospital.state.session_factory() as db:
        db.get(User,'lead').password_change_required=True;db.commit()
    with TestClient(hospital) as client:
        login(client)
        assert client.get('/api/auth/session').json()['user']['password_change_required'] is True
        assert client.get('/api/patients').status_code==403
        assert client.post('/api/patients',json=patient_payload(False)).status_code==403
        changed=client.post('/api/auth/change-password',json={'current_password':PASSWORD,'new_password':'New-temporary-test-credential-981!'})
        assert changed.status_code==200
        assert client.get('/api/auth/session').json()['user']['password_change_required'] is False
        assert client.get('/api/patients').status_code==200


def test_real_ai_requires_explicit_opt_in_and_never_changes_rule_output():
    import httpx
    record=assess({'systolic_bp':120,'diastolic_bp':80},52,'female')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'model':'deepseek-v4-pro','choices':[{'finish_reason':'stop','message':{'content':'{"focus_rule_ids":["DATA_COMPLETENESS"],"checklist_ids":[]}'}}]})
    config=AISettings('deepseek','deepseek-v4-pro','fake-key')
    blocked=asyncio.run(build_briefing(record,synthetic=False,settings=config,transport=httpx.MockTransport(handler)))
    assert blocked['status']=='blocked' and calls==[]
    allowed=asyncio.run(build_briefing(record,synthetic=False,allow_real_patient=True,settings=config,transport=httpx.MockTransport(handler)))
    assert len(calls)==1
    body=calls[0].content.decode()
    assert 'Fictional' not in body and 'systolic_bp' not in body and '120' not in body
    assert allowed['status']=='ready'


def test_same_physical_database_with_different_credentials_is_rejected():
    with pytest.raises(ValueError,match='separate database'):
        Settings(database_url='postgresql+psycopg://one:secret@host.neon.tech/neondb',consultant_database_url='postgresql+psycopg://two:other@host-pooler.neon.tech/neondb').validate()



def test_database_guard_blocks_real_records_in_demo_and_classification_changes(consult_app):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from conftest import patient
    with TestClient(consult_app) as client:
        login(client)
        created=client.post('/api/patients',json=patient_payload(True)).json()
    with consult_app.state.engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text('UPDATE patients SET synthetic=false WHERE id=:id'),{'id':created['id']})
        conn.rollback()
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO patients (id,facility_id,external_id,given_name,family_name,date_of_birth,sex,synthetic,created_at) VALUES ('invalid-real','facility-a','invalid-real','Fictional','Test','1970-01-01','female',false,CURRENT_TIMESTAMP)"))
        conn.rollback()
