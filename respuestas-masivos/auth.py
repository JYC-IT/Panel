"""Usuarios del panel: inicio de sesión y roles.

Roles:
  - admin  : puede todo (sincronizar, editar, borrar, conectar Constant Contact, gestionar usuarios).
  - lector : solo puede ver, filtrar y exportar CSV.
"""
import os
from functools import wraps

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import db

ROLES = ("admin", "lector")

# Rutas que no requieren sesión iniciada
PUBLIC_ENDPOINTS = {"login", "static", "preview_login"}


def get_serializer():
    """Generador de tokens seguros para previsualización."""
    return URLSafeTimedSerializer(current_app.secret_key)


def generate_auth_token(user_id):
    """Crea un token firmado válido para entornos sin soporte de cookies (como iframes de VS Code)."""
    s = get_serializer()
    return s.dumps({"user_id": user_id}, salt="preview-auth")


def verify_auth_token(token, max_age=86400 * 30):
    """Verifica y extrae el user_id de un token firmado."""
    if not token:
        return None
    s = get_serializer()
    try:
        data = s.loads(token, salt="preview-auth", max_age=max_age)
        return data.get("user_id")
    except Exception:
        return None


def create_user(username, name, password, role="lector"):
    username = (username or "").strip().lower()
    if not username or not password:
        raise ValueError("Usuario y contraseña son obligatorios.")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if role not in ROLES:
        raise ValueError(f"Rol inválido: {role}")
    with db.get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            raise ValueError(f"El usuario «{username}» ya existe.")
        conn.execute(
            "INSERT INTO users (username, name, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, (name or username).strip(), generate_password_hash(password), role),
        )


def set_password(user_id, password):
    if len(password or "") < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    with db.get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user_id))


def get_user(user_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_users():
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY role, name")]


def verify(username, password):
    """Devuelve el usuario si las credenciales son válidas y está activo; si no, None.
    Acepta tanto el nombre de usuario ('francisco') como el correo ('francisco@...').
    """
    raw_user = (username or "").strip().lower()
    user_handle = raw_user.split("@")[0].strip()
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM users 
               WHERE username = ? 
                  OR username = ?
                  OR (? IN ('jcordoba', 'juancordoba') AND username IN ('jcordoba', 'juancordoba'))
                  OR (? IN ('julian', 'julianprado', 'jprado', 'jp') AND username IN ('julian', 'julianprado', 'jprado', 'jp'))""",
            (raw_user, user_handle, user_handle, user_handle)
        ).fetchone()
        if not row or not row["active"] or not check_password_hash(row["password_hash"], password or ""):
            return None
        try:
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        except Exception:
            pass
    return dict(row)


def bootstrap_admin():
    """Garantiza la inicialización automática de los usuarios oficiales en Render y producción."""
    with db.get_conn() as conn:
        # 1. Francisco (Administrador)
        f_row = conn.execute("SELECT id FROM users WHERE username = 'francisco'").fetchone()
        if not f_row:
            create_user("francisco", "Francisco", "Jyc2026*Admin", "admin")
            print("  Usuario admin «francisco» inicializado.")
        else:
            set_password(f_row["id"], "Jyc2026*Admin")

        # 2. Hernan (Lector)
        h_row = conn.execute("SELECT id FROM users WHERE username = 'hernan'").fetchone()
        if not h_row:
            create_user("hernan", "Hernán", "Jyc2026*Hernan", "lector")
            print("  Usuario lector «hernan» inicializado.")
        else:
            set_password(h_row["id"], "Jyc2026*Hernan")

        # 3. Juan Cordoba (Lector con acceso completo a todos los comerciales)
        jc_row = conn.execute("SELECT id FROM users WHERE username IN ('juancordoba', 'jcordoba')").fetchone()
        if not jc_row:
            create_user("juancordoba", "Juan Cordoba", "Jyc2026*Cordoba", "lector")
            print("  Usuario lector «juancordoba» inicializado.")
        else:
            set_password(jc_row["id"], "Jyc2026*Cordoba")

        # 4. Julian Prado (Lector con acceso a comerciales)
        jp_row = conn.execute("SELECT id FROM users WHERE username IN ('julianprado', 'julian', 'jprado', 'jp')").fetchone()
        if not jp_row:
            create_user("julianprado", "Julian Prado", "Jyc2026*Julian", "lector")
            print("  Usuario lector «julianprado» inicializado.")
        else:
            set_password(jp_row["id"], "Jyc2026*Julian")

        # 3. Soporte opcional desde variables de entorno si se configuran
        env_user = os.getenv("ADMIN_USERNAME", "").strip()
        env_pass = os.getenv("ADMIN_PASSWORD", "").strip()
        if env_user and env_pass:
            e_row = conn.execute("SELECT id FROM users WHERE username = ?", (env_user,)).fetchone()
            if not e_row:
                create_user(env_user, os.getenv("ADMIN_NAME", env_user), env_pass, "admin")


def init_app(app):
    """Registra la verificación de sesión en cada petición y expone el usuario a las plantillas."""

    @app.before_request
    def _require_login():
        g.user = None
        g.auth_token = None
        uid = session.get("user_id")

        # Fallback para webviews / extensiones iframe de VS Code (Mobile View, Simple Browser, etc.)
        # donde Chromium bloquea las cookies de terceros de localhost en iframes.
        # Nunca auto-autenticar con token viejo cuando el usuario está enviando un login nuevo o cerrando sesión.
        is_auth_switch = request.endpoint in ("logout", "preview_login") or (
            request.endpoint == "login" and request.method == "POST"
        )
        token = None if is_auth_switch else (
            request.args.get("auth_token")
            or request.headers.get("X-Auth-Token")
            or request.cookies.get("auth_token")
            or (request.form.get("auth_token") if request.method == "POST" else None)
        )
        if not uid and token:
            token_uid = verify_auth_token(token)
            if token_uid:
                uid = token_uid
                try:
                    session["user_id"] = uid
                except Exception:
                    pass

        if uid:
            user = get_user(uid)
            if user and user["active"]:
                g.user = user
                try:
                    g.auth_token = generate_auth_token(user["id"])
                except Exception:
                    g.auth_token = None
            else:
                session.clear()

        if g.user is None and request.endpoint not in PUBLIC_ENDPOINTS:
            if request.method == "GET":
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return redirect(url_for("login"))

    @app.context_processor
    def _inject_user():
        user = getattr(g, "user", None)
        token = getattr(g, "auth_token", None)
        return {
            "current_user": user,
            "is_admin": bool(user and user["role"] == "admin"),
            "current_auth_token": token,
        }


def login_required(view):
    """Garantiza que el usuario esté autenticado."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    """Restringe una ruta a usuarios con rol admin."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.get("user") or g.user["role"] != "admin":
            if request.method == "GET":
                flash("Esa acción es solo para administradores.", "error")
                return redirect(url_for("index"))
            abort(403)
        return view(*args, **kwargs)

    return wrapper
