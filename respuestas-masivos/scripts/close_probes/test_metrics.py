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
r = requests.get('https://api.close.com/api/v1/report/activity/metrics/', auth=(api_key, ''))
print('Status:', r.status_code)
if r.status_code == 200:
    metrics = r.json().get('data', [])
    print(f'Total metrics: {len(metrics)}')
    for m in metrics:
        k = m.get('key', '')
        if 'call' in k or 'outcome' in k:
            print(f"Key: {k} | Label: {m.get('label')}")
