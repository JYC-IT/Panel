"""Orquesta la sincronización de todas las fuentes y la guarda en la base de datos."""
import os
import re
import threading

import db
from connectors import (
    constantcontact,
    gmail,
    google_workspace,
    instantly,
)

_lock = threading.Lock()


def _cfg(name, default=""):
    return (os.getenv(name) or default).strip()


def _get_workspace_users():
    """Retorna la lista de correos a monitorear con la Service Account."""
    users = set()
    custom = _cfg("GOOGLE_WORKSPACE_MONITOR_USERS")
    if custom:
        for u in custom.split(","):
            if u.strip():
                users.add(u.strip().lower())

    # Cuentas clave predeterminadas
    default_users = ["jp@jycmedical.com", "support@jycequipment.com", "julianp@jyccorporation.com"]
    for d in default_users:
        users.add(d.lower())

    u1 = _cfg("GMAIL_USER")
    if u1:
        users.add(u1.strip().lower())

    # Detectar automáticamente todos los correos donde las campañas reciben respuestas
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT reply_to_email FROM campaigns WHERE reply_to_email IS NOT NULL AND reply_to_email != ''"
            ).fetchall()
            for r in rows:
                if r[0] and "@" in r[0]:
                    users.add(r[0].strip().lower())
    except Exception:
        pass

    return sorted(list(users))


def _get_mailboxes():
    """Obtiene la lista de cuentas IMAP tradicionales configuradas."""
    accounts = []
    u1, p1 = _cfg("GMAIL_USER"), _cfg("GMAIL_APP_PASSWORD").replace(" ", "")
    if u1 and p1:
        accounts.append((u1, p1))
    
    for i in range(2, 6):
        u = _cfg(f"GMAIL_USER_{i}")
        p = _cfg(f"GMAIL_APP_PASSWORD_{i}").replace(" ", "")
        if u and p:
            accounts.append((u, p))
    return accounts


def sync_gmail_campaigns():
    with db.get_conn() as conn:
        campaigns = [dict(r) for r in conn.execute(
            "SELECT * FROM campaigns WHERE source IN ('gmail', 'constantcontact') AND match_subject IS NOT NULL AND match_subject != ''"
        )]
    if not campaigns:
        return "Gmail: no hay campañas con asunto para rastrear"

    # MODO 1: Google Workspace Service Account (Domain-Wide Delegation)
    if google_workspace.is_service_account_available():
        target_users = _get_workspace_users()
        total_new = 0
        errors = []
        for user_email in target_users:
            # Seleccionar campañas relevantes para este buzón:
            # Si el buzón es uno de los administradores principales, busca todas las campañas.
            # Si es el buzón específico de un asesor/vendedor, busca solo las campañas donde él es el reply_to.
            if user_email in ("jp@jycmedical.com", "support@jycequipment.com", "julianp@jyccorporation.com"):
                user_campaigns = campaigns
            else:
                user_campaigns = [
                    c for c in campaigns
                    if (c.get("reply_to_email") or "").strip().lower() == user_email
                ]

            if not user_campaigns:
                continue

            try:
                results = google_workspace.fetch_replies_for_user(
                    user_email,
                    user_campaigns,
                    default_lookback_days=int(_cfg("LOOKBACK_DAYS", "30")),
                )
                with db.get_conn() as conn:
                    for cid, replies in results.items():
                        for r in replies:
                            total_new += db.insert_reply(conn, cid, r)
            except Exception as exc:
                errors.append(f"{user_email} ({exc})")

        err_msg = f" (errores en: {', '.join(errors)})" if errors else ""
        return f"Google Workspace ({len(target_users)} buzones monitoreados): {total_new} respuestas nuevas{err_msg}"

    # MODO 2: IMAP Tradicional
    mailboxes = _get_mailboxes()
    if not mailboxes:
        return "Gmail: sin configurar (omitido)"

    total_new = 0
    errors = []
    for user, pwd in mailboxes:
        try:
            results = gmail.fetch_replies(
                user,
                pwd,
                campaigns,
                default_lookback_days=int(_cfg("LOOKBACK_DAYS", "30")),
                folder=_cfg("GMAIL_FOLDER") or None,
            )
            with db.get_conn() as conn:
                for cid, replies in results.items():
                    for r in replies:
                        total_new += db.insert_reply(conn, cid, r)
        except Exception as exc:
            errors.append(f"{user} ({exc})")

    err_msg = f" (errores en: {', '.join(errors)})" if errors else ""
    return f"Gmail IMAP ({len(mailboxes)} buzones): {total_new} respuestas nuevas{err_msg}"


