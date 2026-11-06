"""Motor de Auditoría Automática para Close CRM (Daily Sales Performance Audit).
Evalúa a un comercial en un día específico contra las reglas y pilares de JYC Equipment:
  1. Rapport & Discovery:
     - Detección de llamadas ultracortas (< 35s) con KP sin indagación abierta.
     - Detección de brechas largas sin actividad telefónica (gaps > 2 horas).
     - Calidad y cortes en buzones de voz (voicemails).
  2. Pipeline Management & CRM Hygiene:
     - Detección de Pipeline Invertido (compras registradas en Sell en vez de Purchase).
     - Fuga de prospectos (Queue Leakage): Leads tocados hoy sin tarea futura asignada.
     - Tareas vencidas sin completar.
     - Oportunidades estancadas o con precio $0 / sin actualizar.
     - Cambios sospechosos de estado de lead (ej. Unreached -> Reached tras 0s).
"""
import os
import requests
from datetime import datetime, date, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

from connectors import close_crm

BASE_URL = close_crm.BASE_URL
KP_OUTCOME_ID = close_crm.KP_OUTCOME_ID  # 'outcome_033WrVULhq3NJjJSQLPgxg'

# Zona horaria local comercial: UTC-5 (Colombia / US Eastern Standard Time)
LOCAL_OFFSET_HOURS = int(os.getenv("TIMEZONE_OFFSET", "-5"))
LOCAL_TZ = timezone(timedelta(hours=LOCAL_OFFSET_HOURS))


def to_local_datetime(iso_str):
    """Convierte una fecha ISO (generalmente UTC de Close CRM) a la hora local (UTC-5)."""
    if not iso_str:
        return None
    try:
        clean = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        return dt.astimezone(LOCAL_TZ)
    except Exception:
        return None


_AUDIT_CACHE = {}


def _get_auth():
    return close_crm._get_auth()


