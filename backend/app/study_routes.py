"""Facility-scoped, append-only evidence capture and descriptive reporting."""
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import hmac
import statistics
from typing import Annotated
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from .models import StudyRecord, StudyEvent, Facility, Patient, Encounter, User, AuthSession, uid, utcnow
from .security import token_hash
from .study_schemas import StudyRecordCreate, today
from .study_capture import METRICS_VERSION
from .consultations import digest
from .interop import iso

ZONE = ZoneInfo('Africa/Nairobi')
LIMIT = 20000


def bounded(db, query):
    rows = list(db.scalars(query.limit(LIMIT + 1)))
    if len(rows) > LIMIT:
        raise HTTPException(422, 'Report exceeds the protected extraction limit; arrange a governed database extract')
    return rows


def latest(rows):
    result = {}
    for row in rows:
        if digest(row.payload) != row.payload_hash:
            raise HTTPException(409, 'Study evidence integrity mismatch; contact the incident lead')
        if row.record_key not in result or row.revision > result[row.record_key].revision:
            result[row.record_key] = row
    return list(result.values())


def rate(n, d):
    return {'numerator': n, 'denominator': d, 'percent': round(100*n/d, 1) if d else None}


def view(row):
    return {'id': row.id, 'patient_id': row.patient_id, 'encounter_id': row.encounter_id,
            'revision': row.revision, 'previous_id': row.previous_id, 'synthetic': row.synthetic,
            'created_at': iso(row.created_at), 'payload': {k:v for k,v in row.payload.items() if not k.startswith('_')}}


