"""No-record-data HTTPS availability probe for the authorized NCDAI deployment."""
import json
import time
import urllib.request
from datetime import datetime, timezone

ORIGIN='https://ncdai-2.vercel.app'
checks=[]
for path in ['/api/health/live','/api/health/ready','/api/health/consultant','/','/consultant']:
    started=time.monotonic()
    try:
        with urllib.request.urlopen(ORIGIN+path,timeout=20) as response:
            if path.startswith('/api/'):
                payload=json.load(response)
                passed=response.status==200 and payload.get('status') in {'live','ready'}
            else:
                page=response.read(100000).decode('utf-8')
                passed=response.status==200 and 'text/html' in response.headers.get('Content-Type','') and 'id="root"' in page
    except Exception:
        passed=False
    checks.append({'endpoint':path,'passed':passed,'elapsed_seconds':round(time.monotonic()-started,3)})
print(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks},indent=2))
raise SystemExit(0 if all(c['passed'] for c in checks) else 1)
