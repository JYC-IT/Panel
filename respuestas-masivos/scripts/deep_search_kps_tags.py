import os
import sys
import requests
from collections import defaultdict
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
api_key = os.getenv("CLOSE_CRM_API_KEY")
auth = (api_key, "")

BASE_URL = "https://api.close.com/api/v1"

start_date = "2026-11-02T00:00:00-05:00"
end_date = "2026-11-06T23:59:59-05:00"

print("=== BÚSQUEDA DETALLADA DE #TKP Y #EKP EN SEMANA 27 (NOV 02 - NOV 06) ===")

def search_activities(activity_type, date_field="date_created"):
    results = []
    skip = 0
    while True:
        params = {
            "_limit": 100,
            "_skip": skip,
            f"{date_field}__gte": "2026-11-02",
            f"{date_field}__lte": "2026-11-07"
        }
        r = requests.get(f"{BASE_URL}/activity/{activity_type}/", auth=auth, params=params, timeout=20)
        if r.status_code != 200:
            break
        data = r.json().get("data", [])
        if not data:
            break
        results.extend(data)
        skip += len(data)
        if not r.json().get("has_more"):
            break
    return results

# 1. Notes
notes = search_activities("note")
print(f"Total notas en la semana: {len(notes)}")

# 2. Calls
calls = search_activities("call")
print(f"Total llamadas en la semana: {len(calls)}")

# 3. Emails
emails = search_activities("email")
print(f"Total emails en la semana: {len(emails)}")

# 4. SMS
sms = search_activities("sms")
print(f"Total sms en la semana: {len(sms)}")

# Check for #tkp and #ekp
found_records = []

for n in notes:
    text = (n.get("note") or "").lower()
    user = n.get("user_name")
    created = n.get("date_created")
    lead_id = n.get("lead_id")
    if "#tkp" in text or "tkp" in text.split():
        found_records.append({"type": "Nota", "tag": "#TKP", "user": user, "date": created, "lead_id": lead_id, "text": n.get("note")})
    if "#ekp" in text or "ekp" in text.split():
        found_records.append({"type": "Nota", "tag": "#EKP", "user": user, "date": created, "lead_id": lead_id, "text": n.get("note")})

for c in calls:
    text = (c.get("note") or "").lower()
    user = c.get("user_name")
    created = c.get("date_created")
    lead_id = c.get("lead_id")
    outcome = c.get("outcome_id")
    if "#tkp" in text or "tkp" in text.split():
        found_records.append({"type": "Llamada", "tag": "#TKP", "user": user, "date": created, "lead_id": lead_id, "outcome": outcome, "text": c.get("note")})
    if "#ekp" in text or "ekp" in text.split():
        found_records.append({"type": "Llamada", "tag": "#EKP", "user": user, "date": created, "lead_id": lead_id, "outcome": outcome, "text": c.get("note")})

for e in emails:
    body = (e.get("body_text") or "").lower()
    subject = (e.get("subject") or "").lower()
    text = subject + " " + body
    user = e.get("user_name")
    created = e.get("date_created")
    lead_id = e.get("lead_id")
    if "#tkp" in text:
        found_records.append({"type": "Email", "tag": "#TKP", "user": user, "date": created, "lead_id": lead_id, "text": e.get("subject")})
    if "#ekp" in text:
        found_records.append({"type": "Email", "tag": "#EKP", "user": user, "date": created, "lead_id": lead_id, "text": e.get("subject")})

print(f"\nTotal registros con #TKP o #EKP encontrados en Semana 27: {len(found_records)}")

by_tag = defaultdict(int)
by_user = defaultdict(lambda: defaultdict(int))

for rec in found_records:
    by_tag[rec["tag"]] += 1
    by_user[rec["user"]][rec["tag"]] += 1

print("\n--- RESUMEN POR TAG ---")
for t, cnt in by_tag.items():
    print(f"  {t}: {cnt}")

print("\n--- RESUMEN POR ASESOR ---")
for u, tags in sorted(by_user.items()):
    print(f"  Asesor: {u}")
    for t, cnt in tags.items():
        print(f"    * {t}: {cnt}")

print("\n--- DETALLE DE REGISTROS ENCONTRADOS ---")
for idx, r in enumerate(found_records, 1):
    print(f"{idx}. [{r['type']} - {r['tag']}] {r['date'][:16]} | {r['user']} | Lead: {r['lead_id']}")
    print(f"   Contenido: {r.get('text', '').strip()[:100]}")
