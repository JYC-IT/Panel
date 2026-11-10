import os
import sys
import requests
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
api_key = os.getenv("CLOSE_CRM_API_KEY")
auth = (api_key, "")

BASE_URL = "https://api.close.com/api/v1"

print("=== BUSCANDO #tkp Y #ekp EN CLOSE CRM ===")

# 1. Búsqueda en Lead Search
for query_term in ["#tkp", "#ekp", "tkp", "ekp"]:
    try:
        r = requests.get(f"{BASE_URL}/lead/", auth=auth, params={"query": query_term, "_limit": 20}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            total_results = data.get("total_results", len(data.get("data", [])))
            print(f"\n[LEAD QUERY] '{query_term}': Total encontrados = {total_results}")
            for lead in data.get("data", [])[:5]:
                print(f"  - Lead: {lead.get('display_name')} (ID: {lead.get('id')})")
        else:
            print(f"[LEAD QUERY] '{query_term}' status code: {r.status_code}")
    except Exception as e:
        print(f"Error buscando '{query_term}' en leads: {e}")

# 2. Búsqueda en Actividades de Notas (Activity Notes)
print("\n--- REVISANDO ACTIVIDADES DE NOTAS (Activity Note) ---")
try:
    r = requests.get(f"{BASE_URL}/activity/note/", auth=auth, params={"_limit": 100}, timeout=15)
    if r.status_code == 200:
        notes = r.json().get("data", [])
        print(f"Muestra de últimas 100 notas descargadas.")
        for tag in ["#tkp", "#ekp", "tkp", "ekp"]:
            matches = [n for n in notes if tag in (n.get("note") or "").lower()]
            print(f"  Notas con '{tag}': {len(matches)}")
            for m in matches:
                print(f"    * [{m.get('date_created')}] Asesor: {m.get('user_name')} | Texto: {m.get('note').strip()[:80]}")
except Exception as e:
    print(f"Error en notas: {e}")

# 3. Búsqueda en Actividades de Llamadas (Activity Calls) - campo note
print("\n--- REVISANDO NOTAS EN LLAMADAS RECIENTES (Activity Call) ---")
try:
    r = requests.get(f"{BASE_URL}/activity/call/", auth=auth, params={"_limit": 200, "date_created__gte": "2026-11-02"}, timeout=20)
    if r.status_code == 200:
        calls = r.json().get("data", [])
        print(f"Llamadas obtenidas desde Nov 02: {len(calls)}")
        for tag in ["#tkp", "#ekp"]:
            matches = [c for c in calls if tag in (c.get("note") or "").lower()]
            print(f"  Llamadas con '{tag}' en la nota: {len(matches)}")
            for m in matches:
                print(f"    * [{m.get('date_created')}] Asesor: {m.get('user_name')} | Outcome: {m.get('outcome_id')} | Nota: {m.get('note').strip()[:80]}")
except Exception as e:
    print(f"Error en llamadas: {e}")
