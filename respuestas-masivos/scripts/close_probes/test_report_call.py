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
    "relative_range": "this-week",
    "metrics": [
        "calls.outbound.all.count",
        "outcome.outcome_033WrVULhq3NJjJSQLPgxg.count"
    ]
}

r = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload)
print('Status:', r.status_code)
if r.status_code == 200:
    res = r.json()
    print("Report data per user:")
    for row in res.get('data', []):
        u_id = row.get('user_id')
        u_name = row.get('user_name')
        calls = row.get('metrics', {}).get('call.outbound.count', 0)
        kps = row.get('metrics', {}).get('outcome.outcome_033WrVULhq3NJjJSQLPgxg.count', 0)
        print(f"  {u_name} ({u_id}): {calls} outbound calls | {kps} KPs")
else:
    print("Error:", r.text)
