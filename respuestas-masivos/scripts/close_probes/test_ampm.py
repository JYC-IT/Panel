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

# Test querying AM vs PM for Oct 12-16 using datetime ranges
# Oct 12 to Oct 16 is 5 days (Monday to Friday)
# In local time UTC-5 (Bogota / Eastern Daylight Time is UTC-4 in summer):
# AM is 00:00 to 12:00 local time
# PM is 12:00 to 23:59 local time

days = ['2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-16']
total_am = 0
total_pm = 0

for d in days:
    payload_am = {
        "type": "overview",
        "datetime_range": {
            "start": f"{d}T00:00:00-04:00",
            "end": f"{d}T12:00:00-04:00"
        },
        "metrics": ["calls.outbound.all.count"]
    }
    payload_pm = {
        "type": "overview",
        "datetime_range": {
            "start": f"{d}T12:00:00-04:00",
            "end": f"{d}T23:59:59-04:00"
        },
        "metrics": ["calls.outbound.all.count"]
    }
    r_am = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload_am)
    r_pm = requests.post('https://api.close.com/api/v1/report/activity/', auth=auth, json=payload_pm)
    am = r_am.json().get('aggregations', {}).get('totals', {}).get('calls.outbound.all.count', 0)
    pm = r_pm.json().get('aggregations', {}).get('totals', {}).get('calls.outbound.all.count', 0)
    total_am += am
    total_pm += pm

print(f"Total AM: {total_am} | Total PM: {total_pm} | Total: {total_am + total_pm}")
