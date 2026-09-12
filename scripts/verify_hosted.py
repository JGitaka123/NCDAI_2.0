"""Non-destructive acceptance workflow against this synthetic NCDAI deployment.

Adds one fictional record and one completed referral. Uses one optional live AI
request. Credentials are read from a private file and never included in reports.
"""
from pathlib import Path
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]


def run():
    access = json.loads(Path(os.getenv('NCDAI_HOSTED_ACCESS', str(ROOT / '.runtime/hosted-access.json'))).read_text())
    origin = access['url'].rstrip('/')
    if origin != 'https://ncdai-2.vercel.app':
        raise ValueError('This runner targets only the dedicated NCDAI synthetic deployment')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'origin': origin,
              'kind': 'Hosted synthetic engineering acceptance; not clinical validation', 'checks': []}
    with httpx.Client(base_url=origin, timeout=60, follow_redirects=False, trust_env=False, headers={'Origin': origin}) as client:
        def request(method, path, status=200, **kwargs):
            response = client.request(method, '/api' + path, **kwargs)
            assert response.status_code == status, f'{method} {path}: expected {status}, got {response.status_code}'
            return response.json() if response.content else None

        ready = request('GET', '/health/ready')
        assert ready['synthetic_only'] is True and ready['status'] == 'ready'
        request('GET', '/patients', 401)
        report['checks'].append('ready database/rules; unauthenticated records denied')
        auth_response = client.post('/api/auth/login', json={'email': access['email'], 'password': access['password']})
        assert auth_response.status_code == 200, f'Hosted login returned {auth_response.status_code}'
        cookie = auth_response.headers.get('set-cookie', '').lower()
        assert all(part in cookie for part in ['httponly', 'secure', 'samesite=strict', 'path=/api'])
        client.headers['X-CSRF-Token'] = auth_response.json()['csrf_token']
        report['checks'].append('authenticated session with secure HttpOnly Strict cookie')

        record_id = 'HOSTED-' + uuid4().hex[:12]
        patient = request('POST', '/patients', 201, json={'external_id': record_id, 'given_name': 'Synthetic',
            'family_name': 'HostedAcceptance', 'date_of_birth': '1968-01-01', 'sex': 'male', 'synthetic': True})
        data = {'systolic_bp': 190, 'diastolic_bp': 115, 'pulse': 92, 'glucose': 7,
            'glucose_unit': 'mmol/L', 'hba1c': 7.5, 'egfr': 50, 'potassium': 4.5,
            'known_hypertension': 'yes', 'known_diabetes': 'yes', 'known_asthma': 'no',
            'known_copd': 'no', 'known_ckd': 'unknown', 'known_cancer': 'no',
            'pregnancy_status': 'not_applicable', 'symptoms': ['chest_pain'], 'symptoms_reviewed': True,
            'allergies': [], 'allergies_reviewed': True, 'medications': [], 'medications_reviewed': True,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'notes': 'Fictional deployment acceptance case.'}
        encounter = request('POST', '/encounters', 201, json={'patient_id': patient['id'], 'data': data})
        encounter = request('POST', f"/encounters/{encounter['id']}/assess")
        original = encounter['assessment']
        assert original['urgency'] == 'emergency'
        assert any(item['severity'] == 'critical' for item in original['recommendations'])
        assert all(item['evidence'] for item in original['recommendations'])
        report['checks'].append('persisted fictional encounter; emergency findings and evidence retained')

        if os.getenv('NCDAI_HOSTED_LIVE_AI') == '1':
            encounter = request('POST', f"/encounters/{encounter['id']}/ai-briefing", json={
                'assessment_id': original['id'], 'expected_version': encounter['version']})
            updated = encounter['assessment']
            assert {key: value for key, value in updated.items() if key != 'ai_briefing'} == original
            briefing = updated['ai_briefing']
            assert briefing['urgency'] == original['urgency']
            assert all(item in briefing['focus'] for item in original['recommendations'] if item['severity'] == 'critical')
            assert all(item in original['recommendations'] for item in briefing['focus'])
            report['ai'] = {key: briefing.get(key) for key in ['status','reason_code','provider','model','prompt_version','usage','latency_ms']}
            report['checks'].append('live provider request preserves all original findings and urgency')

        assessment = encounter['assessment']
        decisions = [{'recommendation_id': item['id'], 'action': 'accept'} for item in assessment['recommendations']]
        reviewed = request('POST', f"/encounters/{encounter['id']}/review", json={
            'assessment_id': assessment['id'], 'expected_version': encounter['version'], 'decisions': decisions,
            'note': 'Synthetic deployment test; this is not clinical endorsement.'})
        assert reviewed['status'] == 'reviewed'
        retrieved = request('GET', f"/encounters/{encounter['id']}")
        assert retrieved['review']['assessment_snapshot'] == assessment
        request('PATCH', f"/encounters/{encounter['id']}", 409, json={'expected_version': retrieved['version'], 'data': data})
        report['checks'].append('clinician decisions persisted; reviewed record rejects alteration')
        referral = request('POST', f"/encounters/{encounter['id']}/referrals", 201, json={
            'reason': 'Fictional deployment test', 'destination': 'Synthetic receiving clinic', 'urgency': assessment['urgency']})
        assert referral['patient_external_id'] == record_id
        request('PATCH', f"/referrals/{referral['id']}", json={'status': 'accepted'})
        completed = request('PATCH', f"/referrals/{referral['id']}", json={'status': 'completed', 'outcome': 'Synthetic outcome recorded.'})
        assert completed['status'] == 'completed'
        bundle = request('GET', f"/fhir/Bundle/{encounter['id']}")
        assert {'Patient','Encounter','DocumentReference'} <= {entry['resource']['resourceType'] for entry in bundle['entry']}
        report['checks'].append('identified referral completed; reviewed FHIR export retrieved')
        audit = request('GET', '/audit/verify')
        assert audit['valid']
        report['audit'] = {'valid': audit['valid'], 'events': audit['events']}
        request('POST', '/auth/logout', 204)
        request('GET', '/patients', 401)
        report['checks'].append('audit chain valid; logout revokes access')
    report['passed'] = True
    destination = ROOT / 'docs/test-results/hosted-acceptance.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
