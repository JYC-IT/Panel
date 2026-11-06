import requests

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
r = requests.get('https://api.close.com/api/v1/report/activity/metrics/', auth=auth)
metrics = r.json().get('data', [])
for m in metrics:
    if 'call' in m['key']:
        print(f"Key: {m['key']} | Name: {m.get('name')}")
