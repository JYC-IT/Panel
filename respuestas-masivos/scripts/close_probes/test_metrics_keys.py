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
data = r.json()
print("Top-level keys in response:", list(data.keys()))
for m in data.get('metrics', [])[:30]:
    print(m.get('key'), "-->", m.get('name'))