def sync_constantcontact_campaigns():
    token = constantcontact.get_access_token()
    if not token:
        return "Constant Contact: sin configurar (omitido)"

    # Cargar campañas e interacciones ya guardadas para sincronización incremental ultrarrápida
    with db.get_conn() as conn:
        existing_rows = conn.execute(
            """SELECT id, external_id, name, match_subject, reply_to_email,
                      sent_count, opens_count, clicks_count, bounces_count, start_date
               FROM campaigns WHERE source = 'constantcontact'"""
        ).fetchall()
        known_campaigns = {r["external_id"]: dict(r) for r in existing_rows}
        existing_interactions = dict(
            conn.execute(
                """SELECT campaign_id, COUNT(*)
                   FROM contact_interactions
                   WHERE interaction_type = 'click'
                   GROUP BY campaign_id"""
            ).fetchall()
        )

    try:
        remote = constantcontact.fetch_recent_campaigns_with_details(
            token, limit=50, known_campaigns=known_campaigns, max_workers=8
        )
    except Exception as exc:
        return f"Constant Contact: ERROR al conectar API - {exc}"

    if not remote:
        return "Constant Contact: no se encontraron campañas"

    added = 0
    with db.get_conn() as conn:
        for rc in remote:
            cid = rc["campaign_id"]
            name = rc["name"]
            raw_subject = rc["subject"] or rc["name"]
            # Limpiar etiquetas de personalización tipo [[FIRSTNAME OR ""]] para buscar el texto real en Gmail
            clean_subject = re.sub(r'\[\[.*?\]\]', '', raw_subject).strip()
            subject = clean_subject if clean_subject else raw_subject
            reply_to = (rc.get("reply_to") or "").strip().lower()
            sent = int(rc.get("sent_count") or 0)
            opens = int(rc.get("opens") or 0)
            clicks = int(rc.get("clicks") or 0)
            bounces = int(rc.get("bounces") or 0)
            start_date = rc.get("start_date")

            cur = conn.execute(
                """INSERT INTO campaigns (name, source, match_subject, reply_to_email, external_id, sent_count, opens_count, clicks_count, bounces_count, start_date)
                   VALUES (?, 'constantcontact', ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(external_id) DO UPDATE SET
                       name=excluded.name,
                       match_subject=excluded.match_subject,
                       reply_to_email=COALESCE(excluded.reply_to_email, campaigns.reply_to_email),
                       sent_count=excluded.sent_count,
                       opens_count=excluded.opens_count,
                       clicks_count=excluded.clicks_count,
                       bounces_count=excluded.bounces_count,
                       start_date=COALESCE(campaigns.start_date, excluded.start_date)""",
                (name, subject, reply_to or None, cid, sent, opens, clicks, bounces, start_date),
            )
            if cur.rowcount > 0:
                added += 1

            # Obtener el ID interno de la campaña en SQLite
            local_row = conn.execute("SELECT id FROM campaigns WHERE external_id = ?", (cid,)).fetchone()
            if local_row and rc.get("primary_activity_id") and clicks > 0:
                local_cid = local_row[0]
                # Solo descargamos contactos de clics si no los tenemos aún o si hubo nuevos clics
                already_saved = existing_interactions.get(local_cid, 0)
                if already_saved < clicks or already_saved == 0:
                    try:
                        click_contacts = constantcontact.fetch_activity_tracking(
                            token, rc["primary_activity_id"], tracking_type="clicks", limit=100
                        )
                        for contact in click_contacts:
                            db.insert_interaction(conn, local_cid, contact)
                    except Exception:
                        pass

    try:
        sync_weekly_close_kpis()
    except Exception:
        pass

    return f"Constant Contact: {len(remote)} campañas sincronizadas ({added} actualizadas/nuevas)"


