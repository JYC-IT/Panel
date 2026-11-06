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

# Test date filter for Week 24 (Oct 12 to Oct 16)
params = {
    'direction': 'outbound',
    'date_created__gte': '2026-10-12T00:00:00Z',
    'date_created__lte': '2026-10-16T23:59:59Z',
    '_limit': 100
}
r = requests.get('https://api.close.com/api/v1/activity/call/', auth=auth, params=params)
print('Date filter status:', r.status_code)
if r.status_code == 200:
    data = r.json()
    print('Calls returned:', len(data.get('data', [])), '| Has more:', data.get('has_more'))
