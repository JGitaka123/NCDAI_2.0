"""Independent role, integrity and recovery challenges for two-database consultations."""
from datetime import date
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from alembic import command
from alembic.config import Config
from app.config import Settings
from app.main import create_app
from app.models import User, Facility, ConsultationRequest, ConsultationDisposition, Patient, AuthSession
from app.consultant_models import ConsultantOpinion, ConsultantCase
from app.consultant_migration import migrate_initial
from app.security import hash_password
from conftest import login, encounter, assess, review_payload, PASSWORD


@pytest.fixture
def consult_app(tmp_path, monkeypatch, test_password_hash):
    primary=f"sqlite:///{(tmp_path/'primary.db').as_posix()}"
    monkeypatch.setenv('DATABASE_URL',primary)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    config.set_main_option('script_location',str(Path(__file__).resolve().parents[1]/'migrations'))
    command.upgrade(config,'head')
    app=create_app(Settings(environment='test',database_url=primary,consultant_database_url=f"sqlite:///{(tmp_path/'consultant.db').as_posix()}"))
    migrate_initial(app.state.consultant_engine)
    with app.state.session_factory() as db:
        for fid in ['facility-a','facility-b']:
            db.add(Facility(id=fid,name=fid))
        db.flush()
        for email,role,facility in [('clinician@example.test','clinician','facility-a'),('supervisor@example.test','supervisor','facility-a'),('admin@example.test','admin','facility-a'),('other@example.test','supervisor','facility-b')]:
            db.add(User(id=email,facility_id=facility,email=email,display_name=role,role=role,password_hash=test_password_hash))
        db.commit()
    yield app
    app.state.engine.dispose(); app.state.consultant_engine.dispose()


@pytest.fixture
def cc(consult_app):
    with TestClient(consult_app) as client:
        login(client)
        yield client


def request_payload(record,**change):
    result=dict(idempotency_key=str(uuid4()),expected_version=record['version'],assessment_id=record['assessment']['id'],
                recommendation_ids=[record['assessment']['recommendations'][0]['id']],reason_category='disagreement',
                question='Please independently review this fictional recommendation.',immediate_action='The primary team is assessing and arranging indicated escalation.')
    result.update(change);return result


def make_request(cc):
    record=assess(cc,encounter(cc))
    payload=request_payload(record)
    response=cc.post(f"/api/encounters/{record['id']}/consultations",json=payload)
    assert response.status_code==201,response.text
    return record,payload,response.json()


def opinion_payload(row,agreement='disagree'):
    return dict(snapshot_hash=row['snapshot_hash'],agreement=agreement,assessment='Independent fictional assessment.',
                recommended_action='Arrange the documented clinical review today.',rationale='Documented disagreement with the proposed action.',
                urgency='urgent',source_references='Synthetic adjudication fixture; no real clinical advice.')


def test_durable_outbox_replay_and_independent_opinion(cc,consult_app):
    record,payload,row=make_request(cc)
    assert row['status']=='pending_delivery'
    duplicate=cc.post(f"/api/encounters/{record['id']}/consultations",json=payload)
    assert duplicate.json()['id']==row['id']
    assert cc.post(f"/api/encounters/{record['id']}/consultations",json={**payload,'question':'Different question under the same key.'}).status_code==409
    assert cc.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row)).status_code==403
    for _ in range(2):
        delivered=cc.post(f"/api/consultations/{row['id']}/sync")
        assert delivered.status_code==200 and delivered.json()['delivered']
    login(cc,'other@example.test')
    for suffix in ['', '/sync']:
        result=cc.get(f"/api/consultations/{row['id']}") if not suffix else cc.post(f"/api/consultations/{row['id']}{suffix}")
        assert result.status_code==404
    login(cc,'supervisor@example.test')
    answered=cc.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row))
    assert answered.status_code==200,answered.text
    assert answered.json()['opinion']['reviewer_id']=='supervisor@example.test'
    repeated=cc.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row))
    assert repeated.json()['opinion']['opinion_hash']==answered.json()['opinion']['opinion_hash']
    changed=cc.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row,'agree'))
    assert changed.status_code==409
    with consult_app.state.consultant_engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM consultant_cases'))==1
        assert conn.scalar(text('SELECT count(*) FROM consultant_opinions'))==1


