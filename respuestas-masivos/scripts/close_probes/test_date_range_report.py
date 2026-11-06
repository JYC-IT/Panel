import requests
import json

import os
try:
    from dotenv import load_dotenv
    for _p in [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(__file__), '..', '.env'),
        os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    ]:
        if os.path.exists(_p):
            load_dotenv(_p)
            break
except ImportError:
    pass

api_key = os.getenv('CLOSE_CRM_API_KEY', '')
auth = (api_key, '')

payload = {
    "type": "comparison",
    "datetime_range": {
        "start": "2026-10-12T00:00:00Z",
        "end": "2026-10-16T23:59:59Z"
    },
    "metrics": [
        "calls.outbound.all.count",
        "outcome.outcome_033WrVULhq3NJjJSQLPgxg.count"
    ]
}

r = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload)
print('Status:', r.status_code)
if r.status_code == 200:
    res = r.json()
    print("Totals for Oct 12-16:", res.get('aggregations', {}).get('totals'))
    lookup = res.get('lookup', {}).get('user', {})
    for row in res.get('data', []):
        uid = row.get('user_id')
        name = lookup.get(uid, {}).get('display', uid)
        calls = row.get('calls.outbound.all.count', 0)
        kps = row.get('outcome.outcome_033WrVULhq3NJjJSQLPgxg.count', 0)
        print(f"  {name:20}: {calls:4} calls | {kps:2} KPs")
