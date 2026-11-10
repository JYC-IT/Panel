import os
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
auth = (os.getenv("CLOSE_CRM_API_KEY"), "")
BASE_URL = "https://api.close.com/api/v1"

# Fecha: Nov 9, 2026
start_iso = "2026-11-09T00:00:00-05:00"
end_iso = "2026-11-09T23:59:59-05:00"

calls = []
skip = 0
while True:
    r = requests.get(f"{BASE_URL}/activity/call/", auth=auth, params={
        "date_created__gte": start_iso,
        "date_created__lte": end_iso,
        "_limit": 100,
        "_skip": skip
    })
    data = r.json().get("data", [])
    calls.extend(data)
    if not r.json().get("has_more") or len(data) < 100:
        break
    skip += len(data)

print(f"Total llamadas obtenidas para Nov 09: {len(calls)}")

user_calls = defaultdict(list)
for c in calls:
    user_calls[c.get("user_name") or "Desconocido"].append(c)

local_tz = timezone(timedelta(hours=-5))

for user, ucalls in sorted(user_calls.items()):
    ucalls.sort(key=lambda x: x["date_created"])
    gaps = []
    for i in range(len(ucalls) - 1):
        c1 = ucalls[i]
        c2 = ucalls[i+1]

        t1_start = datetime.fromisoformat(c1["date_created"])
        dur1 = timedelta(seconds=c1.get("duration") or 0)
        t1_end = t1_start + dur1
        t2_start = datetime.fromisoformat(c2["date_created"])

        diff = t2_start - t1_end
        diff_minutes = round(diff.total_seconds() / 60.0, 1)

        if diff_minutes >= 30:
            c1_end_local = t1_end.astimezone(local_tz).strftime("%I:%M %p")
            c2_start_local = t2_start.astimezone(local_tz).strftime("%I:%M %p")
            gaps.append({
                "gap_min": diff_minutes,
                "from_time": c1_end_local,
                "to_time": c2_start_local,
                "lead_before": c1.get("lead_id"),
                "lead_after": c2.get("lead_id"),
                "phone_before": c1.get("remote_phone_formatted") or c1.get("remote_phone") or "N/A",
                "phone_after": c2.get("remote_phone_formatted") or c2.get("remote_phone") or "N/A"
            })
    print(f"\nAsesor: {user} ({len(ucalls)} llamadas) -> {len(gaps)} pausas >= 30 min")
    for g in gaps:
        print(f"   [ALERTA] Pausa de {g['gap_min']} min: de {g['from_time']} a {g['to_time']} (Ant: {g['phone_before']} -> Sig: {g['phone_after']})")
