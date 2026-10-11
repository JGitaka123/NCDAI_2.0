from datetime import timedelta
from uuid import uuid4
import json
import pytest
from sqlalchemy import select, text
from fastapi.testclient import TestClient
from app.models import StudyEvent, StudyRecord
from app.study_schemas import today
from conftest import encounter, assess, login, patient, review_payload


def submit(client, record, payload, **extra):
    return client.post('/api/study/records',json={'idempotency_key':str(uuid4()),'patient_id':record.get('patient_id'),'encounter_id':record.get('id'),'synthetic':True,'payload':payload,**extra})


def enrol(client, record, days=35, **extra):
    return submit(client,record,{'kind':'enrolment','index_date':str(today()-timedelta(days=days)),'status':'enrolled','participation_documented':True},**extra)


def query():
    return f'?start={today()-timedelta(days=60)}&end={today()}&synthetic=true'


def test_prospective_events_and_manual_corrections(client,app):
    record=encounter(client)
    record=assess(client,record)
    first_assessment=record['assessment']['id']
    record=assess(client,record)
    assert client.post(f"/api/encounters/{record['id']}/review",json=review_payload(record)).status_code==200
    first=enrol(client,record)
    assert first.status_code==201,first.text
    body={'idempotency_key':str(uuid4()),'previous_id':first.json()['id'],'patient_id':record['patient_id'],'encounter_id':record['id'],'synthetic':True,'payload':{**first.json()['payload'],'status':'withdrawn'}}
    correction=client.post('/api/study/records',json=body)
    assert correction.status_code==201,correction.text
    assert correction.json()['revision']==2
    assert client.post('/api/study/records',json=body).json()['id']==correction.json()['id']
    body['payload']['status']='enrolled'
    assert client.post('/api/study/records',json=body).status_code==409
    body['idempotency_key']=str(uuid4())
    assert client.post('/api/study/records',json=body).status_code==409
    with app.state.session_factory() as db:
        rows=list(db.scalars(select(StudyEvent).where(StudyEvent.encounter_id==record['id'])))
        assert len(rows)==4
        assert first_assessment in [r.payload['assessment_id'] for r in rows]
        assert len(list(db.scalars(select(StudyRecord))))==2
        encoded=json.dumps([r.payload for r in rows])
        assert 'Synthetic' not in encoded and 'Patient' not in encoded
        assert all(r.payload['rules_version'] for r in rows if r.action=='encounter.assess')


@pytest.mark.parametrize('payload',[
    {'kind':'daily_tally','clinic_date':str(today()),'eligible_visits':10,'app_used_visits':9},
    {'kind':'daily_tally','clinic_date':str(today()+timedelta(days=1)),'eligible_visits':0,'app_used_visits':0},
    {'kind':'daily_tally','clinic_date':str(today()),'eligible_visits':True,'app_used_visits':1},
    {'kind':'visit','consultation_minutes':12,'timing_method':'not_recorded'},
    {'kind':'visit','consultation_minutes':None,'timing_method':'observed'},
    {'kind':'visit','helpfulness':6},
    {'kind':'followup','contact_date':str(today()),'status':'completed','systolic_bp':120},
    {'kind':'followup','contact_date':str(today()),'status':'missed','hba1c':7},
    {'kind':'followup','contact_date':str(today()),'status':'completed','systolic_bp':90,'diastolic_bp':100},
    {'kind':'enrolment','index_date':str(today()),'status':'enrolled','participation_documented':False},
])
def test_invalid_observations(client,payload):
    assert submit(client,{},payload).status_code==422


def test_scope_role_and_classification(client,app):
    record=encounter(client)
    assert enrol(client,record,synthetic=False).status_code==403
    with TestClient(app) as other:
        login(other,'other@example.test')
        assert enrol(other,record).status_code==404
        assert other.get(f"/api/study/patients/{record['patient_id']}/records").status_code==404
    login(client,'admin@example.test')
    assert enrol(client,record).status_code==403
    assert client.get('/api/study/export'+query()).status_code==403
    assert client.get('/api/study/summary'+query()).status_code==200
    assert submit(client,{}, {'kind':'daily_tally','clinic_date':str(today()),'eligible_visits':10,'app_used_visits':8,'non_use_workload':2}).status_code==201


