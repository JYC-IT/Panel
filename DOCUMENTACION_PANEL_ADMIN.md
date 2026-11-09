# 📘 Documentación Integral del Proyecto: Panel Admin (JYC Equipment)

## 1. Visión General del Proyecto
El **Panel Admin** es una plataforma centralizada para el seguimiento, auditoría y análisis de operaciones comerciales y de marketing en **JYC Equipment**. Consolida datos de múltiples fuentes de outreach y prospección en tiempo real:

1. **Email Masivo:** Integración con Constant Contact (OAuth2 / Reporting) e Instantly (API v2).
2. **SMS Masivo:** Registro y analítica de campañas de Launch Control.
3. **Gestión Telefónica & Comercial:** Integración directa con Close CRM y registro de llamadas (AM/PM) junto con contactos clave (**KPs: Talked to KP - Needs Next Step**).
4. **Respuestas & Leads:** Lectura de respuestas automáticas vs. humanas vía IMAP (Gmail / Google Workspace).

---

## 2. Arquitectura del Código y Estructura de Carpetas

El proyecto está construido en **Python (Flask)** con persistencia en **SQLite (`data.db`)** y frontend en Jinja2 + Chart.js.

```text
PanelAdmin/
└── respuestas-masivos/
    ├── app.py                      # Fábrica Flask (create_app), registro de blueprints y arranque
    ├── config.py                   # Configuración global, variables de entorno y constantes
    ├── auth.py                     # Sistema de autenticación de usuarios (admin / lector)
    ├── db.py                       # Conexión SQLite, esquemas de tablas, consultas de agregación
    ├── data.db                     # Base de datos SQLite operativa
    ├── requirements.txt            # Dependencias del proyecto
    ├── iniciar.bat                 # Script de inicio rápido en Windows
    ├── connectors/                 # Conectores con servicios externos
    │   ├── close_crm.py            # API Close CRM: llamadas, desglose AM/PM, KPs y asesores
    │   ├── constantcontact.py      # API Constant Contact: campañas, envíos, aperturas, clics
    │   ├── instantly.py            # API v2 Instantly: campañas masivas en frío
    │   ├── gmail.py                # Lector IMAP para respuestas
    │   └── google_workspace.py     # Delegación de dominio y Service Account Google
    ├── routes/                     # Controladores y endpoints web
    │   ├── campaign_routes.py      # Métricas de campañas masivas y listado de respuestas
    │   ├── report_routes.py        # Reporte semanal de resultados y sincronización con Close CRM
    │   ├── audit_routes.py         # Auditoría comercial de llamadas y reproductor de audio
    │   ├── auth_routes.py          # Login, logout y gestión de sesión
    │   └── error_routes.py         # Manejadores de error (404, 500)
    ├── services/                   # Lógica de negocio
    │   ├── audit_engine.py         # Motor de análisis y auditoría de llamadas en Close CRM
    │   ├── report_performance.py   # Cálculos de rendimiento y KPIs comerciales
    │   └── sync_service.py         # Tareas periódicas de sincronización en segundo plano
    ├── templates/                  # Vistas HTML (Jinja2)
    │   ├── base.html               # Layout maestro y navegación ejecutiva
    │   ├── index.html              # Dashboard general de campañas masivas
    │   ├── weekly_report.html      # Reporte ejecutivo semanal (gráficas y tablas históricas)
    │   ├── performance.html        # Métricas de rendimiento individual y del equipo
    │   ├── audit.html              # Vista de auditoría de llamadas Close CRM
    │   └── login.html              # Inicio de sesión seguro
    ├── static/                     # Archivos estáticos (CSS ejecutivo, librerías JS como Chart.js)
    ├── utils/                      # Clasificación de intenciones, limpieza y formateo de texto
    └── scripts/                    # Scripts de mantenimiento, auditorías y pruebas
```

---

## 3. Modelo de Base de Datos (`data.db`)

Las tablas principales son:

