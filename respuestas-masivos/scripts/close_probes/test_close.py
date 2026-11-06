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

# 1. Test me endpoint
r = requests.get('https://api.close.com/api/v1/me/', auth=auth)
print('Me status:', r.status_code)
if r.status_code == 200:
    data = r.json()
    print('User:', data.get('first_name'), data.get('email'))
    orgs = data.get('organizations', [])
    print('Organizations:', [o.get('name') for o in orgs])

# 2. List all users
r_users = requests.get('https://api.close.com/api/v1/user/', auth=auth)
print('Users status:', r_users.status_code)
if r_users.status_code == 200:
    users = r_users.json().get('data', [])
    print(f'Total users in Close: {len(users)}')
    for u in users:
        print(f"  ID: {u.get('id')} | Name: {u.get('first_name')} {u.get('last_name')} | Email: {u.get('email')}")

# 3. Check custom activity types or call outcomes
r_custom = requests.get('https://api.close.com/api/v1/custom_activity_type/', auth=auth)
print('Custom activity status:', r_custom.status_code)
if r_custom.status_code == 200:
    types = r_custom.json().get('data', [])
    print('Custom activity types:', [t.get('name') for t in types])

# 4. Check call outcomes / choices
r_status = requests.get('https://api.close.com/api/v1/status/lead/', auth=auth)
print('Lead status code:', r_status.status_code)