def sync_instantly_campaigns():
    key = _cfg("INSTANTLY_API_KEY")
    if not key:
        return "Instantly: sin configurar (omitido)"

    remote = instantly.list_campaigns(key)
    try:
        stats = instantly.campaign_analytics(key)
    except Exception:
        stats = {}

    new = 0
    with db.get_conn() as conn:
        for rc in remote:
            ext_id = rc.get("id")
            if not ext_id:
                continue
            st = stats.get(ext_id) or {}
            sent = int(st.get("emails_sent_count") or 0)
            opens = int(st.get("open_count") or 0)
            clicks = int(st.get("link_click_count") or 0)
            bounces = int(st.get("bounced_count") or 0)
            created = rc.get("timestamp_created")
            start_date = created[:10] if created else None
            conn.execute(
                """INSERT INTO campaigns (name, source, external_id, sent_count, opens_count, clicks_count, bounces_count, start_date)
                   VALUES (?, 'instantly', ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(external_id) DO UPDATE SET 
                       name = excluded.name, 
                       sent_count = excluded.sent_count,
                       opens_count = excluded.opens_count,
                       clicks_count = excluded.clicks_count,
                       bounces_count = excluded.bounces_count,
                       start_date = COALESCE(campaigns.start_date, excluded.start_date)""",
                (rc.get("name") or ext_id, ext_id, sent, opens, clicks, bounces, start_date),
            )
        conn.commit()
        local = {r["external_id"]: (r["id"], r["n"]) for r in conn.execute(
            """SELECT c.id, c.external_id, COUNT(r.id) AS n FROM campaigns c
               LEFT JOIN replies r ON r.campaign_id = c.id
               WHERE c.source='instantly' GROUP BY c.id""")}

    errors = 0
    for ext_id, (cid, stored) in local.items():
        remote_replies = (stats.get(ext_id) or {}).get("reply_count")
        # Si Instantly no reporta respuestas nuevas, no hace falta descargar nada (evita el límite 429)
        if stats and remote_replies is not None and int(remote_replies) <= stored:
            continue
        try:
            replies = instantly.fetch_replies(key, ext_id)
        except Exception:  # noqa: BLE001 - seguimos con las demás campañas
            errors += 1
            continue
        with db.get_conn() as conn:
            for r in replies:
                new += db.insert_reply(conn, cid, r)
    extra = f" ({errors} campañas con error, se reintentará)" if errors else ""
    return f"Instantly: {len(remote)} campañas, {new} respuestas nuevas{extra}"