### A. `weekly_team_kpis`
Almacena el desempeño semanal acumulado del equipo comercial y de marketing:
* `week_number` (INTEGER UNIQUE): Número de semana (ej: 24, 25, 26).
* `week_label` (TEXT): Etiqueta visual (ej: "Week 26*").
* `date_range` (TEXT): Rango de fechas (ej: "Oct 26 - 30").
* `am_calls`, `pm_calls`, `total_calls`: Conteo de llamadas (AM: antes de las 12:00 PM, PM: después).
* `close_crm_calls`: Llamadas originadas en Close CRM.
* `kps`: Cantidad de contactos clave alcanzados (*Talked to KP*).
* `effectiveness_rate`: Porcentaje de efectividad ($(\text{KPs} / \text{Llamadas Totales}) \times 100$).
* `outreach_emails_cc`: Correos enviados por Constant Contact.
* `outreach_emails_instantly`: Correos enviados por Instantly.
* `outreach_sms`: Mensajes de texto enviados vía Launch Control.
* `total_outreach`: Suma de todos los envíos masivos.
* `opens_count`: Lecturas/aperturas confirmadas.
* `click_rate`: Tasa de clics registrada.
* `notes`: Observaciones ejecutivas de la semana.

### B. `weekly_agent_kpis`
Desglose individual por asesor para cada semana:
* `week_number`, `user_id`, `name`, `calls`, `kps`, `effectiveness`, `synced_at`.

### C. `campaigns` & `replies`
* `campaigns`: Detalle de cada envío masivo (nombre, asunto, remitente, envíos, aperturas, clics, rebotes).
* `replies`: Correos entrantes clasificados entre respuestas reales de clientes y autorespuestas automáticas (*out of office*).

---

## 4. Reglas de Negocio del Equipo Comercial (Close CRM)

### Asesores Comerciales Activos Autorizados (8 Integrantes):
1. **Hernán Bonilla** (`hbonilla@jycexports.com`)
2. **Juan Abuchaibe** (`solutions@jycexports.com`)
3. **Juan Arango** (`plastics@jycmachinery.com`)
4. **Juan Córdoba** (`jcordoba@jycexports.com`)
5. **Julián Prado** (`jp@jycmedical.com`)
6. **Mariana Polanco** (`mpolanco@jycexports.com`)
7. **Roy Jones** (`rjones@jycexports.com` / `royjones@jycexports.com`)
8. **Sebastián Jordan** (`sjordan@jycmachinery.com`)

### Personal Excluido de Reportes Comerciales:
* **Carlos Córdoba** (no incluido en reportes de llamadas salientes).
* **Rod Vélez** (desvinculado de la empresa).
* **Support Team** (buzón de soporte técnico).

### Definición de KP (Key Person):
En Close CRM, un **KP** se computa exclusivamente con el Outcome:
`TALKED TO KP – NEEDS NEXT STEP` (ID: `outcome_033WrVULhq3NJjJSQLPgxg`).

---

## 5. Histórico Consolidado Reciente

### Semana 27* (Nov 2 - 6) - Datos Oficiales Guardados:
* **Llamadas Salientes del Equipo:** **622** (AM: 238 | PM: 384)
* **KPs Logrados:** **56**
* **Efectividad Comercial:** **9.00%**
* **Outreach Masivo:**
  * Constant Contact: **119,222**
  * Instantly: **317**
  * Launch Control (SMS): **0**
  * **Total Outreach:** **119,539**
  * Aperturas: **38,665**
  * Clics: **6,124** (Click Rate: 5.12%)
* **Notas de la semana:** `""`

### Semana 26* (Oct 26 - 30) - Datos Oficiales Guardados:
* **Llamadas del Equipo:** **656** (AM: 373 | PM: 283)
* **KPs Logrados:** **57**
* **Efectividad Comercial:** **8.69%**
* **Outreach Masivo:**
  * Constant Contact: **109,982**
  * Instantly: **174**
  * Launch Control (SMS): **199**
  * **Total Outreach:** **110,355**
  * Aperturas: **31,886**
  * Clics: **501** (Click Rate: 1.57%)
* **Notas de la semana:** `""` (Vacía según instrucción).

### Semana 25* (Oct 19 - 23):
* **Llamadas:** 635 | **KPs:** 51 | **Efectividad:** 8.03%
* **Outreach Total:** 137,972 (CC: 135,842 | SMS: 2,130) | **Aperturas:** 44,067 | **Clics:** 14.7%
* **Notas de la semana:** `"Hernan no estuvo"`.

---

## 6. Instrucciones de Puesta en Marcha

1. Asegurarse de tener Python 3.10+ instalado.
2. Navegar a la carpeta del proyecto y crear o usar el entorno virtual:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Ejecutar la aplicación con el script directo:
   * Doble clic en `iniciar.bat` o:
   ```powershell
   python app.py
   ```
4. Acceder en el navegador a: `http://localhost:5000`
