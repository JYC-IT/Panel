import os, requests
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('CLOSE_CRM_API_KEY', '').strip()
auth = (key, '')

users_r = requests.get('https://api.close.com/api/v1/user/', auth=auth)
users = {}
for u in users_r.json().get('data', []):
    name = f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip() or u.get('email')
    users[u['id']] = name

params = {
    'date_created__gte': '2026-10-19T00:00:00Z',
    'date_created__lte': '2026-10-23T23:59:59Z',
    '_limit': 100
}
has_more = True
cursor = None
all_calls = []
while has_more:
    if cursor:
        params['_cursor'] = cursor
    r = requests.get('https://api.close.com/api/v1/activity/call/', auth=auth, params=params)
    data = r.json()
    items = data.get('data', [])
    all_calls.extend(items)
    has_more = data.get('has_more', False)
    cursor = data.get('cursor_next')
    if len(items) == 0:
        break

print(f"Total Call activities in Close for 2026-10-19 to 2026-10-23: {len(all_calls)}")
from collections import Counter
print("By direction:", Counter(c.get('direction') for c in all_calls))
print("By user:", Counter(users.get(c.get('user_id'), c.get('user_id')) for c in all_calls))

# Outbound calls
outbound = [c for c in all_calls if c.get('direction') == 'outbound']
print(f"Total Outbound Calls: {len(outbound)}")

# Dispositions / Outcomes
print("Dispositions in Outbound:")
for k, v in Counter(c.get('disposition') for c in outbound).most_common():
    print(f"  {k}: {v}")

# Check any custom fields or outcomes or statuses
kp_id = 'outcome_033WrVULhq3NJjJSQLPgxg' # "Talked to KP – Needs Next Step"
kp_calls = [c for c in outbound if c.get('disposition') == kp_id or kp_id in str(c)]
print(f"Calls with KP disposition ({kp_id}): {len(kp_calls)}")

# What other outcomes exist in Close CRM?
outcomes_r = requests.get('https://api.close.com/api/v1/custom_activity_type/', auth=auth)
print("Custom activity types:", len(outcomes_r.json().get('data', [])))
