"""Rutas de autenticación, control de sesiones y accesos."""
from flask import flash, g, redirect, render_template, request, session, url_for
import auth


def register_auth_routes(app):
    @app.route("/login", methods=["GET", "POST"])
    def login():
        # Si ya está autenticado y solo abre GET /login, continuar al panel principal
        if request.method == "GET" and getattr(g, "user", None):
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            next_url = request.form.get("next") or url_for("index")

            user = auth.verify(username, password)
            if user:
                session.clear()
                session["user_id"] = user["id"]
                token = auth.generate_auth_token(user["id"])
                flash(f"¡Bienvenido, {user['name']}!", "ok")

                # Limpiar cualquier auth_token previo en next_url y adjuntar el token del usuario nuevo
                from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
                parsed = urlparse(next_url)
                clean_qs = [(k, v) for k, v in parse_qsl(parsed.query) if k != "auth_token"]
                clean_qs.append(("auth_token", token))
                target = urlunparse(parsed._replace(query=urlencode(clean_qs)))
                resp = redirect(target)
                resp.set_cookie("auth_token", token, max_age=86400 * 30, httponly=True, samesite="Lax")
                return resp
            else:
                flash("Usuario o contraseña incorrectos.", "error")

        next_url = request.args.get("next") or url_for("index")
        return render_template("login.html", next_url=next_url)

    @app.route("/preview-login")
    def preview_login():
        """Acceso 1-clic directo para extensiones de previsualización (VS Code Mobile View / Simple Browser)."""
        user = auth.get_user(1)  # Usuario francisco (admin)
        if user and user["active"]:
            session["user_id"] = user["id"]
            token = auth.generate_auth_token(user["id"])
            flash(f"Modo Vista Previa activado: Sesión iniciada como {user['name']}.", "ok")
            resp = redirect(url_for("index", auth_token=token))
            resp.set_cookie("auth_token", token, max_age=86400 * 30, httponly=True, samesite="Lax")
            return resp
        return redirect(url_for("login"))

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Has cerrado sesión.", "ok")
        resp = redirect(url_for("login", logged_out="1"))
        resp.delete_cookie("auth_token")
        return resp

