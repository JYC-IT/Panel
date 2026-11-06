"""Rutas para el panel de auditoría comercial de llamadas Close CRM."""
import requests
from flask import Response, abort, render_template, request
from connectors import close_crm
from services import audit_engine


def register_audit_routes(app):
    @app.route("/call-recording/<call_id>")
    def call_recording_proxy(call_id):
        """Proxy seguro para reproducir las grabaciones de Close CRM en el navegador."""
        auth_tuple = close_crm._get_auth()
        if not auth_tuple:
            abort(401)

        rec_url = f"https://api.close.com/api/v1/activity/call/{call_id}/recording/"
        try:
            r = requests.get(rec_url, auth=auth_tuple, stream=True, allow_redirects=True, timeout=20)
            if r.status_code == 200:
                return Response(
                    r.iter_content(chunk_size=8192),
                    content_type=r.headers.get("content-type", "audio/mpeg")
                )
            # Fallback si el objeto de llamada contiene una URL externa firmada
            call_resp = requests.get(f"https://api.close.com/api/v1/activity/call/{call_id}/", auth=auth_tuple, timeout=10)
            if call_resp.status_code == 200:
                c_data = call_resp.json()
                direct_url = c_data.get("recording_url") or c_data.get("voice_recording_url")
                if direct_url:
                    r2 = requests.get(direct_url, stream=True, timeout=20)
                    if r2.status_code == 200:
                        return Response(r2.iter_content(chunk_size=8192), content_type=r2.headers.get("content-type", "audio/mpeg"))
            abort(r.status_code if r.status_code in (404, 403) else 404)
        except Exception:
            abort(500)

    @app.route("/audit")
    def audit_view():
        all_users = close_crm.list_users()
        designated = [u for u in all_users if u.get("is_designated")]
        users_list = designated if designated else all_users

        # Seleccionar por defecto el primer comercial activo disponible
        default_uid = users_list[0]["id"] if users_list else ""
        selected_user_id = request.args.get("user_id") or default_uid

        from datetime import date, timedelta
        today = date.today()
        quick_dates = {
            "today": today.isoformat(),
            "yesterday": (today - timedelta(days=1)).isoformat(),
            "two_days_ago": (today - timedelta(days=2)).isoformat()
        }

        audit_date = request.args.get("audit_date") or quick_dates["yesterday"]
        force = request.args.get("refresh") == "1"
        audit_data = audit_engine.audit_agent_day(selected_user_id, audit_date, force_refresh=force)

        return render_template(
            "audit.html",
            audit=audit_data,
            users=users_list,
            selected_user_id=selected_user_id,
            quick_dates=quick_dates,
            active_page="audit"
        )