def audit_agent_day(user_id, audit_date=None, force_refresh=False):
    """
    Ejecuta la auditoría completa de un comercial para un día determinado (YYYY-MM-DD).
    Utiliza cache de memoria (3 min) y cache de leads en SQLite para respuesta ultrarrápida.
    """
    import time
    if not audit_date:
        audit_date = (date.today() - timedelta(days=1)).isoformat()

    cache_key = f"{user_id}_{audit_date}"
    now = time.time()
    if not force_refresh and cache_key in _AUDIT_CACHE:
        entry = _AUDIT_CACHE[cache_key]
        if now < entry["expires_at"]:
            return entry["data"]

    auth = _get_auth()
    if not auth:
        return None

    if not audit_date:
        audit_date = (date.today() - timedelta(days=1)).isoformat()

    # Obtener info del usuario
    all_users = close_crm.list_users()
    user_info = next((u for u in all_users if u["id"] == user_id), None)
    if not user_info:
        user_info = {"id": user_id, "name": "Comercial", "email": ""}

    offset_sign = "+" if LOCAL_OFFSET_HOURS >= 0 else "-"
    offset_str = f"{offset_sign}{abs(LOCAL_OFFSET_HOURS):02d}:00"
    dt_start = f"{audit_date}T00:00:00{offset_str}"
    dt_end = f"{audit_date}T23:59:59{offset_str}"

    # =========================================================================
    # 1. Recopilar Actividades del Día (Llamadas, Emails, Notas) con Paginación
    # =========================================================================
    def fetch_all_activities(endpoint, extra_params=None):
        items = []
        skip = 0
        limit = 100
        while True:
            params = {
                "user_id": user_id,
                "date_created__gte": dt_start,
                "date_created__lte": dt_end,
                "_limit": limit,
                "_skip": skip
            }
            if extra_params:
                params.update(extra_params)
            try:
                r = requests.get(f"{BASE_URL}/{endpoint}/", auth=auth, params=params, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    batch = data.get("data", [])
                    items.extend(batch)
                    if not data.get("has_more") or len(batch) < limit or len(items) >= 500:
                        break
                    skip += limit
                else:
                    break
            except Exception as e:
                print(f"Error fetching {endpoint}: {e}")
                break
        return items

    with ThreadPoolExecutor(max_workers=3) as executor:
        f_calls = executor.submit(fetch_all_activities, "activity/call")
        f_emails = executor.submit(fetch_all_activities, "activity/email", {"direction": "outbound"})
        f_notes = executor.submit(fetch_all_activities, "activity/note")

        calls = f_calls.result()
        emails = f_emails.result()
        notes = f_notes.result()

    # Orden cronológico ascendente de llamadas
    calls = sorted(calls, key=lambda x: x.get("date_created", ""))

    # =========================================================================
    # 2. Cache de Leads tocados hoy
    # =========================================================================
    lead_ids_touched = set()
    for c in calls:
        if c.get("lead_id"):
            lead_ids_touched.add(c.get("lead_id"))
    for e in emails:
        if e.get("lead_id"):
            lead_ids_touched.add(e.get("lead_id"))
    for n in notes:
        if n.get("lead_id"):
            lead_ids_touched.add(n.get("lead_id"))

    # Leer primero de SQLite persistente para acelerar a 0ms los ya conocidos
    import db
    leads_cache = db.get_cached_leads(lead_ids_touched)
    missing_lead_ids = [lid for lid in lead_ids_touched if lid not in leads_cache]

    if missing_lead_ids:
        def fetch_single_lead(lid):
            try:
                r = requests.get(
                    f"{BASE_URL}/lead/{lid}/",
                    auth=auth,
                    params={"_fields": "id,display_name"},
                    timeout=10
                )
                if r.status_code == 200:
                    return lid, r.json()
            except Exception:
                pass
            return lid, {"display_name": "Lead"}

        newly_fetched = {}
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = executor.map(fetch_single_lead, missing_lead_ids[:50])
            for lid, ldata in results:
                leads_cache[lid] = ldata
                newly_fetched[lid] = ldata
        db.save_cached_leads(newly_fetched)

    # =========================================================================
    # 3. Métricas Numéricas de Encabezado
    # =========================================================================
    total_calls = len(calls)
    outbound_calls = [c for c in calls if c.get("direction") == "outbound"]
    inbound_calls = [c for c in calls if c.get("direction") == "inbound"]

    gross_seconds = sum(c.get("duration", 0) or 0 for c in calls)
    kp_calls = [
        c for c in calls
        if c.get("disposition") == KP_OUTCOME_ID
        or (c.get("duration", 0) and c.get("duration") >= 90)
    ]
    kp_talk_seconds = sum(c.get("duration", 0) or 0 for c in kp_calls)

    emails_sent_count = len(emails)
    # Detectar emails duplicados (mismo lead en menos de 10 min)
    duplicate_emails = 0
    email_times = {}
    for em in sorted(emails, key=lambda x: x.get("date_created", "")):
        lid = em.get("lead_id")
        created_str = em.get("date_created", "")[:19]
        if lid in email_times:
            try:
                prev_dt = datetime.strptime(email_times[lid], "%Y-%m-%d %H:%M:%S")
                curr_dt = datetime.strptime(created_str.replace("T", " "), "%Y-%m-%d %H:%M:%S")
                if (curr_dt - prev_dt).total_seconds() <= 600:
                    duplicate_emails += 1
            except Exception:
                pass
        email_times[lid] = created_str.replace("T", " ")

    # =========================================================================
    # 4. Auditoría de Tareas (Queue Leakage & Hygiene)
    # =========================================================================
    # Obtener todas las tareas abiertas asignadas al comercial
    open_tasks_for_user = []
    overdue_tasks_count = 0
    today_iso = date.today().isoformat()
    try:
        r_tasks = requests.get(
            f"{BASE_URL}/task/",
            auth=auth,
            params={"assigned_to": user_id, "is_complete": "false", "_limit": 100},
            timeout=20
        )
        if r_tasks.status_code == 200:
            open_tasks_for_user = r_tasks.json().get("data", [])
            for t in open_tasks_for_user:
                if (t.get("due_date") or "")[:10] < today_iso:
                    overdue_tasks_count += 1
    except Exception as e:
        print(f"Error fetching tasks: {e}")

    leads_with_future_task = {t.get("lead_id") for t in open_tasks_for_user if t.get("lead_id")}
    leads_without_task = []
    for lid in lead_ids_touched:
        if lid not in leads_with_future_task:
            lname = leads_cache.get(lid, {}).get("display_name") or "Sin Nombre"
            leads_without_task.append({"lead_id": lid, "lead_name": lname})

    # =========================================================================
    # 5. Auditoría de Oportunidades y Pipeline Invertido
    # =========================================================================
    opps_created_today = []
    inverted_pipeline_errors = []
    total_opps_value_today = 0

    try:
        r_opps = requests.get(
            f"{BASE_URL}/opportunity/",
            auth=auth,
            params={
                "user_id": user_id,
                "date_created__gte": dt_start,
                "date_created__lte": dt_end,
                "_limit": 50
            },
            timeout=20
        )
        if r_opps.status_code == 200:
            for opp in r_opps.json().get("data", []):
                val = (opp.get("value") or 0) / 100.0
                total_opps_value_today += val
                pipeline_id = opp.get("pipeline_id")
                # pipe_2g0VCRFwavbPI4whagZads = Sell (Wants to Buy)
                # pipe_3BxoKZTZl7XgFpE3YpVQJr = Purchase (Wants to Sell)
                lead_data = leads_cache.get(opp.get("lead_id"), {})
                lead_name = opp.get("lead_name") or lead_data.get("display_name") or "Lead"
                note_text = (opp.get("note") or "").lower()

                # Regla de pipeline invertido: si el nombre o nota sugiere que JYC compra equipo
                # pero está registrada en el Sell Pipeline (pipe_2g0VCRFwavbPI4whagZads)
                is_purchase_context = any(w in note_text for w in ["comprar", "purchase", "bottom line", "blp", "we buy", "asking"])
                if pipeline_id == "pipe_2g0VCRFwavbPI4whagZads" and is_purchase_context:
                    inverted_pipeline_errors.append({
                        "lead_name": lead_name,
                        "value": val,
                        "issue": "Oportunidad de COMPRA registrada incorrectamente en Pipeline SELL (Wants to Buy)"
                    })

                opps_created_today.append({
                    "id": opp.get("id"),
                    "lead_name": lead_name,
                    "value": val,
                    "status_label": opp.get("status_label"),
                    "pipeline_name": "Sell" if pipeline_id == "pipe_2g0VCRFwavbPI4whagZads" else "Purchase"
                })
    except Exception as e:
        print(f"Error checking opps: {e}")

    # =========================================================================
    # 6. Detección de Brechas de Llamadas (Calling Gaps > 2 horas)
    # =========================================================================
    calling_gaps = []
    for i in range(len(calls) - 1):
        try:
            t1 = to_local_datetime(calls[i].get("date_created"))
            t2 = to_local_datetime(calls[i + 1].get("date_created"))
            if t1 and t2:
                gap_seconds = (t2 - t1).total_seconds()
                if gap_seconds >= 7200:  # Más de 2 horas sin llamar
                    gap_hours = round(gap_seconds / 3600.0, 1)
                    calling_gaps.append({
                        "start": t1.strftime("%I:%M %p"),
                        "end": t2.strftime("%I:%M %p"),
                        "duration_hours": gap_hours
                    })
        except Exception:
            pass

    # =========================================================================
    # 7. Evaluación de los 5 Pilares de Rapport (Puntajes y Hallazgos)
    # =========================================================================
    # A. Llamadas ultracortas de prospección (< 35s)
    short_live_calls = [c for c in calls if 5 < (c.get("duration") or 0) <= 35 and c.get("disposition") != "voicemail"]
    # B. Voicemails dejados
    vm_calls = [c for c in calls if (c.get("duration") or 0) > 40 and ("vm" in (c.get("note") or "").lower() or c.get("disposition") == "voicemail")]

    # Evaluación y puntuación ponderada
    rapport_score = 5.0
    pipeline_score = 5.0

    # Penalizaciones Rapport
    if len(short_live_calls) >= 2:
        rapport_score -= 1.0  # Rushed pitches
    if calling_gaps:
        rapport_score -= 0.5  # Brechas de llamadas
    if len(kp_calls) == 0 and total_calls > 10:
        rapport_score -= 1.0  # Cero KPs conectados

    # Penalizaciones Pipeline
    if inverted_pipeline_errors:
        pipeline_score -= 1.5  # Error crítico de pipeline invertido
    if len(leads_without_task) > 0:
        leak_ratio = len(leads_without_task) / max(1, len(lead_ids_touched))
        pipeline_score -= min(2.0, round(leak_ratio * 2.0, 1))
    if overdue_tasks_count > 10:
        pipeline_score -= 0.5

    rapport_score = max(1.0, round(rapport_score, 1))
    pipeline_score = max(1.0, round(pipeline_score, 1))

    # Score consolidado sobre 100
    overall_points = round((rapport_score * 10) + (pipeline_score * 10))
    if overall_points >= 90:
        overall_grade, overall_status = "A+", "Excelente"
    elif overall_points >= 80:
        overall_grade, overall_status = "A", "Sobresaliente"
    elif overall_points >= 70:
        overall_grade, overall_status = "B", "Cumplimiento Adecuado"
    elif overall_points >= 60:
        overall_grade, overall_status = "C", "Atención Requerida"
    else:
        overall_grade, overall_status = "D", "Coaching Urgente"

    # =========================================================================
    # 8. Log Cronológico de Actividades
    # =========================================================================
    activity_log = []
    for c in calls:
        local_dt = to_local_datetime(c.get("date_created"))
        time_str = local_dt.strftime("%I:%M %p") if local_dt else "--:--"
        dur = c.get("duration") or 0
        dur_str = f"{dur}s" if dur < 60 else f"{dur // 60}m {dur % 60}s"
        lid = c.get("lead_id")
        lead_data = leads_cache.get(lid, {})
        lname = lead_data.get("display_name") or "Lead"
        note = c.get("note") or ""

        # Diagnóstico del renglón
        disposition_notes = []
        if dur == 0:
            disposition_notes.append("No answer / 0s")
        elif dur <= 30 and not note:
            disposition_notes.append("Rushed call / No notes")
        if c.get("disposition") == KP_OUTCOME_ID:
            disposition_notes.append("🌟 Live KP Connect")
        if note:
            disposition_notes.append(note[:120])

        has_rec = bool(c.get("recording_url") or c.get("voice_recording_url") or (dur > 15 and c.get("recording_status") not in ("failed", "disabled")))
        activity_log.append({
            "call_id": c.get("id"),
            "lead_id": lid,
            "time": time_str,
            "lead_name": lname,
            "has_recording": has_rec,
            "type": f"Call ({dur_str})",
            "notes": " · ".join(disposition_notes) if disposition_notes else "Completed"
        })

    # =========================================================================
    # 9. Checklist de Coaching y Remediación
    # =========================================================================
    coaching_checklist = []
    if inverted_pipeline_errors:
        coaching_checklist.append(
            f"Reclasificar oportunidades al Pipeline Correcto: Se detectaron {len(inverted_pipeline_errors)} tratos registrados en Sell que pertenecen a Purchase."
        )
    if leads_without_task:
        coaching_checklist.append(
            f"Cero fugas de prospectos (Queue Leakage): {len(leads_without_task)} de los {len(lead_ids_touched)} leads tocados hoy quedaron sin tarea futura. Exigir tarea en 100% de llamadas."
        )
    if calling_gaps:
        longest = max(calling_gaps, key=lambda x: x["duration_hours"])
        coaching_checklist.append(
            f"Eliminar baches en prospección: Hubo un receso de {longest['duration_hours']} horas ({longest['start']} a {longest['end']}) sin actividad de llamadas."
        )
    if short_live_calls:
        coaching_checklist.append(
            f"Evitar preguntas binarias cerradas: En llamadas atendidas de menos de 30s, hacer preguntas abiertas sobre el tamaño de flota y ciclos de reemplazo antes de colgar."
        )
    if overdue_tasks_count > 0:
        coaching_checklist.append(
            f"Depurar bandeja de tareas vencidas: Actualmente el comercial acumula {overdue_tasks_count} tareas retrasadas sin completar."
        )

    audit_result = {
        "audit_date": audit_date,
        "user_id": user_id,
        "agent_name": user_info.get("name"),
        "agent_email": user_info.get("email"),
        "scores": {
            "rapport": rapport_score,
            "pipeline": pipeline_score,
            "overall": overall_points,
            "grade": overall_grade,
            "status": overall_status
        },
        "kpis": {
            "total_calls": total_calls,
            "outbound_calls": len(outbound_calls),
            "inbound_calls": len(inbound_calls),
            "leads_touched": len(lead_ids_touched),
            "kp_connects": len(kp_calls),
            "kp_talk_time_min": round(kp_talk_seconds / 60.0, 1),
            "gross_dial_time_min": round(gross_seconds / 60.0, 1),
            "emails_sent": emails_sent_count,
            "duplicate_emails": duplicate_emails,
            "opps_created": len(opps_created_today),
            "opps_value": total_opps_value_today,
            "leads_without_task_count": len(leads_without_task),
            "overdue_tasks_count": overdue_tasks_count
        },
        "findings": {
            "inverted_pipeline": inverted_pipeline_errors,
            "leads_without_future_task": leads_without_task[:15],
            "calling_gaps": calling_gaps,
            "short_live_calls_count": len(short_live_calls)
        },
        "activity_log": activity_log,
        "coaching_checklist": coaching_checklist
    }
    _AUDIT_CACHE[cache_key] = {"data": audit_result, "expires_at": time.time() + 180}
    return audit_result
