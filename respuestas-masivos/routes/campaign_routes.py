"""Rutas principales para campañas de email masivo, respuestas, clics e integraciones."""
import csv
from datetime import date, timedelta
import io
import os
from flask import Response, abort, flash, redirect, render_template, request, url_for
import auth
from config import Config
from connectors import constantcontact
import db
from services import sync
from utils.intent_classifier import INTENT_CONFIG

STATS_SQL = """
SELECT c.*,
       COALESCE(SUM(CASE WHEN r.is_auto = 0 THEN 1 END), 0)                    AS replies,
       COUNT(DISTINCT CASE WHEN r.is_auto = 0 THEN r.from_email END)           AS responders,
       COALESCE(SUM(CASE WHEN r.is_auto = 0 AND r.intent = 'buy' THEN 1 END), 0) AS buyers_count,
       COALESCE(SUM(CASE WHEN r.is_auto = 0 AND r.intent = 'sell' THEN 1 END), 0) AS sellers_count,
       COALESCE(SUM(CASE WHEN r.is_auto = 1 THEN 1 END), 0)                    AS auto_replies,
       MAX(CASE WHEN r.is_auto = 0 THEN r.received_at END)                     AS last_reply
FROM campaigns c
LEFT JOIN replies r ON r.campaign_id = c.id
{where}
GROUP BY c.id
ORDER BY c.created_at DESC, c.id DESC
"""


def _rate(responders, sent):
    return round(100.0 * responders / sent, 1) if sent else None


def _fecha(value):
    return (value or "")[:16].replace("T", " ")


def _get_campaign(cid):
    with db.get_conn() as conn:
        row = conn.execute(STATS_SQL.format(where="WHERE c.id = ?"), (cid,)).fetchone()
    if not row:
        abort(404)
    c = dict(row)
    c["rate"] = _rate(c["responders"], c["sent_count"])
    return c


