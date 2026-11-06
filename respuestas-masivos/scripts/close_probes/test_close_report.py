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
    "type": "user",
    "relative_range": "this_week",
    "metrics": [
        "call_outbound_count",
        "call_outbound_duration",
        "call_created_count"
    ]
}

r = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload)
print('Status:', r.status_code)
if r.status_code != 200:
    print('Error:', r.text)
else:
    print('Result keys:', list(r.json().keys()))
    print(json.dumps(r.json(), indent=2)[:500])
