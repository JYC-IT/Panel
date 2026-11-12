"""Rutas para reportes semanales, KPIs comerciales y rendimiento."""
from datetime import date, timedelta
from flask import flash, redirect, render_template, request, url_for
import auth
import db
from connectors import close_crm
from services import report_performance


def register_report_routes(app):
    @app.route("/performance")
    @auth.login_required
    def performance_view():
        if request.args.get("view") == "classic":
            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")
            report = report_performance.get_performance_report(start_date, end_date)

            from datetime import date, timedelta
            today = date.today()
            presets = {
                "last_7": {"start": (today - timedelta(days=7)).isoformat(), "end": today.isoformat(), "label": "7 días"},
                "last_30": {"start": (today - timedelta(days=30)).isoformat(), "end": today.isoformat(), "label": "30 días"},
                "this_month": {"start": today.replace(day=1).isoformat(), "end": today.isoformat(), "label": "Este Mes"},
                "last_month": {
                    "start": (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat(),
                    "end": (today.replace(day=1) - timedelta(days=1)).isoformat(),
                    "label": "Mes Anterior"
                }
            }

            return render_template(
                "performance.html",
                report=report,
                presets=presets,
                active_page="performance"
            )

        # Por defecto redirige al nuevo panel comercial requerido por Hernán
        return redirect(url_for("commercial_dashboard_view", **request.args))

    @app.route("/performance/export.csv")
    @auth.login_required
    def export_performance_csv():
        """Exporta el reporte analítico comercial a formato CSV ejecutivo."""
        if request.args.get("view") != "classic":
            return redirect(url_for("export_commercial_csv", **request.args))
        import csv
        import io
        from flask import Response
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        report = report_performance.get_performance_report(start_date, end_date)
        if not report or not report.get("agents"):
            flash("No hay datos para exportar en el rango seleccionado.", "err")
            return redirect(url_for("performance_view"))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Asesor Comercial", "Email", "Llamadas Salientes", "Duracion Promedio (min)",
            "KPs Conectados", "Tasa Efectividad (%)", "Emails Enviados", "Emails Respondidos",
            "Tasa Resp. Email (%)", "SMS Enviados", "Leads Contactados", "Reuniones Agendadas",
            "Oportunidades Activas", "Valor Pipeline ($USD)", "Opps Estancadas (>7d)",
            "Tareas Pendientes", "Tareas Vencidas"
        ])
        for a in report["agents"]:
            writer.writerow([
                a.get("name"),
                a.get("email"),
                a.get("calls", 0),
                a.get("avg_call_duration_min", 0),
                a.get("kps", 0),
                f"{a.get('effectiveness', 0)}%",
                a.get("emails_sent", 0),
                a.get("emails_replied", 0),
                f"{a.get('email_reply_rate', 0)}%",
                a.get("sms_sent", 0),
                a.get("leads_contacted", 0),
                a.get("meetings", 0),
                a.get("active_opps", 0),
                a.get("pipeline_value", 0),
                a.get("stalled_count", 0),
                a.get("open_tasks", 0),
                a.get("overdue_tasks", 0),
            ])
        output.seek(0)
        filename = f"jyc_performance_{report['start_date']}_{report['end_date']}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    @app.route("/weekly-report")
    def weekly_report():
        since = request.args.get("since") or (date.today() - timedelta(days=42)).isoformat()
        selected_week = request.args.get("week", type=int)
        business_summary, business_totals = db.get_business_summary(since_date=since)
        weekly_kpis = db.get_weekly_kpis(limit=6)

        # Close CRM: disponibilidad, asesores y desglose individual
        close_available = close_crm.is_available()
        all_users = close_crm.list_users() if close_available else []
        designated_agents = [u for u in all_users if u.get("is_designated")]
        agent_kpis = db.get_agent_kpis(selected_week)

        # Preparamos estructuras de datos para las gráficas interactivas con Chart.js
        chart_data = {
            "weeks": [w["week_label"] for w in weekly_kpis],
            "date_ranges": [w["date_range"] for w in weekly_kpis],
            "am_calls": [w["am_calls"] for w in weekly_kpis],
            "pm_calls": [w["pm_calls"] for w in weekly_kpis],
            "total_calls": [w["total_calls"] for w in weekly_kpis],
            "calls_goal": [w["calls_goal"] for w in weekly_kpis],
            "kps": [w["kps"] for w in weekly_kpis],
            "kps_goal": [w["kps_goal"] for w in weekly_kpis],
            "effectiveness": [w["effectiveness_rate"] for w in weekly_kpis],
            "outreach_cc": [w["outreach_emails_cc"] for w in weekly_kpis],
            "outreach_instantly": [w["outreach_emails_instantly"] for w in weekly_kpis],
            "outreach_sms": [w["outreach_sms"] for w in weekly_kpis],
            "opens": [w["opens_count"] for w in weekly_kpis],
            "clicks_count": [w.get("clicks_count", 0) for w in weekly_kpis],
            "click_rate": [w["click_rate"] for w in weekly_kpis],
            "notes": [w["notes"] or "" for w in weekly_kpis],
            # Negocios
            "business_labels": [b["business"] for b in business_summary],
            "business_sent": [b["sent"] for b in business_summary],
            "business_opens": [b["opens"] for b in business_summary],
            "business_clicks": [b["clicks"] for b in business_summary],
            "business_replies": [b["replies"] for b in business_summary],
            "business_ventas": [b["ventas"] for b in business_summary],
            "business_compras": [b["compras"] for b in business_summary],
        }

        return render_template(
            "weekly_report.html",
            business_summary=business_summary,
            business_totals=business_totals,
            weekly_kpis=weekly_kpis,
            chart_data=chart_data,
            active_page="weekly_report",
            since=since,
            close_available=close_available,
            designated_agents=designated_agents,
            all_users=all_users,
            agent_kpis=agent_kpis,
            selected_week=selected_week or (agent_kpis[0]["week_number"] if agent_kpis else 24),
        )

    @app.post("/weekly-report/sync-close")
    @auth.admin_required
    def sync_close_crm_route():
        if not close_crm.is_available():
            flash("Close CRM API Key no está configurada.", "err")
            return redirect(url_for("weekly_report"))

        week_number = int(request.form.get("week_number") or 24)
        week_label = request.form.get("week_label") or f"Week {week_number}"
        start_date = request.form.get("start_date") or "2026-10-12"
        end_date = request.form.get("end_date") or "2026-10-16"
        date_range = request.form.get("date_range") or f"{start_date} a {end_date}"
        selected_user_ids = request.form.getlist("user_ids")
        notes = request.form.get("notes", "").strip()

        try:
            res = close_crm.fetch_week_activity(start_date, end_date, selected_user_ids)
            if not res:
                flash("No se pudieron obtener métricas de Close CRM para las fechas indicadas.", "err")
                return redirect(url_for("weekly_report"))

            close_crm_calls = res["total_calls"]
            ringcentral_calls = int(request.form.get("ringcentral_calls") or 0)
            total_calls = close_crm_calls + ringcentral_calls

            # Desglose AM vs PM: si hay llamadas de RingCentral, distribuirlas en proporción
            am_crm = res["am_calls"]
            pm_crm = res["pm_calls"]
            if ringcentral_calls > 0:
                ratio_am = am_crm / close_crm_calls if close_crm_calls else 0.5
                rc_am = round(ringcentral_calls * ratio_am)
                rc_pm = ringcentral_calls - rc_am
                am_calls = am_crm + rc_am
                pm_calls = pm_crm + rc_pm
            else:
                am_calls = am_crm
                pm_calls = pm_crm

            kps = res["kps"]
            effectiveness_rate = round(100.0 * kps / total_calls, 2) if total_calls else 0.0

            with db.get_conn() as conn:
                existing = conn.execute(
                    "SELECT notes FROM weekly_team_kpis WHERE week_number = ?", (week_number,)
                ).fetchone()
                final_notes = notes if notes else ((existing["notes"] or "") if existing else "")

                conn.execute(
                    """INSERT INTO weekly_team_kpis
                       (week_number, week_label, date_range, am_calls, pm_calls, close_crm_calls, ringcentral_calls,
                        total_calls, calls_goal, kps, kps_goal, effectiveness_rate, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2000, ?, 125, ?, ?)
                       ON CONFLICT(week_number) DO UPDATE SET
                           week_label=excluded.week_label,
                           date_range=excluded.date_range,
                           am_calls=excluded.am_calls,
                           pm_calls=excluded.pm_calls,
                           close_crm_calls=excluded.close_crm_calls,
                           ringcentral_calls=excluded.ringcentral_calls,
                           total_calls=excluded.total_calls,
                           kps=excluded.kps,
                           effectiveness_rate=excluded.effectiveness_rate,
                           notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE weekly_team_kpis.notes END""",
                    (week_number, week_label, date_range, am_calls, pm_calls, close_crm_calls, ringcentral_calls, total_calls, kps, effectiveness_rate, final_notes),
                )

            # Guardar métricas individuales por asesor
            db.save_agent_kpis(week_number, res["per_user"])

            rc_msg = f" + {ringcentral_calls} RingCentral" if ringcentral_calls else ""
            flash(f"✅ {week_label}: {total_calls} llamadas totales ({close_crm_calls} Close CRM{rc_msg} · {am_calls} AM / {pm_calls} PM), {kps} KPs.", "ok")
        except Exception as e:
            flash(f"Error sincronizando con Close CRM: {e}", "err")

        return redirect(url_for("weekly_report", week=week_number))

    @app.post("/weekly-report/save-week")
    @auth.admin_required
    def save_weekly_kpi():
        week_number = int(request.form.get("week_number"))
        week_label = request.form.get("week_label") or f"Week {week_number}"
        date_range = request.form.get("date_range") or ""
        am_calls = int(request.form.get("am_calls") or 0)
        pm_calls = int(request.form.get("pm_calls") or 0)
        close_crm_calls = int(request.form.get("close_crm_calls") or (am_calls + pm_calls))
        ringcentral_calls = int(request.form.get("ringcentral_calls") or 0)
        total_calls = am_calls + pm_calls
        calls_goal = int(request.form.get("calls_goal") or 2000)
        kps = int(request.form.get("kps") or 0)
        kps_goal = int(request.form.get("kps_goal") or 125)
        effectiveness_rate = round(100.0 * kps / total_calls, 2) if total_calls else 0.0
        notes = request.form.get("notes", "").strip()
        outreach_emails_cc = int(request.form.get("outreach_emails_cc") or 0)
        outreach_emails_instantly = int(request.form.get("outreach_emails_instantly") or 0)
        outreach_sms = int(request.form.get("outreach_sms") or 0)
        total_outreach = outreach_emails_cc + outreach_emails_instantly + outreach_sms
        opens_count = int(request.form.get("opens_count") or 0)
        click_rate = float(request.form.get("click_rate") or 0.0)

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO weekly_team_kpis
                   (week_number, week_label, date_range, am_calls, pm_calls, close_crm_calls, ringcentral_calls,
                    total_calls, calls_goal, kps, kps_goal, effectiveness_rate, notes, outreach_emails_cc,
                    outreach_emails_instantly, outreach_sms, total_outreach, opens_count, click_rate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(week_number) DO UPDATE SET
                       week_label=excluded.week_label,
                       date_range=excluded.date_range,
                       am_calls=excluded.am_calls,
                       pm_calls=excluded.pm_calls,
                       close_crm_calls=excluded.close_crm_calls,
                       ringcentral_calls=excluded.ringcentral_calls,
                       total_calls=excluded.total_calls,
                       calls_goal=excluded.calls_goal,
                       kps=excluded.kps,
                       kps_goal=excluded.kps_goal,
                       effectiveness_rate=excluded.effectiveness_rate,
                       notes=excluded.notes,
                       outreach_emails_cc=excluded.outreach_emails_cc,
                       outreach_emails_instantly=excluded.outreach_emails_instantly,
                       outreach_sms=excluded.outreach_sms,
                       total_outreach=excluded.total_outreach,
                       opens_count=excluded.opens_count,
                       click_rate=excluded.click_rate""",
                (week_number, week_label, date_range, am_calls, pm_calls, close_crm_calls, ringcentral_calls,
                 total_calls, calls_goal, kps, kps_goal, effectiveness_rate, notes, outreach_emails_cc,
                 outreach_emails_instantly, outreach_sms, total_outreach, opens_count, click_rate),
            )
        flash(f"Datos de {week_label} guardados correctamente.", "ok")
        return redirect(url_for("weekly_report"))

    @app.post("/weekly-report/update-outreach")
    @auth.admin_required
    def update_weekly_outreach():
        week_number = int(request.form.get("week_number") or 25)
        cc = int(request.form.get("outreach_emails_cc") or 0)
        instantly = int(request.form.get("outreach_emails_instantly") or 0)
        sms = int(request.form.get("outreach_sms") or 0)
        tot = cc + instantly + sms
        opens = int(request.form.get("opens_count") or 0)
        clicks_count = int(request.form.get("clicks_count") or request.form.get("clicks") or 0)
        click_rate = float(request.form.get("click_rate") or 0.0)

        with db.get_conn() as conn:
            conn.execute(
                """UPDATE weekly_team_kpis
                   SET outreach_emails_cc = ?,
                       outreach_emails_instantly = ?,
                       outreach_sms = ?,
                       total_outreach = ?,
                       opens_count = ?,
                       clicks_count = ?,
                       click_rate = ?
                   WHERE week_number = ?""",
                (cc, instantly, sms, tot, opens, clicks_count, click_rate, week_number),
            )
        flash(f"Envíos y métricas de la Semana {week_number} actualizados (Instantly: {instantly:,}, CC: {cc:,}, SMS: {sms:,}).", "ok")
        return redirect(url_for("weekly_report"))