def test_opinion_self_review_and_admin_clinical_access_are_blocked(cc):
    login(cc,'supervisor@example.test')
    _,_,row=make_request(cc)
    assert cc.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row)).status_code==409
    login(cc,'admin@example.test')
    assert cc.get('/api/consultations').status_code==403
    assert cc.get(f"/api/consultations/{row['id']}").status_code==403
    assert cc.get('/api/consultation-evaluation').status_code==200


def test_stale_snapshot_requires_explicit_reconciliation_and_preserves_final_action(cc,consult_app):
    record,_,row=make_request(cc)
    changed=cc.patch(f"/api/encounters/{record['id']}",json={'expected_version':record['version'],'data':{'systolic_bp':180,'diastolic_bp':100}})
    assert changed.status_code==200
    login(cc,'supervisor@example.test')
    response=cc.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row)).json()
    final=dict(opinion_hash=response['opinion']['opinion_hash'],expected_encounter_version=changed.json()['version'],action='modified',action_taken='Primary clinician reassessed the updated findings and arranged referral.')
    assert cc.post(f"/api/consultations/{row['id']}/disposition",json=final).status_code==409
    login(cc)
    assert cc.post(f"/api/consultations/{row['id']}/disposition",json=final).status_code==409
    final['stale_snapshot_acknowledged']=True
    result=cc.post(f"/api/consultations/{row['id']}/disposition",json=final)
    assert result.status_code==200,result.text
    assert result.json()['disposition']['snapshot_was_stale']
    assert cc.post(f"/api/consultations/{row['id']}/disposition",json=final).status_code==200
    assert cc.post(f"/api/consultations/{row['id']}/disposition",json={**final,'action':'accepted'}).status_code==409
    assert cc.get(f"/api/encounters/{record['id']}").json()['data']['systolic_bp']==180
    for engine,table in [(consult_app.state.engine,'consultation_requests'),(consult_app.state.engine,'consultation_dispositions'),(consult_app.state.consultant_engine,'consultant_cases'),(consult_app.state.consultant_engine,'consultant_opinions')]:
        for action in ['DELETE','UPDATE']:
            with engine.connect() as conn:
                with pytest.raises(IntegrityError):
                    conn.execute(text(f'DELETE FROM {table}' if action=='DELETE' else f"UPDATE {table} SET {'request_id' if table=='consultation_dispositions' else 'case_id' if table=='consultant_opinions' else 'id'} = 'tamper'"))
                conn.rollback()


def test_remote_outage_preserves_question_then_delivery_recovers(cc,consult_app):
    from sqlalchemy import event
    def fail(*_):
        from sqlalchemy.exc import OperationalError
        raise OperationalError('redacted',{},Exception('offline'))
    event.listen(consult_app.state.consultant_engine,'before_cursor_execute',fail)
    try:
        _,_,row=make_request(cc)
        assert row['service_available'] is False
        assert cc.post(f"/api/consultations/{row['id']}/sync").status_code==503
        assert cc.get(f"/api/consultations/{row['id']}").json()['snapshot']['question']==row['snapshot']['question']
    finally:
        event.remove(consult_app.state.consultant_engine,'before_cursor_execute',fail)
    result=cc.post(f"/api/consultations/{row['id']}/sync")
    assert result.json()['delivered'] is True


@pytest.mark.parametrize('change',[
    {'assessment_id':'stale'}, {'expected_version':999}, {'recommendation_ids':['invented']},
    {'recommendation_ids':[]}, {'question':'short'}, {'immediate_action':'no'},
])
def test_invalid_or_stale_requests_cannot_enter_queue(cc,change):
    record=assess(cc,encounter(cc))
    response=cc.post(f"/api/encounters/{record['id']}/consultations",json=request_payload(record,**change))
    assert response.status_code in {409,422}
    assert cc.get('/api/consultations').json()==[]


