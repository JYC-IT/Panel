import os, requests
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('CLOSE_CRM_API_KEY', '').strip()
auth = (key, '')

# Let's check available metrics in report/activity
payload = {
    "type": "overview",
    "datetime_range": {
        "start": "2026-10-19T00:00:00-04:00",
        "end": "2026-10-23T23:59:59-04:00"
    },
    "metrics": [
        "calls.outbound.all.count",
        "outcome.outcome_033WrVULhq3NJjJSQLPgxg.count"
    ]
}
r2 = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload)
print('r2 status:', r2.status_code)
if r2.status_code == 200:
    print('r2 totals:', r2.json().get('aggregations', {}).get('totals', {}))
else:
    print('r2 error:', r2.text)

# Let's inspect call custom fields
r3 = requests.get('https://api.close.com/api/v1/custom_field/activity/call/', auth=auth)
print('custom fields status:', r3.status_code)
if r3.status_code == 200:
    for cf in r3.json().get('data', []):
        print('Field:', cf.get('name'), cf.get('id'), cf.get('type'))
