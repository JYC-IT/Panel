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

payload = {
    "type": "invalid",
    "relative_range": "invalid",
    "metrics": ["invalid"]
}

r = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload)
print(r.status_code)
print(r.text)