def test_fifty_full_consultation_scenarios(cc,consult_app):
    # Cross urgency, disagreement, opinion and action categories; assertions are
    # workflow invariants, not an independently adjudicated clinical gold standard.
    with TestClient(consult_app) as reviewer:
        login(reviewer,'supervisor@example.test')
        for n in range(50):
            patient=cc.post('/api/patients',json={'external_id':f'CONSULT-{n}','given_name':'Fictional','family_name':'Consultation','date_of_birth':'1970-01-01','sex':'male','synthetic':True}).json()
            data=[{'systolic_bp':150,'diastolic_bp':95},{'symptoms':['chest_pain']},{'glucose':3.0},{'potassium':5.7,'acute_kidney_injury':'yes'},{'known_cancer':'yes'}][n%5]
            record=cc.post('/api/encounters',json={'patient_id':patient['id'],'data':data}).json()
            record=assess(cc,record)
            frozen=record['assessment']
            row=cc.post(f"/api/encounters/{record['id']}/consultations",json=request_payload(record,reason_category=['disagreement','uncertainty','dose_question','outside_scope','other'][n%5])).json()
            delivered=cc.post(f"/api/consultations/{row['id']}/sync")
            assert delivered.status_code==200
            result=reviewer.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row,['agree','partly_agree','disagree','insufficient_information'][n%4]))
            assert result.status_code==200,result.text
            opinion=result.json()['opinion']
            closed=cc.post(f"/api/consultations/{row['id']}/disposition",json={'opinion_hash':opinion['opinion_hash'],'expected_encounter_version':record['version'],'action':['accepted','modified','not_followed'][n%3],'action_taken':'Fictional primary team action with documented rationale.'})
            assert closed.status_code==200,closed.text
            assert closed.json()['status']=='closed'
            assert cc.get(f"/api/encounters/{record['id']}").json()['assessment']==frozen
            reviewed=cc.post(f"/api/encounters/{record['id']}/review",json=review_payload(record))
            assert reviewed.status_code==200
            exported=cc.get(f"/api/fhir/Bundle/{record['id']}")
            assert exported.status_code==200
            import base64,json
            consult_doc=next(e['resource'] for e in exported.json()['entry'] if e['resource']['id']==row['id']+'-consult')
            traced=json.loads(base64.b64decode(consult_doc['content'][0]['attachment']['data']))
            assert traced['opinion_hash']==opinion['opinion_hash']
            assert traced['consultant_opinion']['reviewer_id']=='supervisor@example.test'
            assert traced['snapshot']['assessment']==frozen
        report=reviewer.get('/api/consultation-evaluation?synthetic=true').json()
        assert report['requests']==50 and report['answered']==50 and report['closed']==50
        assert sum(report['agreement'].values())==50 and sum(report['actions'].values())==50
        assert reviewer.get('/api/consultation-evaluation?synthetic=false').json()['requests']==0
        assert reviewer.get('/api/audit/verify').json()['valid']



def exercise_postgres_consultation_races(app):
    from concurrent.futures import ThreadPoolExecutor
    with app.state.session_factory() as db:
        lead=db.get(User,'supervisor@example.test')
        db.add(User(id='second@example.test',facility_id=lead.facility_id,email='second@example.test',display_name='Second test consultant',role='supervisor',password_hash=lead.password_hash))
        db.commit()
    with TestClient(app) as client:
        login(client)
        record=assess(client,encounter(client))
        payload=request_payload(record)
    def submit_request(_):
        with TestClient(app) as c:
            login(c)
            response=c.post(f"/api/encounters/{record['id']}/consultations",json=payload)
            assert response.status_code==201
            return response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests=list(pool.map(submit_request,range(2)))
    assert requests[0]['id']==requests[1]['id']
    row=requests[0]
    def submit_opinion(email):
        with TestClient(app) as c:
            login(c,email)
            return c.post(f"/api/consultations/{row['id']}/opinion",json=opinion_payload(row)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(submit_opinion,['supervisor@example.test','second@example.test']))
    assert sorted(statuses)==[200,409]
    with app.state.consultant_engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM consultant_opinions WHERE case_id=:id'),{'id':row['id']})==1
