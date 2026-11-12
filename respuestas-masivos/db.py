"""Base de datos SQLite: campañas y respuestas."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL,          -- 'gmail' | 'instantly' | 'constantcontact'
    match_subject TEXT,                   -- gmail/cc: texto que aparece en el asunto del masivo
    reply_to_email TEXT,                  -- correo configurado para recibir respuestas
    external_id   TEXT UNIQUE,            -- instantly/constantcontact: id de la campaña
    sent_count    INTEGER DEFAULT 0,      -- correos enviados (para calcular tasa)
    opens_count   INTEGER DEFAULT 0,      -- aperturas (si la plataforma lo provee)
    clicks_count  INTEGER DEFAULT 0,      -- clics (si la plataforma lo provee)
    bounces_count INTEGER DEFAULT 0,      -- rebotes (si la plataforma lo provee)
    start_date    TEXT,                   -- fecha desde la que se buscan respuestas (YYYY-MM-DD)
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS replies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    message_key TEXT NOT NULL,
    from_email  TEXT,
    from_name   TEXT,
    subject     TEXT,
    snippet     TEXT,
    received_at TEXT,
    is_auto     INTEGER DEFAULT 0,        -- 1 = respuesta automática (fuera de oficina, etc.)
    intent      TEXT DEFAULT 'general',   -- 'buy' | 'sell' | 'optout' | 'general'
    UNIQUE (campaign_id, message_key)
);

CREATE TABLE IF NOT EXISTS contact_interactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id   INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    contact_id    TEXT,
    interaction_type TEXT NOT NULL,       -- 'click' | 'open'
    email         TEXT NOT NULL,
    first_name    TEXT,
    last_name     TEXT,
    detail        TEXT,                   -- URL clickeada o tipo de dispositivo
    interacted_at TEXT,
    UNIQUE (campaign_id, interaction_type, email, detail)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    source  TEXT,
    ok      INTEGER,
    message TEXT
);

CREATE TABLE IF NOT EXISTS weekly_team_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_number INTEGER NOT NULL UNIQUE,
    week_label TEXT NOT NULL,
    date_range TEXT NOT NULL,
    am_calls INTEGER DEFAULT 0,
    pm_calls INTEGER DEFAULT 0,
    close_crm_calls INTEGER DEFAULT 0,
    ringcentral_calls INTEGER DEFAULT 0,
    total_calls INTEGER DEFAULT 0,
    calls_goal INTEGER DEFAULT 2000,
    kps INTEGER DEFAULT 0,
    kps_goal INTEGER DEFAULT 125,
    effectiveness_rate REAL DEFAULT 0,
    notes TEXT,
    outreach_emails_cc INTEGER DEFAULT 0,
    outreach_emails_instantly INTEGER DEFAULT 0,
    outreach_sms INTEGER DEFAULT 0,
    total_outreach INTEGER DEFAULT 0,
    opens_count INTEGER DEFAULT 0,
    clicks_count INTEGER DEFAULT 0,
    click_rate REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weekly_agent_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_number INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    calls INTEGER DEFAULT 0,
    kps INTEGER DEFAULT 0,
    effectiveness REAL DEFAULT 0,
    synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (week_number, user_id)
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'lector',   -- 'admin' | 'lector'
    active        INTEGER NOT NULL DEFAULT 1,
    last_login    TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migración suave de columnas por si la tabla ya existía
        for col, ctype in [
            ("opens_count", "INTEGER DEFAULT 0"),
            ("clicks_count", "INTEGER DEFAULT 0"),
            ("reply_to_email", "TEXT"),
            ("bounces_count", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass
        for col, ctype in [
            ("ringcentral_calls", "INTEGER DEFAULT 0"),
            ("close_crm_calls", "INTEGER DEFAULT 0"),
            ("clicks_count", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE weekly_team_kpis ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE replies ADD COLUMN intent TEXT DEFAULT 'general'")
        except sqlite3.OperationalError:
            pass

        # Índices de alto rendimiento y tabla de cache de leads
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads_cache (
                lead_id TEXT PRIMARY KEY,
                display_name TEXT,
                cached_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_verifications (
                activity_id TEXT PRIMARY KEY,
                activity_type TEXT NOT NULL,
                user_id TEXT,
                verdict TEXT NOT NULL,
                category TEXT,
                score INTEGER DEFAULT 0,
                reason TEXT,
                evidence TEXT,
                summary TEXT,
                model_used TEXT,
                analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replies_cid ON replies(campaign_id, is_auto)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replies_intent ON replies(campaign_id, intent)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_source_sent ON campaigns(source, sent_count)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions_cid ON contact_interactions(campaign_id, interaction_type)")

        deduplicate_replies(conn)
        backfill_reply_intents(conn)
        _seed_weekly_kpis(conn)


def deduplicate_replies(conn=None):
    """
    Garantiza que ningún correo de respuesta esté asignado a más de una campaña.
    Si un mensaje fue capturado por múltiples campañas (p. ej. campañas recurrentes
    con el mismo asunto), se atribuye únicamente a la campaña óptima:
    aquella cuya fecha de envío sea la más reciente anterior a la recepción de la respuesta.
    """
    from datetime import datetime

    def _parse_dt(s):
        if not s:
            return None
        try:
            s_clean = s.replace("Z", "+00:00")
            if len(s_clean) == 10:
                return datetime.fromisoformat(s_clean + "T00:00:00")
            return datetime.fromisoformat(s_clean)
        except Exception:
            try:
                return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    def _do_dedup(c):
        dups = c.execute("""
            SELECT message_key, COUNT(DISTINCT campaign_id) as c_count
            FROM replies
            GROUP BY message_key
            HAVING c_count > 1
        """).fetchall()

        if not dups:
            return 0

        to_delete_ids = []
        for d in dups:
            mkey = d["message_key"]
            rows = c.execute("""
                SELECT r.id, r.campaign_id, r.received_at, c.start_date, c.name, c.match_subject, c.reply_to_email
                FROM replies r
                JOIN campaigns c ON c.id = r.campaign_id
                WHERE r.message_key = ?
            """, (mkey,)).fetchall()

            best_id = None
            best_score = float("-inf")
            reply_received = _parse_dt(rows[0]["received_at"])

            for r in rows:
                c_start = _parse_dt(r["start_date"])
                score = 0

                if reply_received and c_start:
                    diff_days = (reply_received.date() - c_start.date()).days
                    if diff_days >= 0:
                        score += max(0, 1000 - diff_days)
                    else:
                        score -= 5000 + abs(diff_days)
                elif c_start:
                    score += 100

                subj_len = len(r["match_subject"] or "")
                score += min(subj_len, 50)

                if (r["match_subject"] or "").strip().upper() == "JYC MEDICAL":
                    score -= 2000

                if score > best_score:
                    best_score = score
                    best_id = r["id"]

            for r in rows:
                if r["id"] != best_id:
                    to_delete_ids.append(r["id"])

        if to_delete_ids:
            for i in range(0, len(to_delete_ids), 500):
                chunk = to_delete_ids[i:i + 500]
                placeholders = ",".join("?" * len(chunk))
                c.execute(f"DELETE FROM replies WHERE id IN ({placeholders})", chunk)

        return len(to_delete_ids)

    if conn is not None:
        return _do_dedup(conn)
    with get_conn() as local_conn:
        return _do_dedup(local_conn)


def backfill_reply_intents(conn=None):
    """
    Clasifica automáticamente todas las respuestas existentes aplicando el clasificador inteligente.
    """
    from utils.intent_classifier import classify_intent

    def _do_backfill(c):
        rows = c.execute("SELECT id, subject, snippet, is_auto FROM replies").fetchall()
        if not rows:
            return 0
        updates = []
        for r in rows:
            res = classify_intent(r["subject"] or "", r["snippet"] or "", bool(r["is_auto"]))
            updates.append((res["intent"], r["id"]))
        if updates:
            c.executemany("UPDATE replies SET intent = ? WHERE id = ?", updates)
        return len(updates)

    if conn is not None:
        return _do_backfill(conn)
    with get_conn() as local_conn:
        return _do_backfill(local_conn)


def update_reply_intent(reply_id: int, intent: str):
    """Permite cambiar manualmente la clasificación de una respuesta."""
    with get_conn() as conn:
        conn.execute("UPDATE replies SET intent = ? WHERE id = ?", (intent, reply_id))


def insert_reply(conn, campaign_id, r):
    """Inserta una respuesta; ignora duplicados. Devuelve True si era nueva."""
    intent = r.get("intent")
    is_auto = 1 if r.get("is_auto") else 0
    if not intent:
        from utils.intent_classifier import classify_intent
        intent = classify_intent(r.get("subject") or "", r.get("snippet") or "", bool(is_auto))["intent"]

    cur = conn.execute(
        """INSERT OR IGNORE INTO replies
           (campaign_id, message_key, from_email, from_name, subject, snippet, received_at, is_auto, intent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            campaign_id,
            r["message_key"],
            (r.get("from_email") or "").lower(),
            r.get("from_name") or "",
            r.get("subject") or "",
            r.get("snippet") or "",
            r.get("received_at") or "",
            is_auto,
            intent,
        ),
    )
    return cur.rowcount > 0


