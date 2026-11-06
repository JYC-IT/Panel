import requests
from datetime import datetime, timezone, timedelta

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

# Query comparison report for Oct 12 - 16
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
data = r.json()
lookup = data.get('lookup', {}).get('user', {})
print("Users in Oct 12-16:")
rows = data.get('data', [])
for r in rows:
    uid = r.get('user_id')
    name = lookup.get(uid, {}).get('display', uid)
    calls = r.get('calls.outbound.all.count', 0)
    kps = r.get('outcome.outcome_033WrVULhq3NJjJSQLPgxg.count', 0)
    print(f"  {name:20}: {calls:4} calls | {kps:2} KPs | user_id: {uid}")
