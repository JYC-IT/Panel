# 📬 ¿Quién responde nuestros masivos?

Panel web que cuenta **cuántas personas y quiénes** responden cada envío masivo, y se actualiza solo.

| Fuente | Cómo se conecta | Qué obtiene |
|---|---|---|
| **Gmail / Google Workspace** | IMAP en solo lectura (no marca correos como leídos) | Respuestas cuyo asunto contiene el texto de la campaña |
| **Constant Contact** | A través de Gmail (si el "responder a" del masivo es tu Gmail) | Igual que Gmail |
| **Instantly** | API v2 | Campañas, enviados y respuestas, automático |

Excluye rebotes (mailer-daemon) y separa las respuestas automáticas ("fuera de oficina", etc.).

## Puesta en marcha

1. Copia `.env.example` a `.env` y rellena:
   - `GMAIL_USER` y `GMAIL_APP_PASSWORD` → crea la contraseña de aplicación en <https://myaccount.google.com/apppasswords> (requiere verificación en 2 pasos; en Workspace, el admin debe permitir IMAP).
   - `INSTANTLY_API_KEY` (opcional).
2. Doble clic en **`iniciar.bat`** (instala dependencias la primera vez y abre <http://localhost:5000>).
3. En el panel, crea una campaña de Gmail con el **texto del asunto** del masivo y la **fecha de envío**. Las campañas de Instantly aparecen solas.
4. Pulsa **Sincronizar ahora** o espera: se sincroniza cada `SYNC_INTERVAL_MINUTES`.

Manual: `pip install -r requirements.txt` y `python app.py`.

## Consejos
- Usa un asunto distintivo en cada masivo (p. ej. "Promo Octubre 2026") para que el conteo sea exacto.
- Agrega el número de **enviados** para ver la tasa de respuesta.
- Exporta la lista de personas a CSV (se abre en Excel) para que ventas les haga seguimiento.
- Para compartir el panel en la oficina, pon `HOST=0.0.0.0` y entra con la IP del PC.

## Estructura del Proyecto
- `app.py` – Fábrica principal de la aplicación Flask (`create_app`)
- `config.py` – Configuración centralizada y lectura de entorno
- `auth.py` – Autenticación, sesiones y control de accesos
- `db.py` – Base de datos SQLite (`data.db`)
- `routes/` – Controladores y rutas web por dominio:
  - `campaign_routes.py` – Campañas, estadísticas y respuestas
  - `audit_routes.py` – Auditorías comerciales y proxy de grabaciones
  - `report_routes.py` – Reportes semanales y métricas de desempeño
  - `auth_routes.py` – Inicio y cierre de sesión
  - `error_routes.py` – Páginas de error personalizadas (404, 500)
- `services/` – Lógica de negocio y tareas del sistema:
  - `audit_engine.py` – Motor de auditoría comercial Close CRM
  - `report_performance.py` – Generador de métricas y rendimiento
  - `sync_service.py` – Sincronización y scheduler automático en segundo plano
- `connectors/` – Integraciones y APIs de terceros:
  - `close_crm.py` – Integración con Close CRM
  - `constantcontact.py` – Integración con Constant Contact OAuth2
  - `gmail.py` – Lector IMAP de respuestas Gmail
  - `google_workspace.py` – Delegación de dominio y Service Account de Google Workspace
  - `instantly.py` – Integración con API v2 de Instantly
- `utils/` – Utilidades auxiliares (parsing, limpieza de texto, detección de autoreply)
- `scripts/` – Herramientas administrativas (p. ej. `crear_usuario.py`), diagnósticos y tareas de mantenimiento
- `tests/` – Pruebas unitarias y de endpoints
- `templates/` y `static/` – Interfaz de usuario (HTML/CSS/JS)

## Próximos pasos posibles
- SMS (cuando se confirme el proveedor: Twilio, etc.)
- Clasificar respuestas: interesado / no interesado / baja
- Alertas a ventas cuando alguien responde
