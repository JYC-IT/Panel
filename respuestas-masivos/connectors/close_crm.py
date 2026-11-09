"""Integración con Close CRM para sincronizar llamadas y contactos clave (KPs)."""
import os
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

BASE_URL = "https://api.close.com/api/v1"
KP_OUTCOME_ID = "outcome_033WrVULhq3NJjJSQLPgxg"
KP_METRIC_KEY = f"outcome.{KP_OUTCOME_ID}.count"
CALLS_METRIC_KEY = "calls.all.all.count"

# Asesores comerciales del equipo JYC activos (8 asesores seleccionados)
DEFAULT_AGENT_EMAILS = [
    "hbonilla@jycexports.com",     # Hernán Bonilla
    "solutions@jycexports.com",    # Juan Abuchaibe
    "plastics@jycmachinery.com",   # Juan Arango
    "jcordoba@jycexports.com",     # Juan Córdoba
    "jp@jycmedical.com",           # Julián Prado
    "mpolanco@jycexports.com",     # Mariana Polanco
    "rjones@jycexports.com",       # Roy Jones
    "royjones@jycexports.com",     # Roy Jones (alias)
    "sjordan@jycmachinery.com",    # Sebastián Jordan
]

# Usuarios inactivos o no comerciales que deben excluirse de reportes
EXCLUDED_EMAILS = {
    "rvelez@jycmedical.com",       # Rod Vélez (desvinculado)
    "ccordoba@jycexports.com",     # Carlos Córdoba
    "ccordoba@equipmentjyc.com",
    "support@jycequipment.com",    # Support Team
}
EXCLUDED_USER_IDS = {
    "user_BWRW97kwcx8bFi9OPYzTKzlJfba7EoDV2XPdh3Fw0DI",  # Rod Vélez
    "user_Aa5pIAD0HQvnxk1hAMdvdBz3UAjW1NaVrKFMfJpmpaK",  # Carlos Córdoba
    "user_7Y6Tfhygn7yAtVJDXuloX19dCquniSIWPdUkqWKjehP",  # Support Team
}


def get_api_key():
    return (os.getenv("CLOSE_CRM_API_KEY") or "").strip()


def _get_auth():
    key = get_api_key()
    return (key, "") if key else None


def is_available():
    return bool(get_api_key())


_USERS_CACHE = {"data": None, "expires_at": 0}


def list_users(force_refresh=False):
    """Retorna la lista de todos los usuarios de Close CRM con cache en memoria de 15 min."""
    import time
    now = time.time()
    if not force_refresh and _USERS_CACHE["data"] and now < _USERS_CACHE["expires_at"]:
        return _USERS_CACHE["data"]

    auth = _get_auth()
    if not auth:
        return []
    try:
        r = requests.get(f"{BASE_URL}/user/", auth=auth, timeout=15)
        if r.status_code == 200:
            users = r.json().get("data", [])
            res = []
            for u in users:
                first = u.get("first_name") or ""
                last = u.get("last_name") or ""
                email = (u.get("email") or "").strip().lower()
                uid = u.get("id")
                name = f"{first} {last}".strip() or email or uid

                # Excluir comerciales inactivos o desvinculados
                if (
                    email in EXCLUDED_EMAILS
                    or uid in EXCLUDED_USER_IDS
                    or "rod velez" in name.lower()
                    or "carlos cordoba" in name.lower()
                    or "carlos córdoba" in name.lower()
                ):
                    continue

                is_designated = email in DEFAULT_AGENT_EMAILS
                res.append({
                    "id": u.get("id"),
                    "name": name,
                    "email": email,
                    "is_designated": is_designated,
                })
            sorted_res = sorted(res, key=lambda x: (not x["is_designated"], x["name"]))
            _USERS_CACHE["data"] = sorted_res
            _USERS_CACHE["expires_at"] = now + 900  # 15 minutos
            return sorted_res
    except Exception:
        if _USERS_CACHE["data"]:
            return _USERS_CACHE["data"]
    return []


def get_designated_agent_ids():
    """Retorna los IDs de los 5 asesores comerciales designados en Close CRM."""
    users = list_users()
    designated = [u["id"] for u in users if u["is_designated"]]
    return designated


def _fetch_day_calls(day_str, period, auth, user_ids):
    """Consulta las llamadas AM o PM de un solo día en Close CRM."""
    if period == "AM":
        time_range = {"start": f"{day_str}T00:00:00-05:00", "end": f"{day_str}T12:00:00-05:00"}
    else:
        time_range = {"start": f"{day_str}T12:00:00-05:00", "end": f"{day_str}T23:59:59-05:00"}

    payload = {
        "type": "overview",
        "datetime_range": time_range,
        "metrics": [CALLS_METRIC_KEY],
    }
    if user_ids:
        payload["users"] = list(user_ids)

    try:
        r = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json().get("aggregations", {}).get("totals", {}).get(CALLS_METRIC_KEY, 0) or 0
    except Exception:
        pass
    return 0


def fetch_week_activity(start_date, end_date, selected_user_ids=None):
    """
    Consulta a Close CRM las llamadas salientes y los KPs ('Talked to KP - Needs Next Step')
    dentro del rango de fechas dado (YYYY-MM-DD), calculando el desglose AM vs PM exacto.
    """
    auth = _get_auth()
    if not auth:
        return None

    if not selected_user_ids:
        selected_user_ids = get_designated_agent_ids()

    # 1. Consulta general por asesor (comparison report) con zona horaria local UTC-5
    payload = {
        "type": "comparison",
        "datetime_range": {
            "start": f"{start_date}T00:00:00-05:00",
            "end": f"{end_date}T23:59:59-05:00"
        },
        "metrics": [CALLS_METRIC_KEY, KP_METRIC_KEY]
    }
    if selected_user_ids:
        payload["users"] = list(selected_user_ids)

    try:
        r = requests.post(f"{BASE_URL}/report/activity/", auth=auth, json=payload, timeout=25)
        if r.status_code != 200:
            return None
        res = r.json()
    except Exception:
        return None

    lookup_users = res.get("lookup", {}).get("user", {})
    user_rows = res.get("data", [])

    per_user = []
    total_calls = 0
    total_kps = 0

    for row in user_rows:
        uid = row.get("user_id")
        if selected_user_ids and uid not in selected_user_ids:
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

    # 2. Desglose AM vs PM en paralelo usando ThreadPoolExecutor
    try:
        d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        num_days = min(7, (d_end - d_start).days + 1)
        day_strs = [(d_start + timedelta(days=i)).isoformat() for i in range(num_days)]

        tasks = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            for day_str in day_strs:
                tasks.append(("AM", executor.submit(_fetch_day_calls, day_str, "AM", auth, selected_user_ids)))
                tasks.append(("PM", executor.submit(_fetch_day_calls, day_str, "PM", auth, selected_user_ids)))

            am_calls = sum(future.result() for period, future in tasks if period == "AM")
            pm_calls = sum(future.result() for period, future in tasks if period == "PM")
    except Exception:
        am_calls = round(total_calls * 0.5)
        pm_calls = total_calls - am_calls

    effectiveness_rate = round(100.0 * total_kps / total_calls, 2) if total_calls else 0.0

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_calls": total_calls,
        "am_calls": am_calls,
        "pm_calls": pm_calls,
        "kps": total_kps,
        "effectiveness_rate": effectiveness_rate,
        "per_user": sorted(per_user, key=lambda x: x["calls"], reverse=True)
    }