def register_campaign_routes(app):
    @app.route("/")
    def index():
        cutoff_date = (date.today() - timedelta(days=42)).isoformat()
        where_6w = "WHERE COALESCE(NULLIF(substr(c.start_date, 1, 10), ''), substr(c.created_at, 1, 10)) >= ?"
        with db.get_conn() as conn:
            rows = [dict(r) for r in conn.execute(STATS_SQL.format(where=where_6w), (cutoff_date,))]
            last_syncs = [dict(r) for r in conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 4")]
            total_unique = conn.execute(
                """SELECT COUNT(DISTINCT r.from_email)
                   FROM replies r
                   JOIN campaigns c ON c.id = r.campaign_id
                   WHERE r.is_auto = 0
                     AND COALESCE(NULLIF(substr(c.start_date, 1, 10), ''), substr(c.created_at, 1, 10)) >= ?""",
                (cutoff_date,),
            ).fetchone()[0]
            advisors = [
                r[0] for r in conn.execute(
                    """SELECT DISTINCT reply_to_email FROM campaigns
                       WHERE reply_to_email IS NOT NULL AND reply_to_email != ''
                       AND COALESCE(NULLIF(substr(start_date, 1, 10), ''), substr(created_at, 1, 10)) >= ?
                       AND reply_to_email NOT LIKE '%ccordoba%'
                       AND reply_to_email NOT LIKE '%rjones%'
                       AND reply_to_email NOT LIKE '%royjones%'
                       ORDER BY reply_to_email""",
                    (cutoff_date,),
                ).fetchall()
            ]
        for r in rows:
            r["rate"] = _rate(r["responders"], r["sent_count"])
        totals = {
            "campaigns": len(rows),
            "sent": sum(r["sent_count"] or 0 for r in rows),
            "opens": sum(r["opens_count"] or 0 for r in rows),
            "clicks": sum(r["clicks_count"] or 0 for r in rows),
            "replies": sum(r["replies"] for r in rows),
            "buyers": sum(r.get("buyers_count", 0) for r in rows),
            "sellers": sum(r.get("sellers_count", 0) for r in rows),
            "unique": total_unique,
        }
        totals["rate"] = _rate(sum(r["responders"] for r in rows), totals["sent"])
        return render_template("index.html", campaigns=rows, totals=totals, last_syncs=last_syncs,
                               advisors=advisors, active_page="campaigns", interval=Config.SYNC_INTERVAL_MINUTES)

    @app.post("/campaign/create")
    @app.post("/campaigns")
    @auth.admin_required
    def create_campaign():
        """Permite registrar manualmente una campaña enviada (contingencia de APIs o Gmail)."""
        name = request.form.get("name", "").strip()
        source = request.form.get("source", "constantcontact").strip().lower()
        start_date = request.form.get("start_date") or None
        sent_count = request.form.get("sent_count", 0)
        opens_count = request.form.get("opens_count", 0)
        clicks_count = request.form.get("clicks_count", 0)
        reply_to_email = request.form.get("reply_to_email", "").strip() or None
        subject = (request.form.get("subject") or request.form.get("match_subject", "")).strip() or None

        if not name:
            flash("El nombre de la campaña es obligatorio.", "error")
            return redirect(url_for("index"))

        try:
            cid = db.insert_manual_campaign(
                name=name,
                source=source,
                start_date=start_date,
                sent_count=sent_count,
                opens_count=opens_count,
                clicks_count=clicks_count,
                match_subject=subject,
                reply_to_email=reply_to_email
            )
            flash(f"Campaña «{name}» registrada correctamente ({source.upper()}).", "ok")
        except Exception as e:
            flash(f"Error al registrar la campaña: {e}", "error")

        return redirect(url_for("index"))

    @app.route("/campaign/<int:cid>")
    def campaign(cid):
        c = _get_campaign(cid)
        show_auto = request.args.get("auto") == "1"
        tab = request.args.get("tab") or "replies"
        selected_intent = request.args.get("intent", "").strip().lower()

        auto_clause = "" if show_auto else " AND is_auto = 0"
        with db.get_conn() as conn:
            count_rows = conn.execute(
                f"SELECT intent, COUNT(*) as cnt FROM replies WHERE campaign_id = ?{auto_clause} GROUP BY intent",
                (cid,)
            ).fetchall()
            intent_counts = {r["intent"]: r["cnt"] for r in count_rows}
            total_replies_count = sum(intent_counts.values())

            query = f"SELECT * FROM replies WHERE campaign_id = ?{auto_clause}"
            params = [cid]
            if selected_intent in INTENT_CONFIG:
                query += " AND intent = ?"
                params.append(selected_intent)
            query += " ORDER BY received_at DESC"
            replies = [dict(r) for r in conn.execute(query, params)]

            clicks = [dict(r) for r in conn.execute(
                "SELECT * FROM contact_interactions WHERE campaign_id = ? AND interaction_type = 'click' ORDER BY interacted_at DESC",
                (cid,)
            )]

        return render_template(
            "campaign.html",
            c=c,
            replies=replies,
            clicks=clicks,
            show_auto=show_auto,
            active_tab=tab,
            selected_intent=selected_intent,
            intent_counts=intent_counts,
            total_replies_count=total_replies_count,
            intent_config=INTENT_CONFIG,
        )

    @app.post("/reply/<int:rid>/intent")
    @auth.login_required
    def set_reply_intent(rid):
        new_intent = request.form.get("intent", "").strip().lower()
        if new_intent in INTENT_CONFIG:
            db.update_reply_intent(rid, new_intent)
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return {"ok": True, "intent": new_intent}
        return redirect(request.referrer or url_for("index"))

    @app.post("/campaign/<int:cid>/update")
    @auth.admin_required
    def update_campaign(cid):
        with db.get_conn() as conn:
            conn.execute("UPDATE campaigns SET sent_count = ? WHERE id = ? AND source = 'gmail'",
                         (int(request.form.get("sent_count") or 0), cid))
        return redirect(url_for("campaign", cid=cid))

    @app.post("/campaign/<int:cid>/delete")
    @auth.admin_required
    def delete_campaign(cid):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM campaigns WHERE id = ?", (cid,))
        flash("Campaña eliminada.", "ok")
        return redirect(url_for("index"))

    @app.route("/campaign/<int:cid>/export.csv")
    def export_csv(cid):
        c = _get_campaign(cid)
        export_type = request.args.get("type", "replies")
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")

        with db.get_conn() as conn:
            if export_type == "clicks":
                rows = conn.execute(
                    "SELECT first_name, last_name, email, detail, interacted_at FROM contact_interactions "
                    "WHERE campaign_id = ? AND interaction_type = 'click' ORDER BY interacted_at DESC", (cid,)
                ).fetchall()
                w.writerow(["Nombre", "Apellido", "Email", "Enlace visitado", "Fecha y Hora"])
                for r in rows:
                    w.writerow([r["first_name"], r["last_name"], r["email"], r["detail"], _fecha(r["interacted_at"])])
                suffix = "_clics_interesados.csv"
            else:
                rows = conn.execute(
                    "SELECT from_name, from_email, received_at, subject, snippet, is_auto, intent FROM replies "
                    "WHERE campaign_id = ? ORDER BY received_at DESC", (cid,)
                ).fetchall()
                w.writerow(["Nombre", "Email", "Fecha", "Intención", "Asunto", "Respuesta", "Automática"])
                for r in rows:
                    intent_key = r["intent"] or "general"
                    intent_label = INTENT_CONFIG.get(intent_key, {}).get("short_label", intent_key.capitalize())
                    w.writerow([
                        r["from_name"],
                        r["from_email"],
                        _fecha(r["received_at"]),
                        intent_label,
                        r["subject"],
                        r["snippet"],
                        "Sí" if r["is_auto"] else "No"
                    ])
                suffix = "_respuestas.csv"

        filename = "".join(ch if ch.isalnum() else "_" for ch in c["name"]) + suffix
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.route("/connect-cc")
    @auth.admin_required
    def connect_constant_contact():
        from urllib.parse import quote
        client_id = os.getenv("CONSTANT_CONTACT_CLIENT_ID", "").strip() or Config.CONSTANT_CONTACT_CLIENT_ID
        if not client_id:
            flash("Configura CONSTANT_CONTACT_CLIENT_ID en las variables de entorno para conectar con 1 clic.", "error")
            return redirect(url_for("index"))

        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host_header = request.host
        redirect_uri = f"{scheme}://{host_header}/callback/constantcontact"
        scope = "campaign_data offline_access"
        state_token = "cc_auth_state_secure_123"
        auth_url = (
            f"https://authz.constantcontact.com/oauth2/default/v1/authorize"
            f"?client_id={quote(client_id, safe='')}"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&response_type=code"
            f"&scope={quote(scope, safe='')}"
            f"&state={state_token}"
        )
        return redirect(auth_url)

    @app.route("/callback/constantcontact")
    def callback_constant_contact():
        code = request.args.get("code")
        error = request.args.get("error_description") or request.args.get("error")
        if error:
            flash(f"Error de autorización en Constant Contact: {error}", "error")
            return redirect(url_for("index"))
        if not code:
            flash("No se recibió código de autorización de Constant Contact.", "error")
            return redirect(url_for("index"))

        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        redirect_uri = f"{scheme}://{request.host}/callback/constantcontact"
        try:
            constantcontact.exchange_code_for_tokens(code, redirect_uri)
            # Sincronización en segundo plano para respuesta instantánea (< 1 segundo)
            import threading
            threading.Thread(target=sync.sync_constantcontact_campaigns, daemon=True).start()
            flash("¡Constant Contact conectado con éxito! Las campañas se están sincronizando en segundo plano.", "ok")
        except Exception as exc:
            flash(f"Error al obtener token de Constant Contact: {exc}", "error")
        return redirect(url_for("index"))

    @app.post("/sync")
    @auth.admin_required
    def sync_now():
        for msg in sync.run_all():
            flash(msg, "error" if "ERROR" in msg else "ok")
        return redirect(request.referrer or url_for("index"))

