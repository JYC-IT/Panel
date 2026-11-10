"""Servicio para el Panel Comercial de Hernán (KPIs Diarios, KPs, Llamadas, Metas, Horarios y Pipelines).
Procesa en tiempo real desde Close CRM todas las métricas de desempeño de los comerciales autorizados.
"""
import os
import requests
import time
from datetime import datetime, date, timedelta, timezone, time as dt_time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

from connectors import close_crm

BASE_URL = close_crm.BASE_URL
KP_OUTCOME_ID = close_crm.KP_OUTCOME_ID
KP_METRIC_KEY = close_crm.KP_METRIC_KEY

# IDs de los Pipelines oficiales en Close CRM
PIPELINE_SALES_ID = "pipe_2g0VCRFwavbPI4whagZads"      # Sell
PIPELINE_PURCHASE_ID = "pipe_3BxoKZTZl7XgFpE3YpVQJr"   # Purchase

# Metas Diarias Oficiales fijadas por Hernán
DAILY_GOAL_CALLS = 60          # Mínimo 60 llamadas diarias
DAILY_GOAL_TOTAL_KPS = 10      # Mínimo 10 KPs diarios
DAILY_GOAL_CALL_KPS = 5        # La mitad de esos KPs deben ser llamadas (mínimo 5)

# 6 Asesores Comerciales Marcados Oficiales en el Orden Requerido por Hernán
COMMERCIAL_TEAM = [
    {"id": "user_TcBTZtqa1UlOlFQyDlhLJzEywClWo3CTQwXt2OREF2e", "name": "Hernan Bonilla", "email": "hbonilla@jycexports.com"},
    {"id": "user_QrLrTvgnGNQRS7AMKX2EuCFrZKvqgKmIUloYX1TkRQd", "name": "Mariana Polanco", "email": "mpolanco@jycexports.com"},
    {"id": "user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D", "name": "Roy Jones", "email": "rjones@jycexports.com"},
    {"id": "user_7cXDrv9AKnoVTSOnXBJo2oYXmUrFRDG40sIYVhmDwHA", "name": "John Abbey", "email": "solutions@jycexports.com"},
    {"id": "user_n1y0yxmKit3rxkJlxhKZXFxEvG4y4G7C4cr4GPypUTx", "name": "Sebastian Jordan", "email": "sjordan@jycmachinery.com"},
    {"id": "user_BZhhrwAL2irTmKaPIntbraEWoINZrcYpKlGUUXsfwcV", "name": "Juan Arango", "email": "plastics@jycmachinery.com"},
]

COMMERCIAL_MAP = {u["id"]: u for u in COMMERCIAL_TEAM}

# Horarios Oficiales de Trabajo y Descansos de los Comerciales (Zona Horaria Local UTC-5)
# Descansos Oficiales Excluidos Automáticamente:
# 1) Pausa Matutina & Almuerzo continuo: 11:50 AM a 1:00 PM (1h 10m sin marcación)
# 2) Pausa de la Tarde: 2:35 PM a 2:45 PM (10 minutos oficiales)
COMMERCIAL_SCHEDULES = {
    "user_TcBTZtqa1UlOlFQyDlhLJzEywClWo3CTQwXt2OREF2e": {  # Hernan Bonilla
        "name": "Hernan Bonilla",
        "default": [
            (dt_time(8, 15), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(17, 15))
        ],
        "schedule_label": "8:15 AM - 5:15 PM (Alm: 11:50-1:00 | Pausa: 2:35-2:45)"
    },
    "user_QrLrTvgnGNQRS7AMKX2EuCFrZKvqgKmIUloYX1TkRQd": {  # Mariana Polanco
        "name": "Mariana Polanco",
        "default": [
            (dt_time(7, 30), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(17, 30))
        ],
        "monday": [
            (dt_time(8, 0), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(15, 0))
        ],
        "schedule_label": "Mar-Vie: 7:30 - 5:30 (Lun: 8 - 3)"
    },
    "user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D": {  # Roy Jones
        "name": "Roy Jones",
        "default": [
            (dt_time(8, 0), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(17, 30))
        ],
        "schedule_label": "8:00 AM - 5:30 PM (Alm: 11:50-1:00 | Pausa: 2:35-2:45)"
    },
    "user_7cXDrv9AKnoVTSOnXBJo2oYXmUrFRDG40sIYVhmDwHA": {  # John Abbey
        "name": "John Abbey",
        "default": [
            (dt_time(8, 0), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(17, 0))
        ],
        "schedule_label": "8:00 AM - 5:00 PM (Alm: 11:50-1:00 | Pausa: 2:35-2:45)"
    },
    "user_n1y0yxmKit3rxkJlxhKZXFxEvG4y4G7C4cr4GPypUTx": {  # Sebastian Jordan
        "name": "Sebastian Jordan",
        "default": [
            (dt_time(8, 0), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(17, 0))
        ],
        "schedule_label": "8:00 AM - 5:00 PM (Alm: 11:50-1:00 | Pausa: 2:35-2:45)"
    },
    "user_BZhhrwAL2irTmKaPIntbraEWoINZrcYpKlGUUXsfwcV": {  # Juan Arango
        "name": "Juan Arango",
        "default": [
            (dt_time(8, 0), dt_time(11, 50)),
            (dt_time(13, 0), dt_time(14, 35)),
            (dt_time(14, 45), dt_time(17, 0))
        ],
        "schedule_label": "8:00 AM - 5:00 PM (Alm: 11:50-1:00 | Pausa: 2:35-2:45)"
    },
}

