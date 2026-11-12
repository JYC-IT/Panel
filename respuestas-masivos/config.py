"""Configuración centralizada de la aplicación y variables de entorno."""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)


class Config:
    """Configuración general del sistema."""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave")
    HOST = os.getenv("HOST", "0.0.0.0" if (os.getenv("PORT") or os.getenv("RENDER")) else "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))
    
    # Sincronización
    SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "15"))
    LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "42"))
    
    # Base de datos
    DB_PATH = os.path.join(BASE_DIR, "data.db")
    
    # Close CRM
    CLOSE_CRM_API_KEY = (os.getenv("CLOSE_CRM_API_KEY") or "").strip()
    
    # Constant Contact
    CONSTANT_CONTACT_CLIENT_ID = os.getenv("CONSTANT_CONTACT_CLIENT_ID", "").strip()
    CONSTANT_CONTACT_CLIENT_SECRET = os.getenv("CONSTANT_CONTACT_CLIENT_SECRET", "").strip()
    CONSTANT_CONTACT_ACCESS_TOKEN = os.getenv("CONSTANT_CONTACT_ACCESS_TOKEN", "").strip()
    CONSTANT_CONTACT_REFRESH_TOKEN = os.getenv("CONSTANT_CONTACT_REFRESH_TOKEN", "").strip()
    
    # Instantly
    INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "").strip()
    
    # Google Workspace / Gmail
    GMAIL_USER = os.getenv("GMAIL_USER", "").strip()
    GMAIL_FOLDER = os.getenv("GMAIL_FOLDER", "").strip()
    GOOGLE_WORKSPACE_MONITOR_USERS = os.getenv("GOOGLE_WORKSPACE_MONITOR_USERS", "").strip()
    # Render monta los archivos secretos en /etc/secrets/ por defecto
    _default_sa = "/etc/secrets/google_service_account.json" if os.path.exists("/etc/secrets/google_service_account.json") else os.path.join(BASE_DIR, "google_service_account.json")
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", _default_sa)

