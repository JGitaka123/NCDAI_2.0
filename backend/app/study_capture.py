"""Record future clinical activity without copying directory details or free text."""
import os
from .models import StudyEvent, Encounter, Patient, Referral
from .consultations import digest

METRICS_VERSION='ncdai-study-metrics-20260914.1'

def capture_event(db, audit):
    if audit.action not in {'encounter.create','encounter.assess','encounter.ai_briefing','encounter.review','referral.create','referral.accepted','referral.completed','referral.cancelled'}:
        return
    referral=db.get(Referral,audit.entity_id) if audit.entity_type=='referral' else None
    encounter=db.get(Encounter,referral.encounter_id if referral else audit.entity_id)
    if encounter is None: return
    patient=db.get(Patient,encounter.patient_id)
    assessment=encounter.assessment or {}
    review=encounter.review or {}
    briefing=assessment.get('ai_briefing') or {}
    data={'metrics_version':METRICS_VERSION,'encounter_version':encounter.version,'application_commit':os.getenv('VERCEL_GIT_COMMIT_SHA') or os.getenv('NCDAI_RELEASE_COMMIT'),
          'assessment_id':assessment.get('id'),'rules_version':assessment.get('rules_version'),
          'evidence_version':assessment.get('evidence_version'),'urgency':assessment.get('urgency'),
          'missing_data':assessment.get('missing_data',[]),
          'recommendations':[{k:r.get(k) for k in ['id','rule_id','severity','category']} for r in assessment.get('recommendations',[])],
          'dosing_version':(assessment.get('dosing') or {}).get('version'),
          'dose_results':[{k:r.get(k) for k in ['medicine_id','status']} for r in (assessment.get('dosing') or {}).get('results',[])],
          'ai':{k:briefing.get(k) for k in ['status','reason_code','provider','model','prompt_version','usage','latency_ms']},
          'decisions':[{k:r.get(k) for k in ['recommendation_id','action']} for r in review.get('decisions',[])],
          'referral_id':referral.id if referral else None,'referral_status':referral.status if referral else None}
    db.add(StudyEvent(id=audit.id,facility_id=audit.facility_id,patient_id=patient.id,encounter_id=encounter.id,
                     actor_id=audit.actor_id,action=audit.action,synthetic=patient.synthetic,payload=data,
                     payload_hash=digest(data),created_at=audit.created_at))
