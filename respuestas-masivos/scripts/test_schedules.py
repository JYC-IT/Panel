import os
import requests
from datetime import datetime, time, timedelta, timezone
from collections import defaultdict
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
auth = (os.getenv("CLOSE_CRM_API_KEY"), "")
BASE_URL = "https://api.close.com/api/v1"

AGENT_SCHEDULES = {
    "user_TcBTZtqa1UlOlFQyDlhLJzEywClWo3CTQwXt2OREF2e": {
        "name": "Hernan Bonilla",
        "default": [(time(8, 15), time(12, 0)), (time(13, 0), time(17, 15))],
    },
    "user_QrLrTvgnGNQRS7AMKX2EuCFrZKvqgKmIUloYX1TkRQd": {
        "name": "Mariana Polanco",
        "default": [(time(7, 30), time(12, 0)), (time(13, 0), time(17, 30))],
        "monday": [(time(8, 0), time(12, 0)), (time(13, 0), time(15, 0))]
    },
    "user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D": {
        "name": "Roy Jones",
        "default": [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 30))],
    },
    "user_7cXDrv9AKnoVTSOnXBJo2oYXmUrFRDG40sIYVhmDwHA": {
        "name": "John Abbey",
        "default": [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 0))],
    },
    "user_n1y0yxmKit3rxkJlxhKZXFxEvG4y4G7C4cr4GPypUTx": {
        "name": "Sebastian Jordan",
        "default": [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 0))],
    },
    "user_BZhhrwAL2irTmKaPIntbraEWoINZrcYpKlGUUXsfwcV": {
        "name": "Juan Arango",
        "default": [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 0))],
    },
}

def get_work_ranges(uid, dt):
    cfg = AGENT_SCHEDULES.get(uid, {})
    if dt.weekday() == 0 and "monday" in cfg:
        return cfg["monday"]
    return cfg.get("default", [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 0))])

def get_effective_gap_minutes(dt_end, dt_start, work_ranges):
    if dt_start <= dt_end:
        return 0.0
    day = dt_end.date()
    total_sec = 0.0
    for w_start_t, w_end_t in work_ranges:
        w_start = datetime.combine(day, w_start_t, dt_end.tzinfo)
        w_end = datetime.combine(day, w_end_t, dt_end.tzinfo)
        overlap_start = max(dt_end, w_start)
        overlap_end = min(dt_start, w_end)
        if overlap_end > overlap_start:
            total_sec += (overlap_end - overlap_start).total_seconds()
    return round(total_sec / 60.0, 1)

start_iso = "2026-11-09T00:00:00-05:00"
end_iso = "2026-11-09T23:59:59-05:00"

r = requests.get(f"{BASE_URL}/activity/call/", auth=auth, params={"date_created__gte": start_iso, "date_created__lte": end_iso, "_limit": 100})
calls = r.json().get("data", [])

local_tz = timezone(timedelta(hours=-5))
user_calls = defaultdict(list)
for c in calls:
    uid = c.get("user_id")
    if uid in AGENT_SCHEDULES:
        dt = datetime.fromisoformat(c["date_created"]).astimezone(local_tz)
        user_calls[uid].append((dt, c))

print("=== RESULTADOS PARA NOV 09 (LUNES) ===")
for uid, cfg in AGENT_SCHEDULES.items():
    ucalls = user_calls.get(uid, [])
    ucalls.sort(key=lambda x: x[0])
    if not ucalls:
        print(f"\n{cfg['name']}: Sin llamadas registradas")
        continue

    first_call = ucalls[0][0].strftime("%I:%M %p")
    last_call = ucalls[-1][0].strftime("%I:%M %p")
    print(f"\nAsesor: {cfg['name']} ({len(ucalls)} llamadas)")
    print(f"  First call of the day: {first_call}")
    print(f"  Last call of the day:  {last_call}")

    w_ranges = get_work_ranges(uid, ucalls[0][0])
    
    # Check start of shift delay
    shift_start_dt = datetime.combine(ucalls[0][0].date(), w_ranges[0][0], local_tz)
    first_call_dt = ucalls[0][0]
    if first_call_dt > shift_start_dt:
        init_delay = round((first_call_dt - shift_start_dt).total_seconds() / 60.0, 1)
        if init_delay >= 30:
            print(f"  [ALERTA INICIO TARDIO] Comenzo a las {first_call} (Demora: {init_delay} min tras inicio de turno a las {shift_start_dt.strftime('%I:%M %p')})")

    # Check gaps between calls
    flagged_gaps = []
    for i in range(len(ucalls) - 1):
        dt1, c1 = ucalls[i]
        dt2, c2 = ucalls[i+1]
        dur1 = timedelta(seconds=c1.get("duration") or 0)
        end1 = dt1 + dur1
        
        eff_min = get_effective_gap_minutes(end1, dt2, w_ranges)
        raw_diff_min = round((dt2 - end1).total_seconds() / 60.0, 1)

        if eff_min >= 30.0:
            flagged_gaps.append({
                "eff_min": eff_min,
                "raw_min": raw_diff_min,
                "from": end1.strftime("%I:%M %p"),
                "to": dt2.strftime("%I:%M %p")
            })

    print(f"  Pausas operativas detectadas (descontando almuerzo y fuera de turno): {len(flagged_gaps)}")
    for g in flagged_gaps:
        print(f"    - Pausa efectiva: {g['eff_min']} min (Tiempo reloj: {g['raw_min']} min) de {g['from']} a {g['to']}")
