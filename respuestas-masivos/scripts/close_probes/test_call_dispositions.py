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

# Test call disposition endpoint
for ep in ['call_disposition', 'call_outcome', 'activity_outcome', 'status/call', 'report/activity/user']:
    r = requests.get(f'https://api.close.com/api/v1/{ep}/', auth=auth)
    print(f"{ep}: status {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  Keys / data: {list(data.keys()) if isinstance(data, dict) else len(data)}")
        if isinstance(data, dict) and 'data' in data:
            print("  Items:", [item.get('name') or item.get('label') or item.get('id') for item in data['data'][:5]])
        elif isinstance(data, list):
            print("  Items:", [item.get('name') or item.get('label') or item.get('id') for item in data[:5]])

# Inspect one full call object to see all its keys and custom fields
r_call = requests.get('https://api.close.com/api/v1/activity/call/', auth=auth, params={'_limit': 1})
if r_call.status_code == 200 and r_call.json().get('data'):
    c = r_call.json()['data'][0]
    print("\nFull call object keys:")
    for k, v in c.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            print(f"  {k} (dict): {v}")
