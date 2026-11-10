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
    │   ├── commercial_routes.py    # Panel de control comercial Hernán (metas diarias, KPs, llamadas, opps, tareas)
    │   ├── audit_routes.py         # Auditoría comercial de llamadas y reproductor de audio
    │   ├── auth_routes.py          # Login, logout y gestión de sesión
    │   └── error_routes.py         # Manejadores de error (404, 500)
    ├── services/                   # Lógica de negocio
    │   ├── audit_engine.py         # Motor de análisis y auditoría de llamadas en Close CRM
    │   ├── commercial_dashboard.py # Motor analítico de metas diarias y KPIs de comerciales (Hernán)
    │   ├── report_performance.py   # Cálculos de rendimiento y KPIs comerciales
    │   └── sync_service.py         # Tareas periódicas de sincronización en segundo plano
    ├── templates/                  # Vistas HTML (Jinja2)
    │   ├── base.html               # Layout maestro y navegación ejecutiva
    │   ├── commercial_dashboard.html # Panel comercial Hernán (KPs, llamadas, metas diarias, opps, tareas)
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

### Definición de KP (Key Person) y Metas Diarias:
* **Live KP Talk (Llamadas):** Outcome oficial `TALKED TO KP – NEEDS NEXT STEP` (`outcome_033WrVULhq3NJjJSQLPgxg`).
* **#EKP (Email KP):** Contactos clave logrados mediante intercambio de correos electrónicos, identificados con el hashtag `#EKP` en las notas o registros de Close CRM.
* **#TKP (Text KP):** Contactos clave logrados vía SMS/Chat/WhatsApp, identificados con el hashtag `#TKP`.
* **Total KPs:** $\text{Live KP Talk} + \text{EKP} + \text{TKP}$.
* **Metas Diarias Obligatorias fijadas por Hernán:**
  1. **Llamadas Diarias Mínimas:** Mínimo **60 llamadas al día** por asesor.
  2. **KPs Diarios Mínimos:** Mínimo **10 KPs diarios** por asesor.
  3. **Composición de KPs:** La mitad de los KPs diarios (mínimo **5**) deben ser llamadas directas (*Live KP Talk*).
* **Métricas Adicionales de Monitoreo:**
  * **Gross Dial Time:** Tiempo bruto total en llamada telefónica (horas y minutos acumulados).
  * **Emails Enviados:** Correos 1-a-1 salientes enviados por cada comercial.
  * **Oportunidades Creadas:** Total de oportunidades creadas en el periodo, clasificadas entre el Pipeline de Ventas (*Sell*, `pipe_2g0VCRFwavbPI4whagZads`) y el Pipeline de Compras (*Purchase*, `pipe_3BxoKZTZl7XgFpE3YpVQJr`).
  * **Tareas:** Tareas creadas (*Set*) vs. tareas completadas (*Done*).
  * **Alertas de Inactividad (&ge; 30 min entre llamadas):** Auditoría en tiempo real del tiempo transcurrido desde que un asesor finaliza una llamada (`hora_fin = hora_inicio + duracion`) hasta que inicia la siguiente llamada del mismo día laboral.

---

## 4.1. Panel Comercial de Hernán (`/commercial-dashboard` o `/comerciales`)
Módulo independiente en la barra de navegación lateral ("Dirección Comercial" -> "Panel Comerciales (Hernán)"):
* Filtros rápidos por fecha: **Hoy**, **Ayer**, **Esta Semana**, **Semana Pasada**, **Este Mes** o Rango Personalizado.
* Cálculo automático de días hábiles del periodo seleccionado para proyectar las metas acumuladas de llamadas y KPs.
* Tabla comparativa con semaforización de cumplimiento (🟢 Cumple Metas, 🟡 Parcial, 🔴 Bajo Meta).
* **Columna y Tarjeta de Inactividad (&gt;30m):** Conteo de pausas por asesor, tiempo máximo de pausa y distinción de pausas efectivas de trabajo descontando automáticamente el descanso de almuerzo continuo (11:50 AM a 1:00 PM) y la pausa de la tarde (2:35 PM a 2:45 PM).
* **Módulo Completo de Auditoría de Inactividad:** Registro detallado de cada pausa &ge; 30 min indicando: asesor, duración laboral efectiva, minutos totales de reloj, tiempo descontado oficial (-1h 10m almuerzo o -10m pausa), horario (de/hasta), severidad (🚨 Crítica &gt;1h, ⚠️ Pausa Larga &gt;30m), y los leads/teléfonos de la llamada previa y de la siguiente llamada.
* Desglose auditor de notas registradas con `#EKP` y `#TKP` con acceso al texto ingresado y empresa/lead.
* Desglose de oportunidades creadas con lead, pipeline y valor monetario.
* Exportación directa a CSV para dirección comercial (`/commercial-dashboard/export.csv`).
* Exportación dedicada de alertas de inactividad a CSV (`/commercial-dashboard/inactivity-export.csv`).

---

## 5. Histórico Consolidado Reciente

### Semana 27* (Nov 2 - 6) - Datos Oficiales Guardados:
* **Llamadas Salientes del Equipo:** **622** (AM: 238 | PM: 384)
* **KPs Logrados:** **66** (56 por llamadas Close CRM + 10 por Email `#EKP`)
* **Efectividad Comercial:** **10.61%**
* **Outreach Masivo:**
  * Constant Contact: **169,842** (5 campañas enviadas)
  * Instantly: **317**
  * Launch Control (SMS): **0**
  * **Total Outreach:** **170,159**
  * Aperturas Humanas Reales (Sin Bots): **32,596** (32,477 CC + 119 Instantly)
  * Clics Humanos Únicos Confirmados: **7,361** (CC) / **7,409** (Total)
* **Notas de la semana:** `"+10 EKP - Opens reales humanos sin bots"`

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
