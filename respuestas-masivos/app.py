"""Panel web: ¿Quién responde nuestros masivos?

Ejecutar:  python app.py   ->  http://localhost:5000
"""
from flask import Flask

from config import Config
import auth
import db
from routes import register_all_routes
from services import sync


def create_app():
    """Fábrica de la aplicación Flask."""
    application = Flask(__name__)
    application.secret_key = Config.SECRET_KEY

    # Filtros de plantillas Jinja2
    @application.template_filter("fecha")
    def fecha(value):
        return (value or "")[:16].replace("T", " ")

    # Inicializar base de datos y usuario admin inicial si aplica
    db.init_db()
    auth.bootstrap_admin()

    # Inicializar subsistemas
    auth.init_app(application)
    register_all_routes(application)

    # Iniciar sincronizador automático en segundo plano (para Gunicorn en Render y local)
    sync.start_scheduler()

    return application


app = create_app()

if __name__ == "__main__":
    import os
    db.init_db()
    is_debug = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")

    # Si el auto-recargador de Werkzeug está activo, arrancar el scheduler solo en el hilo principal de trabajo
    if not is_debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        sync.start_scheduler()

    print(f"\n  Panel disponible en  http://localhost:{Config.PORT}\n")
    app.run(host=Config.HOST, port=Config.PORT, debug=is_debug, use_reloader=is_debug)