def sync_weekly_close_kpis():
    """Sincroniza automáticamente la semana actual (Lunes-Viernes) desde Close CRM + campañas hacia weekly_team_kpis y mantiene solo 4 semanas."""
    from datetime import date, timedelta
    from connectors import close_crm

    if not close_crm.is_available():
        return "Weekly KPIs: Close CRM no configurado (omitido)"

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    sunday = monday + timedelta(days=6)

    # Semana 27 inició el lunes 2026-11-02
    week_number = 27 + ((monday - date(2026, 11, 2)).days // 7)
    week_label = f"Week {week_number}"
    months_es = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    if monday.month == friday.month:
        date_range = f"{months_es[monday.month]} {monday.day} - {friday.day}"
    else:
        date_range = f"{months_es[monday.month]} {monday.day} - {months_es[friday.month]} {friday.day}"

    all_users = close_crm.list_users()
    designated_ids = [u["id"] for u in all_users if u.get("is_designated")]
    res = close_crm.fetch_week_activity(monday.isoformat(), friday.isoformat(), designated_ids)
    if not res:
        return f"Weekly KPIs (W{week_number}): sin respuesta de Close CRM"

    close_crm_calls = int(res.get("total_calls") or 0)
    am_crm = int(res.get("am_calls") or 0)
    pm_crm = int(res.get("pm_calls") or 0)
    kps = int(res.get("kps") or 0)

    with db.get_conn() as conn:
        existing = conn.execute(
            """SELECT ringcentral_calls, outreach_sms, notes, outreach_emails_cc, outreach_emails_instantly,
                      opens_count, clicks_count, click_rate
               FROM weekly_team_kpis WHERE week_number = ?""",
            (week_number,),
        ).fetchone()
        rc_calls = int(existing["ringcentral_calls"] or 0) if existing else 0
        sms_count = int(existing["outreach_sms"] or 0) if existing else 0
        notes = (existing["notes"] or "") if existing else ""

        total_calls = close_crm_calls + rc_calls
        if rc_calls > 0:
            ratio_am = am_crm / close_crm_calls if close_crm_calls else 0.5
            rc_am = round(rc_calls * ratio_am)
            am_calls = am_crm + rc_am
            pm_calls = pm_crm + (rc_calls - rc_am)
        else:
            am_calls, pm_calls = am_crm, pm_crm

        effectiveness_rate = round(100.0 * kps / total_calls, 2) if total_calls else 0.0

        camp_row = conn.execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN source='constantcontact' THEN sent_count ELSE 0 END), 0) AS cc_sent,
                   COALESCE(SUM(CASE WHEN source='instantly' THEN sent_count ELSE 0 END), 0) AS inst_sent,
                   COALESCE(SUM(opens_count), 0) AS opens_sum,
                   COALESCE(SUM(clicks_count), 0) AS clicks_sum
               FROM campaigns
               WHERE COALESCE(NULLIF(substr(start_date, 1, 10), ''), substr(created_at, 1, 10)) BETWEEN ? AND ?""",
            (monday.isoformat(), sunday.isoformat()),
        ).fetchone()
        cc_sent = int(camp_row["cc_sent"] or 0)
        inst_sent = int(camp_row["inst_sent"] or 0)
        opens_sum = int(camp_row["opens_sum"] or 0)
        clicks_sum = int(camp_row["clicks_sum"] or 0)

        # Si la consulta de campañas devuelve 0 pero ya existía un valor registrado (manual o previo), conservarlo
        if cc_sent == 0 and existing and int(existing["outreach_emails_cc"] or 0) > 0:
            cc_sent = int(existing["outreach_emails_cc"])
        if inst_sent == 0 and existing and int(existing["outreach_emails_instantly"] or 0) > 0:
            inst_sent = int(existing["outreach_emails_instantly"])
        if opens_sum == 0 and existing and int(existing["opens_count"] or 0) > 0:
            opens_sum = int(existing["opens_count"])
        if clicks_sum == 0 and existing and int(existing["clicks_count"] or 0) > 0:
            clicks_sum = int(existing["clicks_count"])

        total_outreach = cc_sent + inst_sent + sms_count
        click_rate = round(100.0 * clicks_sum / total_outreach, 2) if total_outreach else (float(existing["click_rate"] or 0.0) if existing else 0.0)

        conn.execute(
            """INSERT INTO weekly_team_kpis
               (week_number, week_label, date_range, am_calls, pm_calls, close_crm_calls, ringcentral_calls,
                total_calls, calls_goal, kps, kps_goal, effectiveness_rate, notes,
                outreach_emails_cc, outreach_emails_instantly, outreach_sms, total_outreach,
                opens_count, clicks_count, click_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2000, ?, 125, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(week_number) DO UPDATE SET
                   week_label=excluded.week_label,
                   date_range=excluded.date_range,
                   am_calls=excluded.am_calls,
                   pm_calls=excluded.pm_calls,
                   close_crm_calls=excluded.close_crm_calls,
                   total_calls=excluded.total_calls,
                   kps=excluded.kps,
                   effectiveness_rate=excluded.effectiveness_rate,
                   outreach_emails_cc=excluded.outreach_emails_cc,
                   outreach_emails_instantly=excluded.outreach_emails_instantly,
                   total_outreach=excluded.total_outreach,
                   opens_count=excluded.opens_count,
                   clicks_count=excluded.clicks_count,
                   click_rate=excluded.click_rate""",
            (
                week_number, week_label, date_range, am_calls, pm_calls, close_crm_calls, rc_calls,
                total_calls, kps, effectiveness_rate, notes,
                cc_sent, inst_sent, sms_count, total_outreach, opens_sum, clicks_sum, click_rate,
            ),
        )

    db.save_agent_kpis(week_number, res.get("per_user") or [])
    db.prune_old_weekly_kpis(keep=4)
    return f"Weekly KPIs (W{week_number}): {total_calls} llamadas, {kps} KPs (4 semanas activas)"


def run_all():
    """Ejecuta todas las fuentes. Devuelve lista de mensajes."""
    if not _lock.acquire(blocking=False):
        return ["Ya hay una sincronización en curso"]
    messages = []
    try:
        # Sincronizamos primero las plataformas de envío (CC e Instantly),
        # y luego Gmail para que pueda detectar respuestas de las campañas recién actualizadas
        sources = (
            ("constantcontact", sync_constantcontact_campaigns),
            ("instantly", sync_instantly_campaigns),
            ("gmail", sync_gmail_campaigns),
            ("weekly_kpis", sync_weekly_close_kpis),
        )
        for source, fn in sources:
            try:
                msg = fn()
                db.log_sync(source, True, msg)
            except Exception as exc:  # noqa: BLE001 - se registra cualquier error de la fuente
                msg = f"{source}: ERROR - {exc}"
                db.log_sync(source, False, msg)
            messages.append(msg)

        # Deduplicación inteligente: garantiza que ninguna respuesta quede atribuida a más de una campaña
        try:
            removed_dups = db.deduplicate_replies()
            if removed_dups > 0:
                messages.append(f"Atribución: {removed_dups} respuestas duplicadas resueltas a su campaña correcta")
        except Exception:
            pass
    finally:
        _lock.release()
    return messages


_scheduler_started = False

def start_scheduler():
    """Hilo en segundo plano que sincroniza cada SYNC_INTERVAL_MINUTES."""
    global _scheduler_started
    if _scheduler_started:
        return
    minutes = int(_cfg("SYNC_INTERVAL_MINUTES", "15"))
    if minutes <= 0:
        return
    _scheduler_started = True
    stop = threading.Event()

    def loop():
        if stop.wait(5):  # primera sincronización poco después de arrancar
            return
        while True:
            run_all()
            if stop.wait(minutes * 60):
                return

    threading.Thread(target=loop, daemon=True, name="sync-scheduler").start()
    return stop