_DASHBOARD_CACHE = {}


def _get_auth():
    return close_crm._get_auth()


def calculate_business_days(start_date_str, end_date_str):
    """Calcula la cantidad de días hábiles (lunes a viernes) entre dos fechas YYYY-MM-DD."""
    try:
        d_start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        d_end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        if d_start > d_end:
            d_start, d_end = d_end, d_start
        
        days_count = 0
        cur = d_start
        while cur <= d_end:
            if cur.weekday() < 5:  # 0=Monday ... 4=Friday
                days_count += 1
            cur += timedelta(days=1)
        return max(1, days_count)
    except Exception:
        return 1


def format_duration(seconds):
    """Convierte segundos en formato legible: 'Xh Ym' y 'HH:MM:SS'."""
    sec = int(seconds or 0)
    hours = sec // 3600
    minutes = (sec % 3600) // 60
    remaining_sec = sec % 60
    
    formatted_h_m = f"{hours}h {minutes:02d}m"
    formatted_clock = f"{hours:02d}:{minutes:02d}:{remaining_sec:02d}"
    return {
        "seconds": sec,
        "minutes": round(sec / 60.0, 1),
        "hours": round(sec / 3600.0, 2),
        "human": formatted_h_m,
        "clock": formatted_clock
    }


def get_work_ranges(uid, dt):
    """Retorna los bloques laborales activos (excluyendo pausa/almuerzo 11:50-1:00 y pausa tarde 2:35-2:45) para un asesor según el día."""
    cfg = COMMERCIAL_SCHEDULES.get(uid, {})
    if dt.weekday() == 0 and "monday" in cfg:
        return cfg["monday"]
    return cfg.get("default", [
        (dt_time(8, 0), dt_time(11, 50)),
        (dt_time(13, 0), dt_time(14, 35)),
        (dt_time(14, 45), dt_time(17, 0))
    ])


def get_effective_gap_minutes(dt_end, dt_start, work_ranges):
    """
    Calcula cuántos minutos de [dt_end, dt_start] caen estrictamente dentro del horario laboral,
    descontando automáticamente el almuerzo y pausa matutina (11:50 AM a 1:00 PM),
    la pausa de la tarde (2:35 PM a 2:45 PM) y el tiempo fuera de turno.
    Retorna (minutos_efectivos, minutos_totales_reloj, minutos_descontados).
    """
    if dt_start <= dt_end:
        return 0.0, 0.0, 0.0
    day = dt_end.date()
    total_sec = 0.0
    for w_start_t, w_end_t in work_ranges:
        w_start = datetime.combine(day, w_start_t, dt_end.tzinfo)
        w_end = datetime.combine(day, w_end_t, dt_end.tzinfo)
        overlap_start = max(dt_end, w_start)
        overlap_end = min(dt_start, w_end)
        if overlap_end > overlap_start:
            total_sec += (overlap_end - overlap_start).total_seconds()
    
    eff_min = round(total_sec / 60.0, 1)
    raw_min = round((dt_start - dt_end).total_seconds() / 60.0, 1)
    disc_min = round(max(0.0, raw_min - eff_min), 1)
    return eff_min, raw_min, disc_min


