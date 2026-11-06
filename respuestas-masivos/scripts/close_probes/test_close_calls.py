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

# Fetch recent calls
r = requests.get('https://api.close.com/api/v1/activity/call/', auth=auth, params={'_limit': 10})
print('Call list status:', r.status_code)
if r.status_code == 200:
    data = r.json()
    calls = data.get('data', [])
    print(f'Total sample calls: {len(calls)}')
    for c in calls[:5]:
        print(f"ID: {c.get('id')} | User: {c.get('user_name')} ({c.get('user_id')}) | Direction: {c.get('direction')} | Disposition: {c.get('disposition')} | Duration: {c.get('duration')}s | Date: {c.get('date_created')}")
        # print extra fields if any
        if 'note' in c:
            print(f"   Note: {c.get('note')[:50] if c.get('note') else 'None'}")
        if 'call_disposition' in c:
            print(f"   Call disposition: {c.get('call_disposition')}")

# Check reporting activity endpoint or custom fields
r_rep = requests.get('https://api.close.com/api/v1/report/activity/', auth=auth)
print('Report activity status:', r_rep.status_code)
if r_rep.status_code == 200:
    print('Report activity keys:', list(r_rep.json().keys()))

# Check activity outcomes in Close CRM settings
r_fields = requests.get('https://api.close.com/api/v1/custom_field/activity/', auth=auth)
print('Activity custom fields status:', r_fields.status_code)
if r_fields.status_code == 200:
    fields = r_fields.json().get('data', [])
    for f in fields:
        print('Field:', f.get('name'), '| Type:', f.get('type'), '| Choices:', f.get('choices'))