def insert_interaction(conn, campaign_id, item):
    """Inserta un clic o apertura; ignora duplicados. Devuelve True si era nuevo."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO contact_interactions
           (campaign_id, contact_id, interaction_type, email, first_name, last_name, detail, interacted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            campaign_id,
            item.get("contact_id") or "",
            item.get("interaction_type") or "click",
            (item.get("email") or item.get("email_address") or "").lower().strip(),
            item.get("first_name") or "",
            item.get("last_name") or "",
            item.get("detail") or item.get("link_url") or item.get("device_type") or "",
            item.get("interacted_at") or item.get("created_time") or "",
        ),
    )
    return cur.rowcount > 0


def log_sync(source, ok, message):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sync_log (source, ok, message) VALUES (?, ?, ?)",
            (source, 1 if ok else 0, message[:1000]),
        )


def _seed_weekly_kpis(conn):
    """Inicializa los datos históricos semanales hasta la Semana 27 (usa INSERT OR IGNORE para no sobrescribir datos)."""
    weeks_data = [
        (17, "Week 17*", "Aug 24–28", 534, 516, 1050, 2400, 112, 150, 10.67, "Festivo", 128000, 2900, 0, 130900, 50300, 16.2, 0, 0, 0),
        (18, "Week 18", "Aug 31–Sep 4", 593, 516, 1109, 2400, 122, 150, 11.00, "Semana normal", 137000, 313, 519, 137832, 40400, 16.2, 0, 0, 0),
        (19, "Week 19*", "Sep 7–11", 617, 373, 990, 2400, 68, 150, 6.87, "Salida Sophia / 1 Semana sin Mauro", 34000, 0, 0, 34000, 5930, 0.0, 0, 0, 0),
        (20, "Week 20*", "Sep 14–18", 550, 774, 1324, 2400, 59, 150, 4.46, "Festivo Lunes", 166000, 0, 23, 166023, 63700, 17.4, 0, 0, 0),
        (21, "Week 21*", "Sep 21–25", 537, 337, 874, 2400, 39, 150, 4.46, "Viaje Hernan y Sebastián", 78000, 0, 0, 78000, 46300, 38.2, 0, 0, 0),
        (22, "Week 22*", "Sep 28–Oct 2", 568, 409, 977, 2400, 92, 150, 9.42, "Viaje Sebastián", 43000, 0, 0, 43000, 22000, 39.0, 0, 0, 0),
        (23, "Week 23*", "Oct 5–9", 405, 388, 793, 2400, 56, 150, 7.06, "Sebastián no estuvo 2 días", 115000, 0, 0, 115000, 60700, 9.5, 0, 0, 5767),
        (24, "Week 24*", "Oct 12–16", 431, 372, 803, 2400, 79, 150, 9.84, "Rodrigo no estuvo 2 dias", 115000, 0, 0, 115000, 45100, 26.4, 71, 732, 11906),
        (25, "Week 25*", "Oct 19 - 23", 203, 432, 635, 2000, 51, 125, 8.03, "Hernan no estuvo", 135842, 0, 2130, 137972, 44067, 14.7, 23, 612, 6478),
        (26, "Week 26*", "Oct 26 - 30", 373, 283, 656, 2000, 57, 125, 8.69, "", 109982, 174, 199, 110355, 31886, 1.57, 0, 656, 501),
        (27, "Week 27*", "Nov 2 - 6", 238, 384, 622, 2000, 66, 125, 10.61, "+10 EKP - Opens reales humanos sin bots", 169842, 317, 0, 170159, 32596, 4.35, 0, 622, 7409),
    ]

    conn.executemany(
        """INSERT OR IGNORE INTO weekly_team_kpis
           (week_number, week_label, date_range, am_calls, pm_calls, total_calls, calls_goal,
            kps, kps_goal, effectiveness_rate, notes, outreach_emails_cc, outreach_emails_instantly,
            outreach_sms, total_outreach, opens_count, click_rate, ringcentral_calls, close_crm_calls, clicks_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        weeks_data,
    )

    w27_agents = [
        (27, "user_7cXDrv9AKnoVTSOnXBJo2oYXmUrFRDG40sIYVhmDwHA", "Juan Abuchaibe", 149, 8, 5.37),
        (27, "user_QrLrTvgnGNQRS7AMKX2EuCFrZKvqgKmIUloYX1TkRQd", "Mariana Polanco", 128, 15, 11.72),
        (27, "user_piUkoIPqMs7i1Lm3vdc2c2pE3lPjU3cCRvrmvxMonGy", "Julian Prado", 98, 6, 6.12),
        (27, "user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D", "Roy Jones", 90, 18, 20.0),
        (27, "user_n1y0yxmKit3rxkJlxhKZXFxEvG4y4G7C4cr4GPypUTx", "Sebastian Jordan", 75, 0, 0.0),
        (27, "user_TcBTZtqa1UlOlFQyDlhLJzEywClWo3CTQwXt2OREF2e", "Hernan Bonilla", 70, 19, 27.14),
        (27, "user_ESOupvkhojB5X4SkkJ20Nv05U2Klc0ImoRgS4Hwbwms", "Juan Cordoba", 12, 0, 0.0),
        (27, "user_BZhhrwAL2irTmKaPIntbraEWoINZrcYpKlGUUXsfwcV", "Juan Arango", 0, 0, 0.0),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO weekly_agent_kpis
           (week_number, user_id, name, calls, kps, effectiveness)
           VALUES (?, ?, ?, ?, ?, ?)""",
        w27_agents,
    )


def get_weekly_kpis(limit=6):
    """Retorna las últimas N semanas registradas en orden cronológico (por defecto las últimas 6 semanas)."""
    with get_conn() as conn:
        if limit:
            rows = conn.execute(
                """SELECT * FROM (
                       SELECT * FROM weekly_team_kpis ORDER BY week_number DESC LIMIT ?
                   ) ORDER BY week_number ASC""",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM weekly_team_kpis ORDER BY week_number ASC"
            ).fetchall()
    return [dict(r) for r in rows]


def save_agent_kpis(week_number, per_user_list):
    """Guarda o actualiza el desglose individual por asesor para una semana."""
    if not per_user_list:
        return
    with get_conn() as conn:
        for u in per_user_list:
            conn.execute(
                """INSERT INTO weekly_agent_kpis
                   (week_number, user_id, name, calls, kps, effectiveness, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(week_number, user_id) DO UPDATE SET
                       name=excluded.name,
                       calls=excluded.calls,
                       kps=excluded.kps,
                       effectiveness=excluded.effectiveness,
                       synced_at=CURRENT_TIMESTAMP""",
                (week_number, u["user_id"], u["name"], u["calls"], u["kps"], u["effectiveness"]),
            )


def get_agent_kpis(week_number=None):
    """Retorna las métricas individuales por asesor para una semana (o la última), excluyendo personal inactivo o desvinculado."""
    with get_conn() as conn:
        exclude_sql = "AND name NOT LIKE '%Roy%' AND name NOT LIKE '%Carlos%' AND user_id != 'user_Aa5pIAD0HQvnxk1hAMdvdBz3UAjW1NaVrKFMfJpmpaK'"
        if week_number:
            rows = conn.execute(
                f"SELECT * FROM weekly_agent_kpis WHERE week_number = ? {exclude_sql} ORDER BY calls DESC",
                (week_number,),
            ).fetchall()
        else:
            # Obtener la semana más reciente con datos
            latest = conn.execute(
                "SELECT MAX(week_number) FROM weekly_agent_kpis"
            ).fetchone()[0]
            if not latest:
                return []
            rows = conn.execute(
                f"SELECT * FROM weekly_agent_kpis WHERE week_number = ? {exclude_sql} ORDER BY calls DESC",
                (latest,),
            ).fetchall()
        return [dict(r) for r in rows]


def classify_campaign(c):
    """
    Clasifica automáticamente una campaña en su Línea de Negocio y Tipo de Intención (Venta vs Compra).
    Negocios: Medical, Machinery, Puertos, Multi Industria
    Intención: Compra, Venta
    """
    c = dict(c)
    name = (c.get("name") or "").lower()
    subj = (c.get("match_subject") or "").lower()
    reply_to = (c.get("reply_to_email") or "").lower()
    full_text = f"{name} {subj} {reply_to}"

    # 1. Línea de negocio
    if ("medical" in full_text or "mri" in full_text or "ct " in full_text
            or "hospital" in full_text or "ultrasound" in full_text or "jycmedical" in reply_to):
        business = "Medical"
    elif ("machinery" in full_text or "injection" in full_text or "molding" in full_text
          or "engel" in full_text or "krauss" in full_text or "sumitomo" in full_text
          or "haitian" in full_text or "jycmachinery" in reply_to):
        business = "Machinery"
    elif ("container handler" in full_text or "puerto" in full_text or "port" in full_text
          or "terminal" in full_text or "reachstacker" in full_text or "breakbulk" in full_text
          or "long beach" in full_text or ("hernan" in name and "loaded" in full_text)):
        business = "Puertos"
    else:
        business = "Multi Industria"

    # 2. Intención (Compra vs Venta)
    buy_keywords = [
        "buy", "purchase", "looking for", "looking to buy", "capex",
        "upgrade", "replacing", "planning an equipment", "compramos"
    ]
    if any(k in full_text for k in buy_keywords):
        intent = "Compra"
    else:
        intent = "Venta"

    return business, intent


def get_business_summary(since_date="2026-09-14"):
    """
    Genera el desglose ejecutivo por Línea de Negocio y Tipo (Compras vs Ventas)
    para las últimas 6 semanas (desde 2026-09-14 / Semana 20 hasta la Semana 25).
    """
    with get_conn() as conn:
        where_clause = ""
        params = []
        if since_date:
            where_clause = "WHERE c.start_date >= ? OR c.start_date IS NULL"
            params = [since_date]

        rows = conn.execute(f"""
            SELECT c.*,
                   COALESCE(SUM(CASE WHEN r.is_auto = 0 THEN 1 END), 0) AS replies
            FROM campaigns c
            LEFT JOIN replies r ON r.campaign_id = c.id
            {where_clause}
            GROUP BY c.id
        """, params).fetchall()

    data = {
        "Medical": {"business": "Medical", "icon": "🩺", "campaigns": 0, "compras": 0, "ventas": 0, "sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "replies": 0},
        "Machinery": {"business": "Machinery", "icon": "⚙️", "campaigns": 0, "compras": 0, "ventas": 0, "sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "replies": 0},
        "Puertos": {"business": "Puertos", "icon": "🚢", "campaigns": 0, "compras": 0, "ventas": 0, "sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "replies": 0},
        "Multi Industria": {"business": "Multi Industria", "icon": "🏗️", "campaigns": 0, "compras": 0, "ventas": 0, "sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "replies": 0},
    }

    totals = {
        "business": "TOTAL CONSOLIDADO",
        "icon": "📊",
        "campaigns": 0,
        "compras": 0,
        "ventas": 0,
        "sent": 0,
        "opens": 0,
        "clicks": 0,
        "bounces": 0,
        "replies": 0,
    }

    for r in rows:
        b, intent = classify_campaign(r)
        if b not in data:
            data[b] = {"business": b, "icon": "📦", "campaigns": 0, "compras": 0, "ventas": 0, "sent": 0, "opens": 0, "clicks": 0, "bounces": 0, "replies": 0}
        d = data[b]

        sent = r["sent_count"] or 0
        opens = r["opens_count"] or 0
        clicks = r["clicks_count"] or 0
        bounces = (r["bounces_count"] if "bounces_count" in r.keys() else 0) or 0
        replies = r["replies"] or 0

        d["campaigns"] += 1
        totals["campaigns"] += 1

        if intent == "Compra":
            d["compras"] += 1
            totals["compras"] += 1
        else:
            d["ventas"] += 1
            totals["ventas"] += 1

        d["sent"] += sent
        totals["sent"] += sent
        d["opens"] += opens
        totals["opens"] += opens
        d["clicks"] += clicks
        totals["clicks"] += clicks
        d["bounces"] += bounces
        totals["bounces"] += bounces
        d["replies"] += replies
        totals["replies"] += replies

    # Calcular tasas porcentuales
    def _calc_rates(item):
        s = item["sent"]
        item["open_rate"] = round(100.0 * item["opens"] / s, 1) if s else 0.0
        item["click_rate"] = round(100.0 * item["clicks"] / s, 1) if s else 0.0
        item["bounce_rate"] = round(100.0 * item["bounces"] / s, 1) if s else 0.0
        item["reply_rate"] = round(100.0 * item["replies"] / s, 2) if s else 0.0

    for d in data.values():
        _calc_rates(d)
    _calc_rates(totals)

    # Ordenar por volumen de correos enviados
    ordered = sorted(data.values(), key=lambda x: x["sent"], reverse=True)
    return ordered, totals


def insert_manual_campaign(name, source, start_date, sent_count=0, opens_count=0, clicks_count=0, match_subject=None, reply_to_email=None):
    """Inserta o actualiza una campaña registrada manualmente de contingencia."""
    name = (name or "").strip()
    if not name:
        raise ValueError("El nombre de la campaña es obligatorio.")
    source = (source or "constantcontact").strip().lower()
    external_id = f"manual_{source}_{name[:25].lower().replace(' ', '_')}_{start_date or 'nodate'}"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO campaigns (name, source, match_subject, reply_to_email, external_id, sent_count, opens_count, clicks_count, start_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(external_id) DO UPDATE SET
                   name=excluded.name,
                   match_subject=COALESCE(excluded.match_subject, campaigns.match_subject),
                   reply_to_email=COALESCE(excluded.reply_to_email, campaigns.reply_to_email),
                   sent_count=excluded.sent_count,
                   opens_count=excluded.opens_count,
                   clicks_count=excluded.clicks_count,
                   start_date=COALESCE(excluded.start_date, campaigns.start_date)""",
            (name, source, match_subject or name, reply_to_email, external_id, int(sent_count or 0), int(opens_count or 0), int(clicks_count or 0), start_date)
        )
        row = conn.execute("SELECT id FROM campaigns WHERE external_id = ?", (external_id,)).fetchone()
        return row["id"] if row else None


def get_cached_leads(lead_ids):
    """Obtiene los nombres de leads cacheados en SQLite."""
    if not lead_ids:
        return {}
    lead_list = list(lead_ids)
    placeholders = ",".join(["?"] * len(lead_list))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT lead_id, display_name FROM leads_cache WHERE lead_id IN ({placeholders})",
            lead_list
        ).fetchall()
        return {r["lead_id"]: {"display_name": r["display_name"]} for r in rows}


def save_cached_leads(leads_map):
    """Guarda leads en SQLite para evitar llamadas recurrentes a la API."""
    if not leads_map:
        return
    with get_conn() as conn:
        for lid, info in leads_map.items():
            name = info.get("display_name") if isinstance(info, dict) else str(info)
            if name and name not in ("Sin Nombre", "Lead", "Lead Desconocido"):
                conn.execute(
                    "INSERT INTO leads_cache (lead_id, display_name) VALUES (?, ?) ON CONFLICT(lead_id) DO UPDATE SET display_name=excluded.display_name",
                    (lid, name)
                )


def get_setting(key: str, default: str = "") -> str:
    """Obtiene una configuración persistente desde SQLite."""
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row and row["value"] is not None else default


def set_setting(key: str, value: str):
    """Guarda o actualiza una configuración persistente en SQLite."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
            (key, value),
        )
