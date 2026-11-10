"""Paquete de rutas y controladores web divididos por dominio."""
from .auth_routes import register_auth_routes
from .audit_routes import register_audit_routes
from .campaign_routes import register_campaign_routes
from .error_routes import register_error_handlers
from .report_routes import register_report_routes
from .commercial_routes import register_commercial_routes


def register_all_routes(app):
    """Registra todos los controladores de rutas y manejadores de error en la app Flask."""
    register_auth_routes(app)
    register_audit_routes(app)
    register_report_routes(app)
    register_commercial_routes(app)
    register_campaign_routes(app)
    register_error_handlers(app)


__all__ = ["register_all_routes"]

