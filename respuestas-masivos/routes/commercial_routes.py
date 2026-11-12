"""Rutas del Panel Comercial (Hernán) para seguimiento de llamadas, KPs, metas y pipelines."""
import csv
import io
from datetime import date, timedelta
from flask import render_template, request, Response, redirect, url_for, flash, g
import auth
from services import commercial_dashboard


def _include_all_commercials():
    """Admin ve todos los comerciales; lectores (ej. Hernán) ven solo su equipo asignado."""
    return bool(getattr(g, "user", None) and g.user.get("role") == "admin")


def get_date_presets():
    """Genera presets de fechas comunes para filtros rápidos."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # Esta semana (Lunes a hoy)
    start_of_week = today - timedelta(days=today.weekday())
    
    # Semana pasada (Lunes a Viernes pasado)
    start_last_week = start_of_week - timedelta(days=7)
    end_last_week = start_last_week + timedelta(days=4)
    
    # Este mes (Día 1 a hoy)
    start_of_month = today.replace(day=1)

    return {
        "today": {
            "start": today.isoformat(),
            "end": today.isoformat(),
            "label": "Hoy"
        },
        "yesterday": {
            "start": yesterday.isoformat(),
            "end": yesterday.isoformat(),
            "label": "Ayer"
        },
        "this_week": {
            "start": start_of_week.isoformat(),
            "end": today.isoformat(),
            "label": "Esta Semana"
        },
        "last_week": {
            "start": start_last_week.isoformat(),
            "end": end_last_week.isoformat(),
            "label": "Semana Pasada"
        },
        "this_month": {
            "start": start_of_month.isoformat(),
            "end": today.isoformat(),
            "label": "Este Mes"
        }
    }


def register_commercial_routes(app):
    """Registra los endpoints para el Panel Comercial de Hernán."""

    @app.route("/commercial-dashboard")
    @app.route("/comerciales")
    @auth.login_required
    def commercial_dashboard_view():
        today_iso = date.today().isoformat()
        start_date = request.args.get("start_date") or today_iso
        end_date = request.args.get("end_date") or today_iso
        force_refresh = request.args.get("refresh") in ("1", "true", "True")

        data = commercial_dashboard.get_commercial_dashboard_data(
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
            include_all_commercials=_include_all_commercials(),
        )

        presets = get_date_presets()

        return render_template(
            "commercial_dashboard.html",
            data=data,
            presets=presets,
            active_page="commercial_dashboard"
        )

    @app.route("/commercial-dashboard/export.csv")
    @auth.login_required
    def export_commercial_csv():
        today_iso = date.today().isoformat()
        start_date = request.args.get("start_date") or today_iso
        end_date = request.args.get("end_date") or today_iso

        data = commercial_dashboard.get_commercial_dashboard_data(
            start_date=start_date,
            end_date=end_date,
            include_all_commercials=_include_all_commercials(),
        )

        if not data or not data.get("commercials"):
            flash("No hay datos disponibles para exportar en este rango.", "err")
            return redirect(url_for("commercial_dashboard_view"))

        output = io.StringIO()
        writer = csv.writer(output)

        # Encabezados
        writer.writerow([
            "Asesor Comercial",
            "Email",
            "Horario Asignado",
            "Primera Llamada (Hora)",
            "Ultima Llamada (Hora)",
            "Llamadas Salientes",
            "Llamadas Entrantes",
            "Total Llamadas",
            "Gross Dial Time",
            "Live KP Talk (Llamada)",
            "EKP (#EKP)",
            "TKP (#TKP)",
            "Total KPs",
            "Efectividad (%)",
            "Emails Enviados",
            "Oportunidades Total",
            "Opps Sales Pipeline",
            "Opps Purchase Pipeline",
            "Tareas Set (Creadas)",
            "Tareas Done (Completadas)",
            "Meta Llamadas Periodo",
            "% Cumpl. Llamadas",
            "Meta KPs Periodo",
            "% Cumpl. KPs",
            "Meta KP Llamadas Periodo",
            "% Cumpl. KP Llamadas",
            "Estado Metas",
            "Alertas Inactividad (>=10m)",
            "Pausa Maxima Inactiva",
            "Live KP Verificados IA",
            "EKP Verificados IA",
            "TKP Verificados IA"
        ])

        summary = data["summary"]
        for c in data["commercials"]:
            writer.writerow([
                c["name"],
                c["email"],
                c.get("schedule_label", "-"),
                c.get("first_call_time", "-"),
                c.get("last_call_time", "-"),
                c["calls_out"],
                c["calls_in"],
                c["calls_total"],
                c["gross_dial_time"]["human"],
                c["live_kp"],
                c["ekp"],
                c["tkp"],
                c["total_kps"],
                f"{c['effectiveness']}%",
                c["emails_sent"],
                c["opps_total"],
                c["opps_sales"],
                c["opps_purchase"],
                c["tasks_set"],
                c["tasks_done"],
                summary["period_target_calls_per_agent"],
                f"{c['calls_pct']}%",
                summary["period_target_kps_per_agent"],
                f"{c['kps_pct']}%",
                summary["period_target_call_kps_per_agent"],
                f"{c['call_kps_pct']}%",
                c["status_goal"],
                c.get("inactivity_count", 0),
                c.get("inactivity_max_human", "-"),
                c.get("live_kp_verified", 0),
                c.get("ekp_verified", 0),
                c.get("tkp_verified", 0),
            ])

        output.seek(0)
        filename = f"panel_comercial_{start_date}_{end_date}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    @app.route("/commercial-dashboard/inactivity-export.csv")
    @auth.login_required
    def export_inactivity_csv():
        today_iso = date.today().isoformat()
        start_date = request.args.get("start_date") or today_iso
        end_date = request.args.get("end_date") or today_iso

        data = commercial_dashboard.get_commercial_dashboard_data(
            start_date=start_date,
            end_date=end_date,
            include_all_commercials=_include_all_commercials(),
        )

        inactivity_records = data.get("inactivity_records", []) if data else []
        if not inactivity_records:
            flash("No hay alertas de inactividad registradas en este periodo.", "info")
            return redirect(url_for("commercial_dashboard_view", start_date=start_date, end_date=end_date))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Asesor Comercial",
            "Fecha",
            "Minutos Inactivo Laboral",
            "Tiempo Inactivo Laboral",
            "Minutos Reloj Total",
            "Minutos Descontados (Almuerzo/Pausa)",
            "Hora Fin Llamada Anterior",
            "Hora Inicio Siguiente Llamada",
            "Tipo de Pausa",
            "Severidad",
            "Telefono Llamada Anterior",
            "Lead Llamada Anterior",
            "Telefono Siguiente Llamada",
            "Lead Siguiente Llamada"
        ])

        for r in inactivity_records:
            writer.writerow([
                r["user_name"],
                r["date"],
                r["gap_minutes"],
                r["gap_human"],
                r.get("raw_minutes", r["gap_minutes"]),
                r.get("discounted_minutes", 0.0),
                r["from_time"],
                r["to_time"],
                r["pause_type"],
                r["severity"],
                r["phone_before"],
                r["lead_before"],
                r["phone_after"],
                r["lead_after"]
            ])

        output.seek(0)
        filename = f"alertas_inactividad_{start_date}_{end_date}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    @app.route("/commercial-dashboard/discipline-export.csv")
    @auth.login_required
    def export_discipline_csv():
        today_iso = date.today().isoformat()
        start_date = request.args.get("start_date") or today_iso
        end_date = request.args.get("end_date") or today_iso

        data = commercial_dashboard.get_commercial_dashboard_data(
            start_date=start_date,
            end_date=end_date,
            include_all_commercials=_include_all_commercials(),
        )

        records = data.get("discipline_records", []) if data else []
        if not records:
            flash("No hay registros de jornada en este periodo.", "info")
            return redirect(url_for("commercial_dashboard_view", start_date=start_date, end_date=end_date))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Asesor Comercial",
            "Fecha",
            "Horario Programado",
            "Entrada Programada",
            "1ra Llamada Mañana",
            "Estado Entrada",
            "Almuerzo / Pausa Programada",
            "Última Llamada Mañana",
            "Estado Salida Almuerzo",
            "Retorno Almuerzo Programado",
            "1ra Llamada Tarde",
            "Estado Retorno Almuerzo",
            "Salida Fin de Turno",
            "Última Llamada Tarde",
            "Estado Fin de Turno",
            "Llamadas AM",
            "Llamadas PM",
            "Total Llamadas Día"
        ])

        for r in records:
            f_am = r.get("first_am", {})
            l_am = r.get("last_am", {})
            f_pm = r.get("first_pm", {})
            l_pm = r.get("last_pm", {})

            writer.writerow([
                r["user_name"],
                r["date"],
                r["schedule_label"],
                r["scheduled_entry"],
                f_am.get("time", "-"),
                f_am.get("label", "-"),
                r["scheduled_lunch"],
                l_am.get("time", "-"),
                l_am.get("label", "-"),
                "1:00 PM",
                f_pm.get("time", "-"),
                f_pm.get("label", "-"),
                r["scheduled_exit"],
                l_pm.get("time", "-"),
                l_pm.get("label", "-"),
                r["calls_am"],
                r["calls_pm"],
                r["calls_total"]
            ])

        output.seek(0)
        filename = f"control_horarios_jornada_{start_date}_{end_date}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    @app.route("/commercial-dashboard/ai-audit-export.csv")
    @auth.login_required
    def export_ai_audit_csv():
        today_iso = date.today().isoformat()
        start_date = request.args.get("start_date") or today_iso
        end_date = request.args.get("end_date") or today_iso

        data = commercial_dashboard.get_commercial_dashboard_data(
            start_date=start_date,
            end_date=end_date,
            include_all_commercials=_include_all_commercials(),
        )

        call_audits = data.get("ai_call_audits", []) if data else []
        tag_audits = data.get("ai_tag_audits", []) if data else []
        if not call_audits and not tag_audits:
            flash("No hay registros de auditoria IA en este periodo.", "info")
            return redirect(url_for("commercial_dashboard_view", start_date=start_date, end_date=end_date))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Tipo Auditoria",
            "Asesor Comercial",
            "Lead",
            "Fecha",
            "Duracion (seg)",
            "Veredicto IA",
            "Categoria",
            "Puntaje (0-100)",
            "Motivo / Analisis",
            "Evidencia CRM / Notetaker",
            "Motor"
        ])

        for c in call_audits:
            writer.writerow([
                "Talked to KP (Llamada)",
                c.get("user_name", ""),
                c.get("lead_name", c.get("lead_id", "")),
                c.get("date", ""),
                c.get("duration", 0),
                c.get("verdict", ""),
                c.get("category", ""),
                c.get("score", 0),
                c.get("reason", ""),
                c.get("summary") or c.get("evidence", ""),
                c.get("model_used", ""),
            ])

        for t in tag_audits:
            writer.writerow([
                f"#{t.get('type', 'KP')} (Nota)",
                t.get("user_name", ""),
                t.get("lead_name", t.get("lead_id", "")),
                t.get("date", ""),
                "-",
                t.get("verdict", ""),
                t.get("category", ""),
                t.get("score", 0),
                t.get("reason", ""),
                t.get("evidence") or t.get("text", ""),
                t.get("model_used", ""),
            ])

        output.seek(0)
        filename = f"auditoria_ia_kp_{start_date}_{end_date}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