def test_report_denominators_followup_and_export(client):
    first=encounter(client)
    assert enrol(client,first).status_code==201
    # Repeated encounters do not inflate patient or enrolment denominators.
    assert client.post('/api/encounters',json={'patient_id':first['patient_id'],'data':{}}).status_code==201
    second_patient=patient(client,'SYN-SECOND')
    second=client.post('/api/encounters',json={'patient_id':second_patient['id'],'data':{}}).json()
    assert enrol(client,second,days=10).status_code==201
    contact={'kind':'followup','contact_date':str(today()),'status':'completed','systolic_bp':130,'diastolic_bp':85}
    saved=submit(client,first,contact)
    assert saved.status_code==201,saved.text
    assert submit(client,first,{**contact,'systolic_bp':125},previous_id=saved.json()['id']).status_code==201
    assert submit(client,first,{'kind':'visit','consultation_minutes':12,'timing_method':'observed','safety_screening':'no_event_reported'}).status_code==201
    assert submit(client,{}, {'kind':'daily_tally','clinic_date':str(today()),'eligible_visits':10,'app_used_visits':8,'non_use_workload':2}).status_code==201
    login(client,'supervisor@example.test')
    response=client.get('/api/study/summary'+query())
    assert response.status_code==200,response.text
    result=response.json()
    assert result['patients_seen']==2 and result['encounters']==3
    assert result['enrolled_patients']==2
    assert result['adoption']=={'numerator':8,'denominator':10,'percent':80.0}
    assert result['followup_completion']=={'numerator':1,'denominator':1,'percent':100.0}
    assert result['paired_systolic_change_mmHg']=={'n':1,'mean':-25.0}
    assert result['consultation_minutes']['observed']=={'n':1,'median':12.0}
    export=client.get('/api/study/export'+query()).json()
    raw=json.dumps(export)
    assert first['patient_id'] not in raw and 'Synthetic' not in raw and 'SYN-SECOND' not in raw
    assert len({row['patient_code'] for row in export['rows']})==2
    assert export['content_sha256']==client.get('/api/study/export'+query()).json()['content_sha256']


def test_empty_denominator_and_synthetic_separation(client):
    login(client,'supervisor@example.test')
    result=client.get('/api/study/summary'+query()).json()
    assert result['adoption']['percent'] is None
    assert result['followup_completion']['percent'] is None
    assert result['paired_systolic_change_mmHg']['mean'] is None
    assert client.get('/api/study/summary'+query().replace('true','false')).json()['encounters']==0
    assert client.get('/api/study/summary'+query().replace(str(today()),str(today()+timedelta(days=1)))).status_code==422


def test_followup_requires_active_enrolment_and_valid_date(client):
    record=encounter(client)
    contact={'kind':'followup','contact_date':str(today()),'status':'completed'}
    assert submit(client,record,contact).status_code==422
    saved=enrol(client,record,days=1).json()
    assert submit(client,record,{**contact,'contact_date':str(today()-timedelta(days=2))}).status_code==422
    assert submit(client,record,{**saved['payload'],'status':'withdrawn'},previous_id=saved['id']).status_code==201
    assert submit(client,record,contact).status_code==422


def test_tampered_evidence_is_not_reported(client,app):
    # create_all test DB intentionally has no migration triggers; verify read guard too.
    record=encounter(client)
    saved=enrol(client,record).json()
    with app.state.session_factory() as db:
        db.execute(text("UPDATE study_records SET payload_hash = 'tampered' WHERE id=:id"),{'id':saved['id']})
        db.commit()
    login(client,'supervisor@example.test')
    assert client.get('/api/study/summary'+query()).status_code==409


def test_fifty_study_workflows(client,app):
    for i in range(50):
        pat=patient(client,f'SYN-STUDY-{i}')
        rec=client.post('/api/encounters',json={'patient_id':pat['id'],'data':{'systolic_bp':150,'diastolic_bp':95,'known_hypertension':'yes'}}).json()
        rec=assess(client,rec)
        assert client.post(f"/api/encounters/{rec['id']}/review",json=review_payload(rec)).status_code==200
        enrolment=enrol(client,rec,days=35 if i<30 else 10)
        assert enrolment.status_code==201,enrolment.text
        body={'kind':'visit','consultation_minutes':10+i%5,'timing_method':'observed' if i%2 else 'estimated',
              'safety_screening':'event_reported' if i%10==0 else 'no_event_reported'}
        assert submit(client,rec,body).status_code==201
        if i<30 and i%3 and i%10:
            assert submit(client,rec,{'kind':'followup','contact_date':str(today()),'status':'completed','systolic_bp':135,'diastolic_bp':85}).status_code==201
        if i%10==0:
            assert submit(client,rec,{'kind':'safety','incident_id':str(uuid4()),'occurred_on':str(today()),'severity':'near_miss','category':'delay',
                                     'description':'Fictional delay for regression verification','immediate_action':'Fictional immediate clinical escalation'}).status_code==201
        if i<30 and i%10==0:
            saved=enrolment.json()
            assert submit(client,rec,{**saved['payload'],'status':'withdrawn'},previous_id=saved['id']).status_code==201
    login(client,'supervisor@example.test')
    result=client.get('/api/study/summary'+query()).json()
    assert result['patients_seen']==50 and result['encounters']==50
    assert result['enrolled_patients']==47
    assert result['followup_completion']['denominator']==27
    assert result['followup_completion']['numerator']==18
    assert result['safety_reports']==5
    assert result['visit_observation_coverage']['numerator']==50
    assert result['activity_events']['encounter.assess']==50
    assert client.get('/api/audit/verify').json()['valid'] is True
