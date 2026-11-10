import os
import requests
import json
from datetime import datetime, date
from collections import defaultdict
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
auth = (os.getenv("CLOSE_CRM_API_KEY"), "")
BASE_URL = "https://api.close.com/api/v1"

start_date = "2026-11-02"
end_date = "2026-11-06"
start_iso = f"{start_date}T00:00:00-05:00"
end_iso = f"{end_date}T23:59:59-05:00"

COMMERCIAL_USERS = [
    ("user_TcBTZtqa1UlOlFQyDlhLJzEywClWo3CTQwXt2OREF2e", "Hernan Bonilla", "hbonilla@jycexports.com"),
    ("user_7cXDrv9AKnoVTSOnXBJo2oYXmUrFRDG40sIYVhmDwHA", "Juan Abuchaibe", "solutions@jycexports.com"),
    ("user_BZhhrwAL2irTmKaPIntbraEWoINZrcYpKlGUUXsfwcV", "Juan Arango", "plastics@jycmachinery.com"),
    ("user_ESOupvkhojB5X4SkkJ20Nv05U2Klc0ImoRgS4Hwbwms", "Juan Cordoba", "jcordoba@jycexports.com"),
    ("user_piUkoIPqMs7i1Lm3vdc2c2pE3lPjU3cCRvrmvxMonGy", "Julian Prado", "jp@jycmedical.com"),
    ("user_QrLrTvgnGNQRS7AMKX2EuCFrZKvqgKmIUloYX1TkRQd", "Mariana Polanco", "mpolanco@jycexports.com"),
    ("user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D", "Roy Jones", "rjones@jycexports.com"),
    ("user_n1y0yxmKit3rxkJlxhKZXFxEvG4y4G7C4cr4GPypUTx", "Sebastian Jordan", "sjordan@jycmachinery.com"),
]
user_ids = [u[0] for u in COMMERCIAL_USERS]

print("1. Fetching Close activity report...")
payload = {
    "type": "comparison",
    "datetime_range": {"start": start_iso, "end": end_iso},
    "users": user_ids,
    "metrics": [
        "calls.outbound.all.count",
        "calls.inbound.all.count",
        "calls.outbound.all.sum_duration",
        "calls.inbound.all.sum_duration",
        "emails.sent.all.count",
        "outcome.outcome_033WrVULhq3NJjJSQLPgxg.count"
    ]
}
r_act = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=payload, timeout=25)
act_by_user = {row["user_id"]: row for row in r_act.json().get("data", [])}

print("2. Fetching Opportunities created...")
opps_sales = defaultdict(int)
opps_purchase = defaultdict(int)
r_opps = requests.get(f"{BASE_URL}/opportunity/", auth=auth, params={"date_created__gte": start_iso, "date_created__lte": end_iso, "_limit": 100}, timeout=20)
for opp in r_opps.json().get("data", []):
    uid = opp.get("user_id")
    pipe = opp.get("pipeline_id")
    if pipe == "pipe_2g0VCRFwavbPI4whagZads":
        opps_sales[uid] += 1
    elif pipe == "pipe_3BxoKZTZl7XgFpE3YpVQJr":
        opps_purchase[uid] += 1

print("3. Fetching Notes for #EKP / #TKP...")
ekp_by_user = defaultdict(int)
tkp_by_user = defaultdict(int)
r_notes = requests.get(f"{BASE_URL}/activity/note/", auth=auth, params={"date_created__gte": start_iso, "date_created__lte": end_iso, "_limit": 100}, timeout=20)
for n in r_notes.json().get("data", []):
    text = (n.get("note") or "").lower()
    uid = n.get("user_id")
    if "#ekp" in text or "ekp" in text.split():
        ekp_by_user[uid] += 1
    if "#tkp" in text or "tkp" in text.split():
        tkp_by_user[uid] += 1

print("4. Fetching Tasks Set / Done...")
tasks_set = defaultdict(int)
r_tset = requests.get(f"{BASE_URL}/task/", auth=auth, params={"date_created__gte": start_iso, "date_created__lte": end_iso, "_limit": 100}, timeout=20)
for t in r_tset.json().get("data", []):
    tasks_set[t.get("created_by")] += 1

tasks_done = defaultdict(int)
r_tdone = requests.get(f"{BASE_URL}/activity/task_completed/", auth=auth, params={"date_created__gte": start_iso, "date_created__lte": end_iso, "_limit": 100}, timeout=20)
for t in r_tdone.json().get("data", []):
    tasks_done[t.get("user_id") or t.get("created_by")] += 1

print("\n" + "="*125)
print(f"{'Asesor':<18} | {'Out':<4} | {'In':<3} | {'Total':<5} | {'DialTime':<8} | {'KP Call':<7} | {'EKP':<3} | {'TKP':<3} | {'TotKP':<5} | {'Emails':<6} | {'OppS':<4} | {'OppP':<4} | {'OppT':<4} | {'T.Set':<5} | {'T.Done':<6}")
print("="*125)
for uid, name, email in COMMERCIAL_USERS:
    uact = act_by_user.get(uid, {})
    out_c = uact.get("calls.outbound.all.count", 0) or 0
    in_c = uact.get("calls.inbound.all.count", 0) or 0
    tot_c = out_c + in_c
    dur_sec = (uact.get("calls.outbound.all.sum_duration", 0) or 0) + (uact.get("calls.inbound.all.sum_duration", 0) or 0)
    mins = int(dur_sec // 60)
    dial_time_str = f"{mins // 60}h {mins % 60:02d}m"
    live_kp = uact.get("outcome.outcome_033WrVULhq3NJjJSQLPgxg.count", 0) or 0
    ekp = ekp_by_user[uid]
    tkp = tkp_by_user[uid]
    tot_kp = live_kp + ekp + tkp
    emails = uact.get("emails.sent.all.count", 0) or 0
    osales = opps_sales[uid]
    opurch = opps_purchase[uid]
    otot = osales + opurch
    tset = tasks_set[uid]
    tdone = tasks_done[uid]
    print(f"{name:<18} | {out_c:<4} | {in_c:<3} | {tot_c:<5} | {dial_time_str:<8} | {live_kp:<7} | {ekp:<3} | {tkp:<3} | {tot_kp:<5} | {emails:<6} | {osales:<4} | {opurch:<4} | {otot:<4} | {tset:<5} | {tdone:<6}")
