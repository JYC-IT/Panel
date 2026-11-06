"""Servicio de consultas analíticas avanzadas a Close CRM (Solo Lectura)
para informes de Rapport y Pipeline Management por asesor comercial.
"""
import os
import requests
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

from connectors import close_crm

BASE_URL = close_crm.BASE_URL


def _get_auth():
    return close_crm._get_auth()


def is_available():
    return close_crm.is_available()


_PERF_CACHE = {}


def get_performance_report(start_date=None, end_date=None, force_refresh=False):
    """
    Obtiene reporte completo de Rapport y Pipeline Management para los asesores comerciales.
    Rango por defecto: últimos 7 días. Con cache de memoria (3 min) para carga instantánea.
    """
    import time
    today = date.today()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today - timedelta(days=7)).isoformat()

    cache_key = f"{start_date}_{end_date}"
    now = time.time()
    if not force_refresh and cache_key in _PERF_CACHE:
        entry = _PERF_CACHE[cache_key]
        if now < entry["expires_at"]:
            return entry["data"]

    auth = _get_auth()
    if not auth:
        return None

    raw_users = close_crm.list_users()
    # Asegurar exclusión estricta de comerciales desvinculados (Roy Jones y Carlos Córdoba)
    users = [
        u for u in raw_users
        if "roy" not in (u.get("name") or "").lower()
        and "rjones" not in (u.get("email") or "").lower()
        and "carlos" not in (u.get("name") or "").lower()
        and "ccordoba" not in (u.get("email") or "").lower()
    ]
    designated_users = [u for u in users if u.get("is_designated")]
    user_map = {u["id"]: u for u in designated_users}
    user_ids = list(user_map.keys())

    if not user_ids:
        # Fallback a todos los usuarios si ninguno está explícitamente marcado
        user_map = {u["id"]: u for u in users}
        user_ids = list(user_map.keys())[:10]

    # 1. Métricas de Actividad (Rapport) via Activity Report API
    metrics_to_fetch = [
        "calls.outbound.all.count",
        "calls.outbound.all.avg_duration",
        "calls.outbound.all.sum_duration",
        "emails.sent.manual.count",
        "emails.sent.manual_with_reply.count",
        "sms.sent.all.count",
        "sms.received.all.count",
        "leads.contacted.all.count",
        "meetings.completed.count",
        close_crm.KP_METRIC_KEY
    ]

    payload = {
        "type": "comparison",
        "datetime_range": {
            "start": f"{start_date}T00:00:00-05:00",
            "end": f"{end_date}T23:59:59-05:00"
        },
        "users": user_ids,
        "metrics": metrics_to_fetch
    }

    activity_data = {}
    try:
        r = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=payload, timeout=25)
        if r.status_code == 200:
            for row in r.json().get("data", []):
                activity_data[row.get("user_id")] = row
    except Exception as e:
        print(f"Error fetching Close activity report: {e}")

    # 2. Consultas de Pipeline y Tareas en paralelo por usuario
    pipeline_data = {}

    def fetch_user_pipeline(uid):
        res = {
            "active_opps_count": 0,
            "active_opps_value": 0,
            "stalled_opps": [], # > 7 días sin actividad
            "open_tasks_count": 0,
            "overdue_tasks_count": 0
        }
        # A. Oportunidades activas
        try:
            r_opp = requests.get(
                f"{BASE_URL}/opportunity/",
                auth=auth,
                params={"user_id": uid, "status_type": "active", "_limit": 100},
                timeout=20
            )
            if r_opp.status_code == 200:
                opp_json = r_opp.json()
                res["active_opps_count"] = opp_json.get("total_results", 0)
                # Valor anualizado / total esperado
                res["active_opps_value"] = (opp_json.get("total_value_annualized", 0) or opp_json.get("total_value_one_time", 0) or 0) / 100.0

                now_dt = datetime.now()
                for opp in opp_json.get("data", []):
                    # Chequear estancamiento (> 7 días)
                    updated_str = opp.get("date_updated") or opp.get("date_created")
                    if updated_str:
                        try:
                            # Parse ISO format
                            clean_dt = updated_str[:19].replace("T", " ")
                            dt_up = datetime.strptime(clean_dt, "%Y-%m-%d %H:%M:%S")
                            days_inactive = (now_dt - dt_up).days
                            if days_inactive >= 7:
                                res["stalled_opps"].append({
                                    "lead_name": opp.get("lead_name") or "Sin Empresa",
                                    "status": opp.get("status_label") or "Activo",
                                    "value": (opp.get("value") or 0) / 100.0,
                                    "days_inactive": days_inactive
                                })
                        except Exception:
                            pass
        except Exception as e:
            print(f"Error fetching opps for {uid}: {e}")

        # B. Tareas vencidas y pendientes
        try:
            today_iso = date.today().isoformat()
            r_task_overdue = requests.get(
                f"{BASE_URL}/task/",
                auth=auth,
                params={"assigned_to": uid, "is_complete": "false", "due_date__lt": today_iso, "_limit": 1},
                timeout=15
            )
            if r_task_overdue.status_code == 200:
                res["overdue_tasks_count"] = r_task_overdue.json().get("total_results", 0)

            r_task_all = requests.get(
                f"{BASE_URL}/task/",
                auth=auth,
                params={"assigned_to": uid, "is_complete": "false", "_limit": 1},
                timeout=15
            )
            if r_task_all.status_code == 200:
                res["open_tasks_count"] = r_task_all.json().get("total_results", 0)
        except Exception as e:
            print(f"Error fetching tasks for {uid}: {e}")

        return uid, res

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(fetch_user_pipeline, user_ids)
        for uid, pdata in results:
            pipeline_data[uid] = pdata

    # 3. Consolidar informe por agente
    agents_report = []
    total_calls_all = 0
    total_kps_all = 0
    total_emails_all = 0
    total_opps_value_all = 0

    for uid in user_ids:
        u_info = user_map.get(uid, {})
        u_act = activity_data.get(uid, {})
        u_pip = pipeline_data.get(uid, {})

        calls = u_act.get("calls.outbound.all.count", 0) or 0
        avg_call_sec = u_act.get("calls.outbound.all.avg_duration", 0) or 0
        emails_sent = u_act.get("emails.sent.manual.count", 0) or 0
        emails_replied = u_act.get("emails.sent.manual_with_reply.count", 0) or 0
        email_reply_rate = round(100.0 * emails_replied / emails_sent, 1) if emails_sent else 0.0
        kps = u_act.get(close_crm.KP_METRIC_KEY, 0) or 0
        leads_contacted = u_act.get("leads.contacted.all.count", 0) or 0
        sms_sent = u_act.get("sms.sent.all.count", 0) or 0
        meetings = u_act.get("meetings.completed.count", 0) or 0

        eff_rate = round(100.0 * kps / calls, 1) if calls else 0.0

        total_calls_all += calls
        total_kps_all += kps
        total_emails_all += emails_sent
        total_opps_value_all += u_pip.get("active_opps_value", 0)

        agents_report.append({
            "user_id": uid,
            "name": u_info.get("name"),
            "email": u_info.get("email"),
            # Dimensión Rapport
            "calls": calls,
            "avg_call_duration_min": round(avg_call_sec / 60.0, 1),
            "kps": kps,
            "effectiveness": eff_rate,
            "emails_sent": emails_sent,
            "emails_replied": emails_replied,
            "email_reply_rate": email_reply_rate,
            "sms_sent": sms_sent,
            "leads_contacted": leads_contacted,
            "meetings": meetings,
            # Dimensión Pipeline
            "active_opps": u_pip.get("active_opps_count", 0),
            "pipeline_value": round(u_pip.get("active_opps_value", 0)),
            "stalled_opps": u_pip.get("stalled_opps", []),
            "stalled_count": len(u_pip.get("stalled_opps", [])),
            "open_tasks": u_pip.get("open_tasks_count", 0),
            "overdue_tasks": u_pip.get("overdue_tasks_count", 0)
        })

    # Ordenar por llamadas y KPs
    agents_report = sorted(agents_report, key=lambda x: (x["calls"], x["kps"]), reverse=True)

    report_result = {
        "start_date": start_date,
        "end_date": end_date,
        "agents": agents_report,
        "summary": {
            "total_agents": len(agents_report),
            "total_calls": total_calls_all,
            "total_kps": total_kps_all,
            "total_emails": total_emails_all,
            "total_pipeline_value": total_opps_value_all
        }
    }
    _PERF_CACHE[cache_key] = {"data": report_result, "expires_at": time.time() + 180}
    return report_result
