import requests
from collections import Counter

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

# Fetch recent 500 calls
r = requests.get('https://api.close.com/api/v1/activity/call/', auth=auth, params={'_limit': 100, 'direction': 'outbound'})
print('Status code:', r.status_code)
if r.status_code != 200:
    print('Error:', r.text)
if r.status_code == 200:
    calls = r.json().get('data', [])
    print(f"Total outbound calls sampled: {len(calls)}")
    user_counts = Counter(c.get('user_name') for c in calls)
    print("Call counts by user in recent sample:")
    for user, cnt in user_counts.most_common():
        print(f"  {user}: {cnt} calls")

    kp_counts = Counter(c.get('user_name') for c in calls if c.get('outcome_id') == 'outcome_033WrVULhq3NJjJSQLPgxg')
    print("\nKP counts by user in recent sample:")
    for user, cnt in kp_counts.most_common():
        print(f"  {user}: {cnt} KPs")
