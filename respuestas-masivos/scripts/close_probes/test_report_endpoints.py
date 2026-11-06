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

endpoints = [
    'report',
    'report/activity',
    'report/call',
    'report/activity/call',
    'data-pipeline'
]

for ep in endpoints:
    # Try GET and POST
    r_get = requests.get(f'https://api.close.com/api/v1/{ep}/', auth=auth)
    print(f"GET {ep}: {r_get.status_code}")
    if r_get.status_code in (200, 400, 422):
        print("  Response:", r_get.text[:200])

    r_post = requests.post(f'https://api.close.com/api/v1/{ep}/', auth=auth, json={})
    print(f"POST {ep}: {r_post.status_code}")
    if r_post.status_code in (200, 400, 422):
        print("  Response:", r_post.text[:200])
