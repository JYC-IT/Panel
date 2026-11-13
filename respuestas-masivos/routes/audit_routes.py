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

        # Probar URLs candidatas de audio en Close CRM
        # 1. URL directa canónica: https://api.close.com/call/<id>/recording/
        # 2. URL legada v1: https://api.close.com/api/v1/activity/call/<id>/recording/
        candidate_urls = [
            f"https://api.close.com/call/{call_id}/recording/",
            f"https://api.close.com/api/v1/activity/call/{call_id}/recording/",
        ]

        for url in candidate_urls:
            try:
                r = requests.get(url, auth=auth_tuple, stream=True, allow_redirects=True, timeout=15)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith(("audio/", "application/octet-stream", "video/")):
                    return Response(
                        r.iter_content(chunk_size=8192),
                        content_type=r.headers.get("content-type", "audio/mpeg"),
                        headers={
                            "Accept-Ranges": "bytes",
                            "Cache-Control": "public, max-age=3600"
                        }
                    )
            except Exception:
                continue

        # Fallback: consultar el objeto de llamada para obtener la URL firmada
        try:
            call_resp = requests.get(f"https://api.close.com/api/v1/activity/call/{call_id}/", auth=auth_tuple, timeout=10)
            if call_resp.status_code == 200:
                c_data = call_resp.json()
                direct_url = c_data.get("recording_url") or c_data.get("voice_recording_url")
                if direct_url and direct_url not in candidate_urls:
                    r2 = requests.get(
                        direct_url,
                        auth=auth_tuple if "close.com" in direct_url else None,
                        stream=True,
                        allow_redirects=True,
                        timeout=15
                    )
                    if r2.status_code == 200:
                        return Response(
                            r2.iter_content(chunk_size=8192),
                            content_type=r2.headers.get("content-type", "audio/mpeg"),
                            headers={"Accept-Ranges": "bytes"}
                        )
        except Exception:
            pass

        # Respuesta amigable si la llamada no cuenta con audio procesado en Close CRM
        return (
            """<!doctype html>
            <html lang="es">
            <head><meta charset="utf-8"><title>Audio No Disponible</title>
            <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;}a{color:#38bdf8;text-decoration:none;}</style>
            </head>
            <body>
            <h2 style="color:#f59e0b;">Audio no disponible en Close CRM</h2>
            <p>La llamada seleccionada no tiene archivo de grabación procesado o expiró en Close CRM.</p>
            <p style="margin-top:20px;"><a href="javascript:window.close()">← Cerrar ventana</a></p>
            </body></html>""",
            404,
            {"Content-Type": "text/html; charset=utf-8"}
        )

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

