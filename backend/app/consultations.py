"""Durable consultant handoff, isolated storage and traceable clinical disposition."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import statistics
from typing import Annotated
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from .models import ConsultationRequest, ConsultationDisposition, Encounter, Patient, User, AuthSession, uid, utcnow
from .security import token_hash
from .consultant_models import ConsultantCase, ConsultantOpinion, CONSULTANT_SCHEMA
from .consultation_schemas import ConsultationCreate, OpinionCreate, DispositionCreate
from .db import make_engine, make_sessions
from .interop import iso


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


def install_consultation_routes(api, *, settings, get_db, clinical_user, privileged, scoped, commit_change, authenticated):
    DB = Annotated[object, Depends(get_db)]
    CLINICAL = Annotated[User, Depends(clinical_user)]
    PRIVILEGED = Annotated[User, Depends(privileged)]
    engine = make_engine(settings.consultant_database_url) if settings.consultant_database_url else None
    factory = make_sessions(engine) if engine is not None else None
    api.state.consultant_engine = engine

    def configured():
        if factory is None:
            raise HTTPException(503, 'Consultant service is not configured; use the hospital escalation process')
        return factory

    def remote_ready(remote):
        if remote.scalar(text('SELECT version FROM consultant_schema')) != CONSULTANT_SCHEMA:
            raise HTTPException(503, 'Consultant database migration requires attention')

    def refresh_actor(db, request, user):
        # Serialize account/session revocation against consultant writes. Recheck
        # authorization after any row-lock wait, before touching the remote store.
        db.scalar(select(User).where(User.id==user.id).with_for_update())
        raw=request.cookies.get(settings.cookie_name,'')
        db.scalar(select(AuthSession).where(AuthSession.id==token_hash(raw)).with_for_update())
        db.expire_all()
        return clinical_user(authenticated(request,db))

    def locked_request(db, request_id, user, request):
        obj = db.scalar(select(ConsultationRequest).where(ConsultationRequest.id == request_id,
                         ConsultationRequest.facility_id == user.facility_id).with_for_update())
        if obj is None:
            raise HTTPException(404, 'Consultation not found')
        refresh_actor(db,request,user)
        return obj

    def verify_case(row, case):
        if (case.facility_id != row.facility_id or case.snapshot_hash != row.snapshot_hash or
                digest(case.snapshot) != row.snapshot_hash or digest(row.snapshot) != row.snapshot_hash):
            raise HTTPException(409, 'Consultation snapshot integrity mismatch; contact the incident lead')

    def ensure_delivered(row):
        with configured()() as remote:
            remote_ready(remote)
            existing = remote.get(ConsultantCase,row.id)
            if existing is None:
                if digest(row.snapshot) != row.snapshot_hash:
                    raise HTTPException(409,'Original snapshot integrity mismatch')
                remote.add(ConsultantCase(id=row.id,facility_id=row.facility_id,snapshot_hash=row.snapshot_hash,snapshot=deepcopy(row.snapshot)))
                remote.commit()
            else:
                verify_case(row,existing)

    def load_states(rows):
        """Fetch an entire queue page in one remote transaction, not N round trips."""
        if not rows:
            return {}
        with configured()() as remote:
            remote_ready(remote)
            ids=[r.id for r in rows]
            cases={c.id:c for c in remote.scalars(select(ConsultantCase).where(ConsultantCase.id.in_(ids)))}
            opinions={o.case_id:o for o in remote.scalars(select(ConsultantOpinion).where(ConsultantOpinion.case_id.in_(ids)))}
            output={}
            for row in rows:
                case=cases.get(row.id); opinion=opinions.get(row.id)
                if case is None:
                    output[row.id]=(False,None)
                    continue
                verify_case(row,case)
                if opinion is None:
                    output[row.id]=(True,None)
                    continue
                if (digest(opinion.opinion) != opinion.opinion_hash or opinion.opinion.get('snapshot_hash') != row.snapshot_hash or
                        opinion.opinion.get('case_id') != row.id or opinion.opinion.get('reviewer_id') != opinion.reviewer_id):
                    raise HTTPException(409,'Consultant opinion integrity mismatch')
                output[row.id]=(True,{**deepcopy(opinion.opinion),'opinion_hash':opinion.opinion_hash})
            return output

    def load_opinion(row):
        return load_states([row])[row.id]

    def page_states(rows):
        try:
            return load_states(rows)
        except (SQLAlchemyError, HTTPException) as error:
            if isinstance(error,HTTPException) and error.status_code != 503:
                raise
            return None

    def result(db,row, *, with_snapshot=True, states=False):
        available=True
        try:
            if states is None:
                raise HTTPException(503,'Consultant service unavailable')
            delivered,opinion=load_opinion(row) if states is False else states[row.id]
        except (SQLAlchemyError, HTTPException) as error:
            if isinstance(error,HTTPException) and error.status_code != 503:
                raise
            available,delivered,opinion=False,False,None
        current=db.get(Encounter,row.encounter_id)
        disposition=db.get(ConsultationDisposition,row.id)
        stale=(current.version != row.snapshot['encounter_version'] or
               (current.assessment or {}).get('id') != row.snapshot['assessment_id'])
        obj={'id':row.id,'encounter_id':row.encounter_id,'patient_id':row.patient_id,
             'requested_by':row.requested_by,'created_at':iso(row.created_at),
             'snapshot_hash':row.snapshot_hash,'snapshot_stale':stale,'current_encounter_version':current.version,
             'service_available':available,'delivered':delivered,
             'status':'closed' if disposition else 'answered' if opinion else 'awaiting_consultant' if delivered else 'pending_delivery',
             'opinion':opinion,'disposition':None,
             'urgency':row.snapshot['assessment']['urgency'],'question':row.snapshot['question'],
             'synthetic':row.snapshot['synthetic']}
        if with_snapshot:
            obj['snapshot']=row.snapshot
            patient=db.get(Patient,row.patient_id)
            obj['patient_identity']={'record_id':patient.external_id,'name':patient.given_name+' '+patient.family_name}
        if disposition:
            if digest({k:v for k,v in disposition.opinion_snapshot.items() if k != 'opinion_hash'}) != disposition.opinion_hash:
                raise HTTPException(409, 'Acknowledged consultant response integrity mismatch')
            if obj['opinion'] is None:
                obj['opinion'] = disposition.opinion_snapshot
            obj['disposition']={k:getattr(disposition,k) for k in ('actor_id','opinion_hash','action','action_taken','current_encounter_version','snapshot_was_stale')}
            obj['disposition']['created_at']=iso(disposition.created_at)
        return obj

    @api.get('/api/health/consultant')
    def consultant_health():
        try:
            with configured()() as remote:
                remote_ready(remote)
            return {'status':'ready','schema':CONSULTANT_SCHEMA}
        except SQLAlchemyError:
            raise HTTPException(503,'Consultant database unavailable') from None

    @api.post('/api/encounters/{encounter_id}/consultations',status_code=201)
    def request_consultation(encounter_id:str,payload:ConsultationCreate,request:Request,db:DB,user:CLINICAL):
        configured()
        encounter=db.scalar(select(Encounter).where(Encounter.id==encounter_id,Encounter.facility_id==user.facility_id).with_for_update())
        if encounter is None:
            raise HTTPException(404,'Encounter not found')
        user=refresh_actor(db,request,user)
        payload_hash=digest({'encounter_id':encounter_id,**payload.model_dump(mode='json')})
        existing=db.scalar(select(ConsultationRequest).where(ConsultationRequest.requested_by==user.id,
                           ConsultationRequest.idempotency_key==str(payload.idempotency_key)))
        if existing:
            if existing.payload_hash != payload_hash:
                raise HTTPException(409,'This submission key belongs to a different request')
            return result(db,existing)
        if encounter.version != payload.expected_version or not encounter.assessment or encounter.assessment['id'] != payload.assessment_id:
            raise HTTPException(409,'The assessment changed; reload before requesting review')
        known={r['id'] for r in encounter.assessment['recommendations']}
        selected=payload.recommendation_ids
        if len(set(selected)) != len(selected) or not set(selected) <= known:
            raise HTTPException(422,'Select distinct recommendations from this assessment')
        patient=db.get(Patient,encounter.patient_id)
        today=date.today(); dob=patient.date_of_birth
        age=today.year-dob.year-((today.month,today.day)<(dob.month,dob.day))
        request_id=uid()
        snapshot={'schema':'ncdai-consult-snapshot-1','request_id':request_id,'facility_id':user.facility_id,
                  'encounter_id':encounter.id,'encounter_version':encounter.version,'assessment_id':encounter.assessment['id'],
                  'requested_by':user.id,'synthetic':patient.synthetic,'age':age,'sex':patient.sex,
                  'data':deepcopy(encounter.data),'assessment':deepcopy(encounter.assessment),
                  'primary_review':deepcopy(encounter.review),'recommendation_ids':selected,
                  'reason_category':payload.reason_category,'question':payload.question,'immediate_action':payload.immediate_action,
                  'requested_at':iso(utcnow())}
        row=ConsultationRequest(id=request_id,facility_id=user.facility_id,encounter_id=encounter.id,patient_id=patient.id,
                requested_by=user.id,idempotency_key=str(payload.idempotency_key),payload_hash=payload_hash,
                snapshot=snapshot,snapshot_hash=digest(snapshot))
        db.add(row)
        commit_change(db,user,'consultation.request','consultation',row.id)
        # The committed request is the outbox. A separate POST delivers it; remote
        # failure cannot undo or obscure successful local submission.
        return result(db,row)

    @api.post('/api/consultations/{request_id}/sync')
    def sync_consultation(request_id:str,request:Request,db:DB,user:CLINICAL):
        row=locked_request(db,request_id,user,request)
        try:
            ensure_delivered(row)
        except SQLAlchemyError:
            raise HTTPException(503,'Request is saved; consultant delivery is unavailable. Retry delivery and use hospital escalation if urgent.') from None
        return result(db,row)

    @api.get('/api/consultations')
    def consultations(db:DB,user:CLINICAL,encounter_id:str|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
        query=select(ConsultationRequest).where(ConsultationRequest.facility_id==user.facility_id)
        if encounter_id:
            scoped(db,Encounter,encounter_id,user)
            query=query.where(ConsultationRequest.encounter_id==encounter_id)
        rows=list(db.scalars(query.order_by(ConsultationRequest.created_at.desc()).offset(offset).limit(limit)))
        states=page_states(rows)
        return [result(db,row,with_snapshot=False,states=states) for row in rows]

    @api.get('/api/consultations/{request_id}')
    def consultation(request_id:str,db:DB,user:CLINICAL):
        row=scoped(db,ConsultationRequest,request_id,user)
        commit_change(db,user,'consultation.view','consultation',row.id)
        return result(db,row)

    @api.post('/api/consultations/{request_id}/opinion')
    def submit_opinion(request_id:str,payload:OpinionCreate,request:Request,db:DB,user:CLINICAL):
        if user.role != 'supervisor':
            raise HTTPException(403,'Consultant/supervisor role required')
        row=locked_request(db,request_id,user,request)
        if user.role != 'supervisor':
            raise HTTPException(403,'Consultant/supervisor role required')
        if row.requested_by==user.id:
            raise HTTPException(409,'An independent consultant must answer this request')
        if payload.snapshot_hash != row.snapshot_hash:
            raise HTTPException(409,'Review the preserved snapshot before submitting')
        if db.get(ConsultationDisposition,row.id):
            raise HTTPException(409,'The consultation is closed')
        try:
            ensure_delivered(row)
            with configured()() as remote:
                remote_ready(remote)
                existing=remote.get(ConsultantOpinion,row.id)
                if existing:
                    comparable={k:existing.opinion.get(k) for k in payload.model_dump()}
                    if existing.reviewer_id==user.id and comparable==payload.model_dump():
                        remote.close()
                        return result(db,row)
                    raise HTTPException(409,'An opinion is already recorded; create a new consultation for further review')
                opinion={**payload.model_dump(),'case_id':row.id,'reviewer_id':user.id,
                         'reviewer_name':user.display_name,'reviewed_at':iso(utcnow())}
                remote.add(ConsultantOpinion(case_id=row.id,reviewer_id=user.id,opinion=opinion,opinion_hash=digest(opinion)))
                remote.commit()
        except SQLAlchemyError:
            raise HTTPException(503,'Consultant response could not be confirmed. Reload before retrying; identical submissions are safe.') from None
        return result(db,row)

    @api.post('/api/consultations/{request_id}/disposition')
    def record_disposition(request_id:str,payload:DispositionCreate,request:Request,db:DB,user:CLINICAL):
        row=locked_request(db,request_id,user,request)
        _,opinion=load_opinion(row)
        if opinion is None or opinion['opinion_hash']!=payload.opinion_hash:
            raise HTTPException(409,'Reload the consultant opinion before recording the final action')
        if opinion['reviewer_id']==user.id:
            raise HTTPException(409,'The primary care team must independently record the action taken')
        existing=db.get(ConsultationDisposition,row.id)
        if existing:
            if existing.actor_id==user.id and existing.opinion_hash==payload.opinion_hash and existing.action==payload.action and existing.action_taken==payload.action_taken:
                return result(db,row)
            raise HTTPException(409,'A final action is already recorded; start a new consultation for follow-up')
        encounter=db.scalar(select(Encounter).where(Encounter.id==row.encounter_id).with_for_update())
        if encounter.version != payload.expected_encounter_version:
            raise HTTPException(409,'The encounter changed; reload before recording action')
        stale=encounter.version!=row.snapshot['encounter_version'] or (encounter.assessment or {}).get('id')!=row.snapshot['assessment_id']
        if stale and not payload.stale_snapshot_acknowledged:
            raise HTTPException(409,'Confirm that you reviewed subsequent encounter changes; the consultant answered an earlier snapshot')
        db.add(ConsultationDisposition(request_id=row.id,facility_id=user.facility_id,actor_id=user.id,opinion_hash=payload.opinion_hash,opinion_snapshot=deepcopy(opinion),
               action=payload.action,action_taken=payload.action_taken,current_encounter_version=encounter.version,snapshot_was_stale=stale))
        commit_change(db,user,'consultation.disposition','consultation',row.id)
        return result(db,row)

    @api.get('/api/consultation-evaluation')
    def evaluation(db:DB,user:PRIVILEGED,synthetic:bool=True):
        rows=list(db.scalars(select(ConsultationRequest).where(ConsultationRequest.facility_id==user.facility_id)))
        rows=[r for r in rows if r.snapshot['synthetic'] is synthetic]
        agreement={key:0 for key in ('agree','partly_agree','disagree','insufficient_information')}
        actions={key:0 for key in ('accepted','modified','not_followed')}
        pending=answered=closed=unavailable=0; response_minutes=[]
        states=page_states(rows)
        for row in rows:
            item=result(db,row,with_snapshot=False,states=states)
            if not item['service_available']:
                unavailable+=1
            elif item['opinion']:
                answered+=1; agreement[item['opinion']['agreement']]+=1
                a=datetime.fromisoformat(row.snapshot['requested_at']); b=datetime.fromisoformat(item['opinion']['reviewed_at'])
                response_minutes.append(max(0,(b-a).total_seconds()/60))
            else:
                pending+=1
            if item['disposition']:
                closed+=1;actions[item['disposition']['action']]+=1
        return {'synthetic':synthetic,'requests':len(rows),'answered':answered,'pending':pending,'closed':closed,
                'service_unavailable_records':unavailable,'agreement':agreement,'actions':actions,
                'median_response_minutes':statistics.median(response_minutes) if response_minutes else None,
                'definition':'Consultation episode counts, not unique patients or diagnostic accuracy. Unavailable opinions are not classified as unanswered.'}