def get_commercial_dashboard_data(start_date=None, end_date=None, force_refresh=False):
    """
    Obtiene todas las métricas para el panel comercial de Hernán:
    - Lista ordenada y exclusiva de los comerciales seleccionados.
    - Llamadas: Total, Salientes, Entrantes, Gross Dial Time, Live KP Talk
    - Horarios de inicio y fin: First Call of the day (Time) y Last Call of the day (Time)
    - Alertas de Inactividad >= 30 min (descontando almuerzo 12-1 y tiempos fuera de turno)
    - KPIs #EKP y #TKP
    - Total KPs (Talked to KP + EKP + TKP)
    - Emails Enviados
    - Oportunidades: Total, Sales Pipeline, Purchase Pipeline
    - Tareas: Set / Done
    - Metas Diarias: 60 llamadas, 10 KPs (mínimo 5 por llamada) y % de cumplimiento.
    """
    auth = _get_auth()
    if not auth:
        return None

    today = date.today()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = today.isoformat()

    cache_key = f"comm_dash_{start_date}_{end_date}"
    now_ts = time.time()
    if not force_refresh and cache_key in _DASHBOARD_CACHE:
        entry = _DASHBOARD_CACHE[cache_key]
        if now_ts < entry["expires_at"]:
            return entry["data"]

    start_iso = f"{start_date}T00:00:00-05:00"
    end_iso = f"{end_date}T23:59:59-05:00"

    business_days = calculate_business_days(start_date, end_date)
    period_target_calls = business_days * DAILY_GOAL_CALLS
    period_target_kps = business_days * DAILY_GOAL_TOTAL_KPS
    period_target_call_kps = business_days * DAILY_GOAL_CALL_KPS

    user_ids = [u["id"] for u in COMMERCIAL_TEAM]

    # --- 1. Reporte de Actividad Close CRM (Comparison) ---
    def fetch_activity_report():
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
                KP_METRIC_KEY
            ]
        }
        try:
            r = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=payload, timeout=25)
            if r.status_code == 200:
                return {row["user_id"]: row for row in r.json().get("data", [])}
        except Exception as e:
            print(f"Error fetching activity report: {e}")
        return {}

    # --- 2. Oportunidades Creadas (Sales vs Purchase) ---
    def fetch_opportunities():
        opps_data = {
            "sales_by_user": defaultdict(int),
            "purchase_by_user": defaultdict(int),
            "total_by_user": defaultdict(int),
            "list": []
        }
        try:
            skip = 0
            while True:
                r = requests.get(
                    f"{BASE_URL}/opportunity/",
                    auth=auth,
                    params={
                        "date_created__gte": start_iso,
                        "date_created__lte": end_iso,
                        "_limit": 100,
                        "_skip": skip
                    },
                    timeout=20
                )
                if r.status_code != 200:
                    break
                data = r.json().get("data", [])
                for opp in data:
                    uid = opp.get("user_id")
                    if uid not in COMMERCIAL_MAP:
                        continue
                    pipe_id = opp.get("pipeline_id")
                    val = (opp.get("value") or 0) / 100.0
                    pipe_type = "Sales" if pipe_id == PIPELINE_SALES_ID else ("Purchase" if pipe_id == PIPELINE_PURCHASE_ID else "Otro")
                    
                    if pipe_id == PIPELINE_SALES_ID:
                        opps_data["sales_by_user"][uid] += 1
                    elif pipe_id == PIPELINE_PURCHASE_ID:
                        opps_data["purchase_by_user"][uid] += 1
                    opps_data["total_by_user"][uid] += 1

                    opps_data["list"].append({
                        "id": opp.get("id"),
                        "user_id": uid,
                        "user_name": opp.get("user_name"),
                        "lead_name": opp.get("lead_name") or "Sin Empresa",
                        "pipeline_name": opp.get("pipeline_name") or pipe_type,
                        "pipeline_type": pipe_type,
                        "status_label": opp.get("status_label") or "Activo",
                        "value": val,
                        "date_created": opp.get("date_created")
                    })
                if not r.json().get("has_more") or len(data) < 100:
                    break
                skip += len(data)
        except Exception as e:
            print(f"Error fetching opps: {e}")
        return opps_data

    # --- 3. Notas con #EKP y #TKP ---
    def fetch_notes_tags():
        tags_data = {
            "ekp_by_user": defaultdict(int),
            "tkp_by_user": defaultdict(int),
            "records": []
        }
        try:
            skip = 0
            while True:
                r = requests.get(
                    f"{BASE_URL}/activity/note/",
                    auth=auth,
                    params={
                        "date_created__gte": start_iso,
                        "date_created__lte": end_iso,
                        "_limit": 100,
                        "_skip": skip
                    },
                    timeout=20
                )
                if r.status_code != 200:
                    break
                notes = r.json().get("data", [])
                for n in notes:
                    uid = n.get("user_id")
                    if uid not in COMMERCIAL_MAP:
                        continue
                    text = (n.get("note") or "").strip()
                    text_lower = text.lower()
                    
                    is_ekp = "#ekp" in text_lower or "ekp" in text_lower.split()
                    is_tkp = "#tkp" in text_lower or "tkp" in text_lower.split()

                    if is_ekp:
                        tags_data["ekp_by_user"][uid] += 1
                        tags_data["records"].append({
                            "type": "EKP",
                            "user_id": uid,
                            "user_name": n.get("user_name"),
                            "date": n.get("date_created"),
                            "lead_id": n.get("lead_id"),
                            "lead_name": n.get("lead_name") or "",
                            "text": text
                        })
                    if is_tkp:
                        tags_data["tkp_by_user"][uid] += 1
                        tags_data["records"].append({
                            "type": "TKP",
                            "user_id": uid,
                            "user_name": n.get("user_name"),
                            "date": n.get("date_created"),
                            "lead_id": n.get("lead_id"),
                            "lead_name": n.get("lead_name") or "",
                            "text": text
                        })
                if not r.json().get("has_more") or len(notes) < 100:
                    break
                skip += len(notes)
        except Exception as e:
            print(f"Error fetching notes tags: {e}")
        return tags_data

    # --- 4. Tareas Set (creadas en el periodo) ---
    def fetch_tasks_set():
        tasks_by_user = defaultdict(int)
        try:
            skip = 0
            while True:
                r = requests.get(
                    f"{BASE_URL}/task/",
                    auth=auth,
                    params={
                        "date_created__gte": start_iso,
                        "date_created__lte": end_iso,
                        "_limit": 100,
                        "_skip": skip
                    },
                    timeout=20
                )
                if r.status_code != 200:
                    break
                tasks = r.json().get("data", [])
                for t in tasks:
                    uid = t.get("created_by")
                    if uid in COMMERCIAL_MAP:
                        tasks_by_user[uid] += 1
                if not r.json().get("has_more") or len(tasks) < 100:
                    break
                skip += len(tasks)
        except Exception as e:
            print(f"Error fetching tasks set: {e}")
        return tasks_by_user

    # --- 5. Tareas Done (completadas en el periodo) ---
    def fetch_tasks_done():
        done_by_user = defaultdict(int)
        try:
            skip = 0
            while True:
                r = requests.get(
                    f"{BASE_URL}/activity/task_completed/",
                    auth=auth,
                    params={
                        "date_created__gte": start_iso,
                        "date_created__lte": end_iso,
                        "_limit": 100,
                        "_skip": skip
                    },
                    timeout=20
                )
                if r.status_code != 200:
                    break
                done_list = r.json().get("data", [])
                for item in done_list:
                    uid = item.get("user_id") or item.get("created_by")
                    if uid in COMMERCIAL_MAP:
                        done_by_user[uid] += 1
                if not r.json().get("has_more") or len(done_list) < 100:
                    break
                skip += len(done_list)
        except Exception as e:
            print(f"Error fetching tasks done: {e}")
        return done_by_user

    # --- 6. Análisis de Inactividad entre Llamadas & Horas Primera/Última Llamada ---
    def fetch_call_inactivity():
        user_day_calls = defaultdict(list)
        all_gaps = []
        gaps_by_user = defaultdict(list)
        first_last_by_user = defaultdict(dict)

        local_tz = timezone(timedelta(hours=-5))

        try:
            skip = 0
            while True:
                r = requests.get(
                    f"{BASE_URL}/activity/call/",
                    auth=auth,
                    params={
                        "date_created__gte": start_iso,
                        "date_created__lte": end_iso,
                        "_limit": 100,
                        "_skip": skip
                    },
                    timeout=25
                )
                if r.status_code != 200:
                    break
                data = r.json().get("data", [])
                for c in data:
                    uid = c.get("user_id")
                    raw_date = c.get("date_created")
                    if not uid or not raw_date or uid not in COMMERCIAL_MAP:
                        continue
                    try:
                        clean_dt = raw_date.replace("Z", "+00:00")
                        dt_utc = datetime.fromisoformat(clean_dt)
                        dt_local = dt_utc.astimezone(local_tz)
                        day_str = dt_local.strftime("%Y-%m-%d")
                        user_day_calls[(uid, day_str)].append((dt_local, c))
                    except Exception:
                        pass
                if not r.json().get("has_more") or len(data) < 100:
                    break
                skip += len(data)

            # Analizar intervalos entre llamadas para cada asesor por cada día laboral
            for (uid, day_str), ucalls in user_day_calls.items():
                ucalls.sort(key=lambda x: x[0])
                if not ucalls:
                    continue

                w_ranges = get_work_ranges(uid, ucalls[0][0])
                first_dt = ucalls[0][0]
                last_dt = ucalls[-1][0]

                # Guardar First y Last call de cada día
                if uid not in first_last_by_user or day_str >= first_last_by_user[uid].get("day", ""):
                    first_last_by_user[uid] = {
                        "day": day_str,
                        "first_call_time": first_dt.strftime("%I:%M %p"),
                        "last_call_time": last_dt.strftime("%I:%M %p"),
                        "first_dt": first_dt,
                        "last_dt": last_dt
                    }

                # A. Alerta de Demora en Inicio de Turno (si primera llamada es >= 30 min tras hora de entrada)
                shift_start_t = w_ranges[0][0]
                shift_start_dt = datetime.combine(first_dt.date(), shift_start_t, local_tz)
                if first_dt > shift_start_dt:
                    init_delay_min = round((first_dt - shift_start_dt).total_seconds() / 60.0, 1)
                    if init_delay_min >= 30.0:
                        u_name = ucalls[0][1].get("user_name") or COMMERCIAL_MAP.get(uid, {}).get("name", "Asesor")
                        raw_human = f"{int(init_delay_min // 60)}h {int(init_delay_min % 60):02d}m" if init_delay_min >= 60 else f"{int(init_delay_min)} min"
                        init_gap = {
                            "user_id": uid,
                            "user_name": u_name,
                            "date": day_str,
                            "gap_minutes": init_delay_min,
                            "raw_minutes": init_delay_min,
                            "raw_human": raw_human,
                            "discounted_minutes": 0.0,
                            "discounted_human": "",
                            "gap_human": raw_human,
                            "from_time": shift_start_dt.strftime("%I:%M %p"),
                            "to_time": first_dt.strftime("%I:%M %p"),
                            "pause_type": "Inicio Tardío" if init_delay_min < 60 else "Inicio Muy Tardío (>1h)",
                            "severity": "Critical" if init_delay_min >= 60 else "Warning",
                            "is_lunch": False,
                            "phone_before": "Inicio de Turno",
                            "phone_after": ucalls[0][1].get("remote_phone_formatted") or ucalls[0][1].get("remote_phone") or "N/A",
                            "lead_before": f"Turno programado {shift_start_dt.strftime('%I:%M %p')}",
                            "lead_after": ucalls[0][1].get("lead_name") or ucalls[0][1].get("lead_id") or "Primer Lead",
                            "lead_id_before": None,
                            "lead_id_after": ucalls[0][1].get("lead_id"),
                        }
                        gaps_by_user[uid].append(init_gap)
                        all_gaps.append(init_gap)

                # B. Intervalos entre llamadas a lo largo del día
                for i in range(len(ucalls) - 1):
                    dt1, c1 = ucalls[i]
                    dt2, c2 = ucalls[i+1]

                    dur1 = timedelta(seconds=c1.get("duration") or 0)
                    end1 = dt1 + dur1

                    # Excluir cualquier intervalo que cruce la ventana de almuerzo (11:50 AM a 1:00 PM).
                    # El almuerzo (pausa matutina 11:50-12:00 + almuerzo 12:00-13:00) es el corte natural de la jornada.
                    # El control de a qué hora cortó antes del almuerzo y a qué hora retomó en la tarde
                    # se audita y monitorea exclusivamente en el "Control de Jornada (Primera y Última Llamada)"
                    # para evitar generar alertas artificiales por el receso del almuerzo.
                    lunch_start_dt = datetime.combine(end1.date(), dt_time(11, 50), local_tz)
                    lunch_end_dt = datetime.combine(end1.date(), dt_time(13, 0), local_tz)
                    if end1 < lunch_end_dt and dt2 > lunch_start_dt:
                        continue

                    eff_minutes, raw_diff_minutes, disc_minutes = get_effective_gap_minutes(end1, dt2, w_ranges)

                    if eff_minutes >= 30.0:
                        severity = "Critical" if eff_minutes >= 60.0 else "Warning"
                        pause_type = "Crítica (>1h)" if eff_minutes >= 60.0 else "Pausa Larga (>30m)"

                        disc_human = f"-{int(disc_minutes // 60)}h {int(disc_minutes % 60):02d}m" if disc_minutes >= 60 else f"-{int(disc_minutes)}m" if disc_minutes > 0 else ""
                        raw_human = f"{int(raw_diff_minutes // 60)}h {int(raw_diff_minutes % 60):02d}m" if raw_diff_minutes >= 60 else f"{int(raw_diff_minutes)} min"

                        u_name = c1.get("user_name") or COMMERCIAL_MAP.get(uid, {}).get("name", "Asesor")
                        gap_item = {
                            "user_id": uid,
                            "user_name": u_name,
                            "date": day_str,
                            "gap_minutes": eff_minutes,
                            "raw_minutes": raw_diff_minutes,
                            "raw_human": raw_human,
                            "discounted_minutes": disc_minutes,
                            "discounted_human": disc_human,
                            "gap_human": f"{int(eff_minutes // 60)}h {int(eff_minutes % 60):02d}m" if eff_minutes >= 60 else f"{int(eff_minutes)} min",
                            "from_time": end1.strftime("%I:%M %p"),
                            "to_time": dt2.strftime("%I:%M %p"),
                            "pause_type": pause_type,
                            "severity": severity,
                            "is_lunch": False,
                            "phone_before": c1.get("remote_phone_formatted") or c1.get("remote_phone") or "N/A",
                            "phone_after": c2.get("remote_phone_formatted") or c2.get("remote_phone") or "N/A",
                            "lead_before": c1.get("lead_name") or c1.get("lead_id") or "Sin Lead",
                            "lead_after": c2.get("lead_name") or c2.get("lead_id") or "Sin Lead",
                            "lead_id_before": c1.get("lead_id"),
                            "lead_id_after": c2.get("lead_id"),
                        }
                        gaps_by_user[uid].append(gap_item)
                        all_gaps.append(gap_item)

            # C. Cálculo de Checkpoints de Jornada: 1ra AM, Última AM, 1ra PM, Última PM
            all_daily_records = []
            user_latest_checkpoints = {}

            all_days = sorted(list(set(k[1] for k in user_day_calls.keys())), reverse=True)
            if not all_days:
                all_days = [end_date]

            now_local = datetime.now(local_tz)
            today_str = now_local.strftime("%Y-%m-%d")

            for day_str in all_days:
                try:
                    day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
                except Exception:
                    continue

                for agent in COMMERCIAL_TEAM:
                    uid = agent["id"]
                    u_name = agent["name"]
                    ucalls = sorted(user_day_calls.get((uid, day_str), []), key=lambda x: x[0])

                    dummy_dt = datetime.combine(day_date, dt_time(10, 0), local_tz)
                    w_ranges = get_work_ranges(uid, dummy_dt)
                    shift_start_t = w_ranges[0][0]
                    lunch_start_t = dt_time(11, 50)
                    lunch_end_t = dt_time(13, 0)
                    shift_end_t = w_ranges[-1][1]

                    am_calls = [x for x in ucalls if x[0].time() < lunch_end_t]
                    pm_calls = [x for x in ucalls if x[0].time() >= lunch_end_t]

                    # 1. Primera Llamada de la Mañana (Entrada)
                    entry_dt = datetime.combine(day_date, shift_start_t, local_tz)
                    if am_calls:
                        f_am_dt = am_calls[0][0]
                        f_am_time = f_am_dt.strftime("%I:%M %p")
                        diff_m = int((f_am_dt - entry_dt).total_seconds() / 60)
                        if diff_m <= 10:
                            f_am_status = "ok"
                            f_am_label = "A tiempo"
                            f_am_color = "#059669"
                        elif diff_m <= 30:
                            f_am_status = "warning"
                            f_am_label = f"+{diff_m}m tarde"
                            f_am_color = "#d97706"
                        else:
                            f_am_status = "danger"
                            f_am_label = f"+{diff_m // 60}h {diff_m % 60:02d}m tarde" if diff_m >= 60 else f"+{diff_m}m tarde"
                            f_am_color = "#dc2626"
                        f_am_info = {"time": f_am_time, "label": f_am_label, "status": f_am_status, "color": f_am_color, "diff_m": diff_m}
                    else:
                        f_am_info = {"time": "-", "label": "Sin llamadas AM", "status": "danger", "color": "#94a3b8", "diff_m": 0}

                    # 2. Última Llamada de la Mañana (Almuerzo / Pausa 11:50)
                    lunch_dt = datetime.combine(day_date, lunch_start_t, local_tz)
                    if am_calls:
                        l_am_dt = am_calls[-1][0]
                        l_am_time = l_am_dt.strftime("%I:%M %p")
                        if l_am_dt >= lunch_dt - timedelta(minutes=15):
                            l_am_status = "ok"
                            l_am_label = "Hasta almuerzo"
                            l_am_color = "#059669"
                            early_m = 0
                        else:
                            early_m = int((lunch_dt - l_am_dt).total_seconds() / 60)
                            if early_m <= 30:
                                l_am_status = "warning"
                                l_am_label = f"Cortó {early_m}m antes"
                                l_am_color = "#d97706"
                            else:
                                l_am_status = "danger"
                                l_am_label = f"Cortó {early_m // 60}h {early_m % 60:02d}m antes" if early_m >= 60 else f"Cortó {early_m}m antes"
                                l_am_color = "#dc2626"
                        l_am_info = {"time": l_am_time, "label": l_am_label, "status": l_am_status, "color": l_am_color, "diff_m": early_m}
                    else:
                        l_am_info = {"time": "-", "label": "Sin llamadas AM", "status": "danger", "color": "#94a3b8", "diff_m": 0}

                    # 3. Primera Llamada de la Tarde (Retorno Almuerzo 1:00 PM)
                    ret_dt = datetime.combine(day_date, lunch_end_t, local_tz)
                    if pm_calls:
                        f_pm_dt = pm_calls[0][0]
                        f_pm_time = f_pm_dt.strftime("%I:%M %p")
                        diff_pm = int((f_pm_dt - ret_dt).total_seconds() / 60)
                        if diff_pm <= 15:
                            f_pm_status = "ok"
                            f_pm_label = "A tiempo"
                            f_pm_color = "#059669"
                        elif diff_pm <= 30:
                            f_pm_status = "warning"
                            f_pm_label = f"+{diff_pm}m tarde"
                            f_pm_color = "#d97706"
                        else:
                            f_pm_status = "danger"
                            f_pm_label = f"+{diff_pm // 60}h {diff_pm % 60:02d}m tarde" if diff_pm >= 60 else f"+{diff_pm}m tarde"
                            f_pm_color = "#dc2626"
                        f_pm_info = {"time": f_pm_time, "label": f_pm_label, "status": f_pm_status, "color": f_pm_color, "diff_m": diff_pm}
                    else:
                        if day_str == today_str and now_local.time() < dt_time(13, 30):
                            f_pm_info = {"time": "-", "label": "En curso", "status": "neutral", "color": "#64748b", "diff_m": 0}
                        else:
                            f_pm_info = {"time": "-", "label": "Sin llamadas PM", "status": "danger", "color": "#94a3b8", "diff_m": 0}

                    # 4. Última Llamada de la Tarde (Salida / Cierre)
                    exit_dt = datetime.combine(day_date, shift_end_t, local_tz)
                    if pm_calls:
                        l_pm_dt = pm_calls[-1][0]
                        l_pm_time = l_pm_dt.strftime("%I:%M %p")
                        if l_pm_dt >= exit_dt - timedelta(minutes=15):
                            l_pm_status = "ok"
                            l_pm_label = "Salida normal"
                            l_pm_color = "#059669"
                            early_exit = 0
                        else:
                            early_exit = int((exit_dt - l_pm_dt).total_seconds() / 60)
                            if early_exit <= 30:
                                l_pm_status = "warning"
                                l_pm_label = f"Cortó {early_exit}m antes"
                                l_pm_color = "#d97706"
                            else:
                                l_pm_status = "danger"
                                l_pm_label = f"Cortó {early_exit // 60}h {early_exit % 60:02d}m antes" if early_exit >= 60 else f"Cortó {early_exit}m antes"
                                l_pm_color = "#dc2626"
                        l_pm_info = {"time": l_pm_time, "label": l_pm_label, "status": l_pm_status, "color": l_pm_color, "diff_m": early_exit}
                    else:
                        if day_str == today_str and now_local.time() < shift_end_t:
                            l_pm_info = {"time": "-", "label": "En curso", "status": "neutral", "color": "#64748b", "diff_m": 0}
                        else:
                            l_pm_info = {"time": "-", "label": "Sin llamadas PM", "status": "danger", "color": "#94a3b8", "diff_m": 0}

                    record = {
                        "user_id": uid,
                        "user_name": u_name,
                        "date": day_str,
                        "schedule_label": COMMERCIAL_SCHEDULES.get(uid, {}).get("schedule_label", "8:00 AM - 5:00 PM"),
                        "scheduled_entry": shift_start_t.strftime("%I:%M %p"),
                        "scheduled_lunch": "11:50 AM - 1:00 PM",
                        "scheduled_exit": shift_end_t.strftime("%I:%M %p"),
                        "calls_am": len(am_calls),
                        "calls_pm": len(pm_calls),
                        "calls_total": len(ucalls),
                        "first_am": f_am_info,
                        "last_am": l_am_info,
                        "first_pm": f_pm_info,
                        "last_pm": l_pm_info,
                    }
                    all_daily_records.append(record)

                    if uid not in user_latest_checkpoints or day_str >= user_latest_checkpoints[uid]["date"]:
                        user_latest_checkpoints[uid] = record
        except Exception as e:
            print(f"Error analyzing discipline checkpoints: {e}")

        all_gaps.sort(key=lambda x: (x["date"], x["gap_minutes"]), reverse=True)
        order_map = {agent["id"]: i for i, agent in enumerate(COMMERCIAL_TEAM)}
        all_daily_records.sort(key=lambda x: (x["date"], -order_map.get(x["user_id"], 99)), reverse=True)

        return {
            "by_user": gaps_by_user,
            "all_gaps": all_gaps,
            "first_last": first_last_by_user,
            "daily_records": all_daily_records,
            "latest_by_user": user_latest_checkpoints
        }

    # Ejecución paralela
    with ThreadPoolExecutor(max_workers=6) as executor:
        f_act = executor.submit(fetch_activity_report)
        f_opps = executor.submit(fetch_opportunities)
        f_notes = executor.submit(fetch_notes_tags)
        f_tset = executor.submit(fetch_tasks_set)
        f_tdone = executor.submit(fetch_tasks_done)
        f_gaps = executor.submit(fetch_call_inactivity)

        activity_report = f_act.result()
        opps_data = f_opps.result()
        notes_tags = f_notes.result()
        tasks_set = f_tset.result()
        tasks_done = f_tdone.result()
        call_gaps = f_gaps.result()

    # --- Consolidación por Comercial en el Orden Estricto Requerido ---
    commercial_rows = []
    tot_out_calls = 0
    tot_in_calls = 0
    tot_calls = 0
    tot_dur_sec = 0
    tot_live_kps = 0
    tot_ekp = 0
    tot_tkp = 0
    tot_all_kps = 0
    tot_emails = 0
    tot_opps_sales = 0
    tot_opps_purch = 0
    tot_opps = 0
    tot_tset = 0
    tot_tdone = 0

    for agent in COMMERCIAL_TEAM:
        uid = agent["id"]
        uact = activity_report.get(uid, {})

        out_c = uact.get("calls.outbound.all.count", 0) or 0
        in_c = uact.get("calls.inbound.all.count", 0) or 0
        c_total = out_c + in_c

        dur_out = uact.get("calls.outbound.all.sum_duration", 0) or 0
        dur_in = uact.get("calls.inbound.all.sum_duration", 0) or 0
        dur_total_sec = dur_out + dur_in
        dur_info = format_duration(dur_total_sec)

        live_kp = uact.get(KP_METRIC_KEY, 0) or 0
        ekp = notes_tags["ekp_by_user"][uid]
        tkp = notes_tags["tkp_by_user"][uid]
        all_kps = live_kp + ekp + tkp

        emails_sent = uact.get("emails.sent.all.count", 0) or 0

        op_sales = opps_data["sales_by_user"][uid]
        op_purch = opps_data["purchase_by_user"][uid]
        op_total = op_sales + op_purch

        t_set = tasks_set[uid]
        t_done = tasks_done[uid]

        # Horas primera y última llamada
        fl_info = call_gaps["first_last"].get(uid, {})
        first_call_time = fl_info.get("first_call_time", "-")
        last_call_time = fl_info.get("last_call_time", "-")

        # Inactividad entre llamadas (descontando almuerzo y fuera de horario)
        user_gaps = call_gaps["by_user"].get(uid, [])
        gaps_count = len(user_gaps)
        gaps_total_min = round(sum(g["gap_minutes"] for g in user_gaps), 1)
        max_gap_min = max([g["gap_minutes"] for g in user_gaps], default=0)
        max_gap_human = f"{int(max_gap_min // 60)}h {int(max_gap_min % 60):02d}m" if max_gap_min >= 60 else f"{int(max_gap_min)} min" if max_gap_min > 0 else "-"

        # Promedios diarios
        avg_calls_day = round(c_total / business_days, 1)
        avg_kps_day = round(all_kps / business_days, 1)
        avg_call_kps_day = round(live_kp / business_days, 1)

        # Cumplimiento contra metas del periodo
        calls_pct = round(100.0 * c_total / period_target_calls, 1) if period_target_calls else 0.0
        kps_pct = round(100.0 * all_kps / period_target_kps, 1) if period_target_kps else 0.0
        call_kps_pct = round(100.0 * live_kp / period_target_call_kps, 1) if period_target_call_kps else 0.0

        met_calls = c_total >= period_target_calls
        met_kps = all_kps >= period_target_kps
        met_call_kps = live_kp >= period_target_call_kps

        # Estado global
        if met_calls and met_kps and met_call_kps:
            status_goal = "Cumple Todo"
            status_class = "ok"
        elif met_calls or met_kps:
            status_goal = "Parcial"
            status_class = "warning"
        else:
            status_goal = "Bajo Meta"
            status_class = "danger"

        # Efectividad de llamada (Live KP / Llamadas Totales)
        eff_rate = round(100.0 * live_kp / c_total, 2) if c_total else 0.0

        # Totales acumulados equipo
        tot_out_calls += out_c
        tot_in_calls += in_c
        tot_calls += c_total
        tot_dur_sec += dur_total_sec
        tot_live_kps += live_kp
        tot_ekp += ekp
        tot_tkp += tkp
        tot_all_kps += all_kps
        tot_emails += emails_sent
        tot_opps_sales += op_sales
        tot_opps_purch += op_purch
        tot_opps += op_total
        tot_tset += t_set
        tot_tdone += t_done

        commercial_rows.append({
            "id": uid,
            "name": agent["name"],
            "email": agent["email"],
            "schedule_label": COMMERCIAL_SCHEDULES.get(uid, {}).get("schedule_label", "8:00 AM - 5:00 PM"),
            # Horarios de llamada y Checkpoints Mañana / Tarde
            "first_call_time": first_call_time,
            "last_call_time": last_call_time,
            "checkpoints": call_gaps.get("latest_by_user", {}).get(uid, {}),
            # Llamadas
            "calls_out": out_c,
            "calls_in": in_c,
            "calls_total": c_total,
            "gross_dial_time": dur_info,
            "live_kp": live_kp,
            # Inactividad entre llamadas
            "inactivity_count": gaps_count,
            "inactivity_total_min": gaps_total_min,
            "inactivity_max_human": max_gap_human,
            "inactivity_gaps": user_gaps,
            # KPIs Hashtags
            "ekp": ekp,
            "tkp": tkp,
            "total_kps": all_kps,
            "effectiveness": eff_rate,
            # Emails
            "emails_sent": emails_sent,
            # Oportunidades
            "opps_sales": op_sales,
            "opps_purchase": op_purch,
            "opps_total": op_total,
            # Tareas
            "tasks_set": t_set,
            "tasks_done": t_done,
            # Promedios diarios
            "avg_calls_day": avg_calls_day,
            "avg_kps_day": avg_kps_day,
            "avg_call_kps_day": avg_call_kps_day,
            # Porcentajes de meta
            "calls_pct": calls_pct,
            "kps_pct": kps_pct,
            "call_kps_pct": call_kps_pct,
            "met_calls": met_calls,
            "met_kps": met_kps,
            "met_call_kps": met_call_kps,
            "status_goal": status_goal,
            "status_class": status_class,
        })

    # Mantenemos el orden predeterminado estricto de COMMERCIAL_TEAM solicitado por Hernán

    team_summary = {
        "agents_count": len(commercial_rows),
        "business_days": business_days,
        "daily_goal_calls": DAILY_GOAL_CALLS,
        "daily_goal_total_kps": DAILY_GOAL_TOTAL_KPS,
        "daily_goal_call_kps": DAILY_GOAL_CALL_KPS,
        "period_target_calls_per_agent": period_target_calls,
        "period_target_kps_per_agent": period_target_kps,
        "period_target_call_kps_per_agent": period_target_call_kps,
        # Totales equipo
        "total_out_calls": tot_out_calls,
        "total_in_calls": tot_in_calls,
        "total_calls": tot_calls,
        "gross_dial_time": format_duration(tot_dur_sec),
        "total_live_kps": tot_live_kps,
        "total_ekp": tot_ekp,
        "total_tkp": tot_tkp,
        "total_all_kps": tot_all_kps,
        "total_emails": tot_emails,
        "total_opps_sales": tot_opps_sales,
        "total_opps_purchase": tot_opps_purch,
        "total_opps": tot_opps,
        "total_tasks_set": tot_tset,
        "total_tasks_done": tot_tdone,
        "team_effectiveness": round(100.0 * tot_live_kps / tot_calls, 2) if tot_calls else 0.0,
        # Inactividad / Alertas de Pausas > 30 min (operativas sin almuerzo)
        "total_inactivity_alerts": len(call_gaps["all_gaps"]),
        "total_critical_alerts": len([g for g in call_gaps["all_gaps"] if g["severity"] == "Critical"]),
    }

    result = {
        "start_date": start_date,
        "end_date": end_date,
        "business_days": business_days,
        "commercials": commercial_rows,
        "summary": team_summary,
        "tagged_records": notes_tags["records"],
        "opportunities_list": opps_data["list"],
        "inactivity_records": call_gaps["all_gaps"],
        "discipline_records": call_gaps.get("daily_records", []),
    }

    _DASHBOARD_CACHE[cache_key] = {
        "data": result,
        "expires_at": time.time() + 120  # 2 minutos de cache
    }

    return result