def install_study_routes(api, *, settings, get_db, authenticated, clinical_user, privileged, scoped, commit_change):
    DB = Annotated[object, Depends(get_db)]
    AUTH = Annotated[User, Depends(authenticated)]
    CLINICAL = Annotated[User, Depends(clinical_user)]
    PRIVILEGED = Annotated[User, Depends(privileged)]

    def real_mode(db, user, synthetic):
        if not synthetic and (settings.synthetic_only or user.facility_id != settings.clinical_facility_id or
                              db.get(Facility, user.facility_id).record_mode != 'clinical_testing'):
            raise HTTPException(403, 'Real study records require the enabled clinical facility')

    @api.post('/api/study/records', status_code=201)
    def save(payload: StudyRecordCreate, request: Request, db: DB, user: AUTH):
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        db.scalar(select(AuthSession).where(AuthSession.id == token_hash(request.cookies.get(settings.cookie_name,''))).with_for_update())
        db.expire_all()
        user = authenticated(request, db)
        # Reuse the audit advisory lock, avoiding facility row/FK lock inversion.
        # SQLite uses the existing request-level writer lock in get_db.
        if db.bind.dialect.name == 'postgresql':
            lock_key = int.from_bytes(hashlib.sha256(user.facility_id.encode()).digest()[:8], 'big', signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':lock_key})
        data = payload.payload.model_dump(mode='json')
        kind = data['kind']
        if kind != 'daily_tally': clinical_user(user)
        real_mode(db, user, payload.synthetic)
        submission_hash = digest(payload.model_dump(mode='json'))
        prior = db.scalar(select(StudyRecord).where(StudyRecord.actor_id == user.id, StudyRecord.idempotency_key == str(payload.idempotency_key)))
        if prior:
            if prior.payload.get('_submission_hash') != submission_hash:
                raise HTTPException(409, 'This submission identifier was already used for different data')
            return view(prior)
        pid = str(payload.patient_id) if payload.patient_id else None
        eid = str(payload.encounter_id) if payload.encounter_id else None
        if kind == 'daily_tally':
            if pid or eid: raise HTTPException(422, 'Daily clinic totals must not reference a patient')
            key = f'daily_tally:{payload.synthetic}:{data["clinic_date"]}'
        else:
            if not pid or not eid: raise HTTPException(422, 'Select a saved patient encounter')
            patient = scoped(db, Patient, pid, user)
            encounter = scoped(db, Encounter, eid, user)
            if encounter.patient_id != pid: raise HTTPException(422, 'Encounter does not belong to this patient')
            if patient.synthetic != payload.synthetic: raise HTTPException(422, 'Record classification must match the patient')
            key = {'enrolment':f'enrolment:{pid}', 'visit':f'visit:{eid}',
                   'followup':f'followup:{pid}:{data.get("contact_date")}',
                   'safety':f'safety:{data.get("incident_id")}'}.get(kind)
            if kind == 'enrolment':
                index_date = date.fromisoformat(data['index_date'])
                age = index_date.year-patient.date_of_birth.year-((index_date.month,index_date.day)<(patient.date_of_birth.month,patient.date_of_birth.day))
                if age < 18 and data['status'] == 'enrolled': raise HTTPException(422, 'This feasibility cohort is for adults')
                data['_baseline'] = {k:encounter.data.get(k) for k in ('systolic_bp','diastolic_bp','hba1c','egfr')}
                data['_age_band'] = 'under_18' if age<18 else '18_39' if age<40 else '40_59' if age<60 else '60_plus'
                data['_sex'] = patient.sex
                data['_conditions'] = {k:encounter.data.get(k,'unknown') for k in ('known_hypertension','known_diabetes','known_asthma','known_copd','known_ckd','known_cancer')}
            if kind == 'followup':
                enrol = db.scalar(select(StudyRecord).where(StudyRecord.facility_id == user.facility_id,
                         StudyRecord.record_key == f'enrolment:{pid}').order_by(StudyRecord.revision.desc()).limit(1))
                if not enrol or enrol.payload['status'] != 'enrolled':
                    raise HTTPException(422, 'An active documented enrolment is required for study follow-up')
                if data['contact_date'] < enrol.payload['index_date']: raise HTTPException(422, 'Follow-up cannot precede enrolment')
        previous = db.scalar(select(StudyRecord).where(StudyRecord.facility_id == user.facility_id, StudyRecord.record_key == key).order_by(StudyRecord.revision.desc()).limit(1))
        if (str(payload.previous_id) if payload.previous_id else None) != (previous.id if previous else None):
            raise HTTPException(409, 'A newer observation exists. Reload saved study records before making a correction')
        if previous and (previous.patient_id != pid or previous.synthetic != payload.synthetic):
            raise HTTPException(409, 'An observation cannot be reassigned to another patient or record class')
        # Enrolment corrections retain the original clinical baseline, not a later visit.
        if previous and kind == 'enrolment':
            if data['index_date'] != previous.payload['index_date'] or eid != previous.encounter_id:
                raise HTTPException(422, 'The index date and encounter are fixed after enrolment; contact the study lead for an adjudicated correction')
            for k in ('_baseline','_age_band','_sex','_conditions'): data[k] = previous.payload[k]
        data['_submission_hash'] = submission_hash
        row = StudyRecord(id=uid(), facility_id=user.facility_id, patient_id=pid, encounter_id=eid, actor_id=user.id,
                          kind=kind, record_key=key, revision=previous.revision+1 if previous else 1,
                          previous_id=previous.id if previous else None, idempotency_key=str(payload.idempotency_key),
                          synthetic=payload.synthetic, payload=data, payload_hash=digest(data))
        db.add(row)
        commit_change(db,user,'study.record','study_record',row.id)
        return view(row)

    @api.get('/api/study/patients/{patient_id}/records')
    def patient_records(patient_id: str, db: DB, user: CLINICAL):
        scoped(db,Patient,patient_id,user)
        rows = latest(bounded(db,select(StudyRecord).where(StudyRecord.facility_id==user.facility_id,StudyRecord.patient_id==patient_id)))
        output = [view(r) for r in rows]
        commit_change(db,user,'study.view','patient',patient_id)
        return output

    def window(start, end):
        if end > today() or start > end or (end-start).days > 120:
            raise HTTPException(422,'Choose a past or current window of at most 121 days')
        return (datetime.combine(start,time.min,ZONE).astimezone(timezone.utc),
                datetime.combine(end+timedelta(days=1),time.min,ZONE).astimezone(timezone.utc))

    @api.get('/api/study/tallies')
    def tallies(start: date, end: date, synthetic: bool, db: DB, user: AUTH):
        window(start,end)
        rows = latest(bounded(db,select(StudyRecord).where(StudyRecord.facility_id==user.facility_id,StudyRecord.synthetic==synthetic,StudyRecord.kind=='daily_tally')))
        output = [view(r) for r in rows if start.isoformat()<=r.payload['clinic_date']<=end.isoformat()]
        commit_change(db,user,'study.tallies_view','facility',user.facility_id)
        return output

    def report(db,user,start,end,synthetic,export=False):
        lo,hi = window(start,end)
        asof = min(hi,utcnow())
        observations = latest(bounded(db,select(StudyRecord).where(StudyRecord.facility_id==user.facility_id,StudyRecord.synthetic==synthetic,StudyRecord.created_at<asof)))
        events = bounded(db,select(StudyEvent).where(StudyEvent.facility_id==user.facility_id,StudyEvent.synthetic==synthetic,StudyEvent.created_at>=lo,StudyEvent.created_at<asof))
        if any(digest(r.payload)!=r.payload_hash for r in events): raise HTTPException(409,'Study event integrity mismatch')
        encounters = bounded(db,select(Encounter).join(Patient,Patient.id==Encounter.patient_id).where(Encounter.facility_id==user.facility_id,Patient.synthetic==synthetic,Encounter.created_at>=lo,Encounter.created_at<asof))
        in_period = lambda value: start.isoformat()<=value<=end.isoformat()
        enrolments = [r for r in observations if r.kind=='enrolment' and in_period(r.payload['index_date'])]
        active = [r for r in enrolments if r.payload['status']=='enrolled']
        due = [r for r in active if date.fromisoformat(r.payload['index_date'])+timedelta(days=30)<=end]
        followups = [r for r in observations if r.kind=='followup' and r.payload['contact_date']<=end.isoformat()]
        complete = {}
        for enrol in due:
            day = date.fromisoformat(enrol.payload['index_date'])
            candidates = [r for r in followups if r.patient_id==enrol.patient_id and r.payload['status']=='completed'
                          and 21<=(date.fromisoformat(r.payload['contact_date'])-day).days<=45]
            if candidates: complete[enrol.patient_id] = min(candidates,key=lambda r:abs((date.fromisoformat(r.payload['contact_date'])-day).days-30))
        tally = [r for r in observations if r.kind=='daily_tally' and in_period(r.payload['clinic_date'])]
        encounter_ids = {r.id for r in encounters}
        visits = [r for r in observations if r.kind=='visit' and r.encounter_id in encounter_ids]
        safety = [r for r in observations if r.kind=='safety' and in_period(r.payload['occurred_on'])]
        briefs = [r for r in events if r.action=='encounter.ai_briefing']
        decisions = Counter(d.get('action','unknown') for r in encounters for d in (r.review or {}).get('decisions',[]))
        med = lambda xs: statistics.median(xs) if xs else None
        timing = {method:[r.payload['consultation_minutes'] for r in visits if r.payload['timing_method']==method] for method in ('observed','estimated')}
        paired = [complete[r.patient_id].payload['systolic_bp']-r.payload['_baseline']['systolic_bp'] for r in due
                  if r.patient_id in complete and complete[r.patient_id].payload.get('systolic_bp') is not None and r.payload['_baseline'].get('systolic_bp') is not None]
        summary = {
            'metrics_version':METRICS_VERSION,'generated_at':iso(utcnow()),'as_of':iso(asof),
            'window':{'start':str(start),'end':str(end),'timezone':'Africa/Nairobi','synthetic':synthetic},
            'patients_seen':len({r.patient_id for r in encounters}),'encounters':len(encounters),
            'clinicians_recording_encounters':len({r.created_by for r in encounters}),
            'review_completion':rate(sum(r.status=='reviewed' for r in encounters),len(encounters)),
            'enrolment_status':dict(Counter(r.payload['status'] for r in enrolments)),
            'enrolled_patients':len(active),'clinic_days_reported':len(tally),
            'enrolled_age_bands':dict(Counter(r.payload['_age_band'] for r in active)),
            'enrolled_sex':dict(Counter(r.payload['_sex'] for r in active)),
            'adoption':rate(sum(r.payload['app_used_visits'] for r in tally),sum(r.payload['eligible_visits'] for r in tally)),
            'non_use':{k:sum(r.payload[k] for r in tally) for k in ('non_use_connectivity','non_use_workload','non_use_declined','non_use_other')},
            'followup_completion':rate(len(complete),len(due)),
            'followup_outside_window_or_not_completed':len(due)-len(complete),
            'visit_observation_coverage':rate(len(visits),len(encounters)),
            'consultation_minutes':{k:{'n':len(v),'median':med(v)} for k,v in timing.items()},
            'decision_changes_reported':dict(Counter(r.payload['decision_changed'] for r in visits)),
            'recommendation_decisions':dict(decisions),
            'workflow_issues':dict(Counter(r.payload['workflow_issue'] for r in visits)),
            'consultation_languages':dict(Counter(r.payload['language'] for r in visits)),
            'helpfulness_ratings':dict(Counter(str(r.payload['helpfulness']) if r.payload['helpfulness'] is not None else 'not_recorded' for r in visits)),
            'safety_screening':dict(Counter(r.payload['safety_screening'] for r in visits)),
            'safety_reports':len(safety),'safety_severity':dict(Counter(r.payload['severity'] for r in safety)),
            'open_safety_reports':sum(r.payload['status']=='open' for r in safety),
            'persisted_ai_briefings':len(briefs),'ai_status':dict(Counter(r.payload['ai'].get('status') or 'unknown' for r in briefs)),
            'ai_latency_ms':{'n':sum(r.payload['ai'].get('latency_ms') is not None for r in briefs),'median':med([r.payload['ai']['latency_ms'] for r in briefs if r.payload['ai'].get('latency_ms') is not None])},
            'activity_events':dict(Counter(r.action for r in events)),
            'assessment_versions':dict(Counter(r.payload.get('rules_version') or 'unknown' for r in events if r.action=='encounter.assess')),
            'dose_check_status':dict(Counter(d.get('status','unknown') for r in events if r.action=='encounter.assess' for d in r.payload.get('dose_results',[]))),
            'paired_systolic_change_mmHg':{'n':len(paired),'mean':round(statistics.mean(paired),2) if paired else None},
            'limits':[
                'Descriptive single-facility feasibility data; no causal effectiveness or clinical accuracy estimate.',
                'Adoption uses manually entered eligible clinic visits on reported days only; repeat visits are not unique patients.',
                'Follow-up: active enrollees whose day 30 is due by report end; completed contacts on days 21–45, closest to day 30. Withdrawals are reported separately.',
                'Events begin with this release. Unsubmitted forms, failures before persistence, offline use and unreported harms are not automatically captured.',
                'Encounter status reflects the current saved record; study revisions and events are restricted to the as-of cutoff. Save the export to freeze a readout.',
                'A zero safety count means no events reported, not proven absence of harm. Timing estimates are separate from observed timings.',
                'Baseline BP is frozen at enrolment. Paired change is descriptive, with no control group or adjustment for missing follow-up.'
            ]}
        if not export: return summary
        def pseudonym(patient_id):
            return hmac.new(settings.secret_key.encode(),f'study-v1:{user.facility_id}:{patient_id}'.encode(),hashlib.sha256).hexdigest()[:32]
        cohort_ids = {r.patient_id for r in enrolments}
        rows=[]
        for row in observations:
            if row.patient_id not in cohort_ids: continue
            data = {k:v for k,v in row.payload.items() if k not in {'description','immediate_action','incident_id','_submission_hash'} and not k.startswith('_')}
            if row.kind=='enrolment': data.update(baseline=row.payload['_baseline'],age_band=row.payload['_age_band'],sex=row.payload['_sex'],recorded_conditions=row.payload['_conditions'])
            rows.append({'patient_code':pseudonym(row.patient_id),'encounter_code':pseudonym('encounter:'+row.encounter_id),'kind':row.kind,'revision':row.revision,'recorded_at':iso(row.created_at),'data':data})
        activity=[]
        for row in events:
            if row.patient_id not in cohort_ids: continue
            data={k:v for k,v in row.payload.items() if k not in {'referral_id','assessment_id'}}
            activity.append({'patient_code':pseudonym(row.patient_id),'encounter_code':pseudonym('encounter:'+row.encounter_id),
                             'clinician_code':pseudonym('clinician:'+row.actor_id),'action':row.action,'recorded_at':iso(row.created_at),'data':data})
        output={'summary':summary,'classification':'Pseudonymised health data; not anonymous. Store only in approved study storage.',
                'rows':rows,'activity':activity,'content_sha256':digest({'rows':rows,'activity':activity})}
        return output

    @api.get('/api/study/summary')
    def summary(start: date,end: date,synthetic: bool,db: DB,user: PRIVILEGED):
        output=report(db,user,start,end,synthetic)
        commit_change(db,user,'study.summary_view','facility',user.facility_id)
        return output

    @api.get('/api/study/export')
    def export(start: date,end: date,synthetic: bool,db: DB,user: CLINICAL):
        if user.role!='supervisor': raise HTTPException(403,'Clinical supervisor role required for patient-level study export')
        output=report(db,user,start,end,synthetic,export=True)
        commit_change(db,user,'study.export','facility',user.facility_id)
        return output
