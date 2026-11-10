import os
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
api_key = os.getenv("CLOSE_CRM_API_KEY")
auth = (api_key, "")

BASE_URL = "https://api.close.com/api/v1"
KP_OUTCOME_ID = "outcome_033WrVULhq3NJjJSQLPgxg"
KP_METRIC_KEY = f"outcome.{KP_OUTCOME_ID}.count"
CALLS_METRIC_KEY = "calls.all.all.count"

selected_user_ids = [
    "user_TcBTZtqa1UlOlFQyDlhLJzEywClWo3CTQwXt2OREF2e",  # Hernan Bonilla
    "user_7cXDrv9AKnoVTSOnXBJo2oYXmUrFRDG40sIYVhmDwHA",  # Juan Abuchaibe
    "user_BZhhrwAL2irTmKaPIntbraEWoINZrcYpKlGUUXsfwcV",  # Juan Arango
    "user_ESOupvkhojB5X4SkkJ20Nv05U2Klc0ImoRgS4Hwbwms",  # Juan Cordoba
    "user_piUkoIPqMs7i1Lm3vdc2c2pE3lPjU3cCRvrmvxMonGy",  # Julian Prado
    "user_QrLrTvgnGNQRS7AMKX2EuCFrZKvqgKmIUloYX1TkRQd",  # Mariana Polanco
    "user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D",  # Roy Jones
    "user_n1y0yxmKit3rxkJlxhKZXFxEvG4y4G7C4cr4GPypUTx",  # Sebastian Jordan
]

start_date = "2026-11-02"
end_date = "2026-11-06"

payload = {
    "type": "comparison",
    "datetime_range": {
        "start": f"{start_date}T00:00:00-05:00",
        "end": f"{end_date}T23:59:59-05:00"
    },
    "metrics": [CALLS_METRIC_KEY, KP_METRIC_KEY],
    "users": selected_user_ids
}

r = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=payload, timeout=25)
res = r.json()
lookup_users = res.get("lookup", {}).get("user", {})
user_rows = res.get("data", [])

per_user = []
total_calls = 0
total_kps = 0

for row in user_rows:
    uid = row.get("user_id")
    if uid not in selected_user_ids:
        continue
    name = lookup_users.get(uid, {}).get("display", uid)
    c_count = row.get(CALLS_METRIC_KEY, 0) or 0
    kp_count = row.get(KP_METRIC_KEY, 0) or 0
    total_calls += c_count
    total_kps += kp_count
    eff = round(100.0 * kp_count / c_count, 2) if c_count else 0.0
    per_user.append({
        "user_id": uid,
        "name": name,
        "calls": c_count,
        "kps": kp_count,
        "effectiveness": eff
    })

# Fetch AM vs PM
def _fetch_day_calls(day_str, period):
    if period == "AM":
        time_range = {"start": f"{day_str}T00:00:00-05:00", "end": f"{day_str}T12:00:00-05:00"}
    else:
        time_range = {"start": f"{day_str}T12:00:00-05:00", "end": f"{day_str}T23:59:59-05:00"}
    pl = {
        "type": "overview",
        "datetime_range": time_range,
        "metrics": [CALLS_METRIC_KEY],
        "users": selected_user_ids
    }
    resp = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=pl, timeout=15)
    if resp.status_code == 200:
        return resp.json().get("aggregations", {}).get("totals", {}).get(CALLS_METRIC_KEY, 0) or 0
    return 0

days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
with ThreadPoolExecutor(max_workers=5) as executor:
    tasks_am = [executor.submit(_fetch_day_calls, d, "AM") for d in days]
    tasks_pm = [executor.submit(_fetch_day_calls, d, "PM") for d in days]
    am_calls = sum(t.result() for t in tasks_am)
    pm_calls = sum(t.result() for t in tasks_pm)

eff_total = round(100.0 * total_kps / total_calls, 2) if total_calls else 0.0

print(f"=== METRICAS EXACTAS CLOSE CRM (ALL CALLS - ALL TYPES) ===")
print(f"Llamadas Totales: {total_calls} (esperado: 703)")
print(f"  - Llamadas AM:  {am_calls}")
print(f"  - Llamadas PM:  {pm_calls}")
print(f"KPs Totales:      {total_kps} (esperado: 56)")
print(f"Efectividad:      {eff_total}%\n")

print("--- Desglose Individual ---")
for a in sorted(per_user, key=lambda x: x["calls"], reverse=True):
    print(f"{a['name']:20} | Llamadas: {a['calls']:4} | KPs: {a['kps']:3} | Efectividad: {a['effectiveness']:5.2f}%")
