"""Conector Constant Contact API v3 de Alto Rendimiento.
Obtiene campañas recientes, estadísticas (enviados, aperturas, clics) y el asunto de cada campaña.
Optimizado con:
1. Connection pooling (HTTP keep-alive reuse) para reducir latencia TLS.
2. Procesamiento concurrente con ThreadPoolExecutor (8 workers en paralelo).
3. Sincronización incremental para no re-consultar metadatos inmutables de campañas históricas.
"""
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://api.cc.email/v3"

_session = None

def get_session():
    """Retorna una sesión con HTTP keep-alive y connection pooling para reutilizar handshakes TLS."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=2)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def _get_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


def save_tokens_to_env(access_token: str, refresh_token: str = None):
    """Actualiza el archivo .env con los nuevos tokens para mantener la sesión."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        has_at = has_rt = False
        new_lines = []
        for line in lines:
            if line.startswith("CONSTANT_CONTACT_ACCESS_TOKEN="):
                new_lines.append(f"CONSTANT_CONTACT_ACCESS_TOKEN={access_token}\n")
                has_at = True
            elif refresh_token and line.startswith("CONSTANT_CONTACT_REFRESH_TOKEN="):
                new_lines.append(f"CONSTANT_CONTACT_REFRESH_TOKEN={refresh_token}\n")
                has_rt = True
            else:
                new_lines.append(line)
        
        if not has_at:
            new_lines.append(f"CONSTANT_CONTACT_ACCESS_TOKEN={access_token}\n")
        if refresh_token and not has_rt:
            new_lines.append(f"CONSTANT_CONTACT_REFRESH_TOKEN={refresh_token}\n")
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        os.environ["CONSTANT_CONTACT_ACCESS_TOKEN"] = access_token
        if refresh_token:
            os.environ["CONSTANT_CONTACT_REFRESH_TOKEN"] = refresh_token
    except Exception:
        pass


def exchange_code_for_tokens(code: str, redirect_uri: str):
    """Intercambia un authorization code por access_token y refresh_token."""
    client_id = os.getenv("CONSTANT_CONTACT_CLIENT_ID", "").strip()
    client_secret = os.getenv("CONSTANT_CONTACT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError("Falta CONSTANT_CONTACT_CLIENT_ID o CONSTANT_CONTACT_CLIENT_SECRET en .env")

    r = requests.post(
        "https://authz.constantcontact.com/oauth2/default/v1/token",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "JYC-PanelAdmin/1.0"},
        auth=(client_id, client_secret),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        },
        timeout=20
    )
    r.raise_for_status()
    data = r.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if access_token:
        save_tokens_to_env(access_token, refresh_token)
    return data


def get_access_token():
    """Retorna un token válido. Si hay refresh token configurado y expiró, lo renueva."""
    from dotenv import load_dotenv
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(root_dir, ".env"), override=True)
    token = os.getenv("CONSTANT_CONTACT_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("CONSTANT_CONTACT_CLIENT_ID", "").strip()
    client_secret = os.getenv("CONSTANT_CONTACT_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("CONSTANT_CONTACT_REFRESH_TOKEN", "").strip()

    # Si hay credenciales OAuth para renovar
    if refresh_token and client_id and client_secret:
        try:
            r = requests.post(
                "https://authz.constantcontact.com/oauth2/default/v1/token",
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "JYC-PanelAdmin/1.0"},
                auth=(client_id, client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                },
                timeout=20
            )
            if r.status_code == 200:
                data = r.json()
                new_token = data.get("access_token")
                new_refresh = data.get("refresh_token") or refresh_token
                if new_token:
                    save_tokens_to_env(new_token, new_refresh)
                    return new_token
        except Exception:
            pass
    return token


def list_campaigns(token: str, limit: int = 50):
    """Lista las campañas de email más recientes."""
    url = f"{BASE}/emails"
    params = {"limit": limit}
    session = get_session()
    r = session.get(url, headers=_get_headers(token), params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("campaigns", [])


def get_campaign_details(token: str, campaign_id: str):
    """Obtiene detalles de una campaña, incluyendo sus activities."""
    url = f"{BASE}/emails/{campaign_id}"
    session = get_session()
    r = session.get(url, headers=_get_headers(token), timeout=15)
    r.raise_for_status()
    return r.json()


def get_activity_details(token: str, activity_id: str):
    """Obtiene el asunto, remitente y reply_to de la actividad del email."""
    url = f"{BASE}/emails/activities/{activity_id}"
    session = get_session()
    r = session.get(url, headers=_get_headers(token), timeout=15)
    r.raise_for_status()
    return r.json()


def get_campaign_stats(token: str, campaign_id: str):
    """Obtiene estadísticas de la campaña (enviados, aperturas, clics, rebotes)."""
    url = f"{BASE}/reports/stats/email_campaigns/{campaign_id}"
    try:
        session = get_session()
        r = session.get(url, headers=_get_headers(token), timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def _enrich_single_campaign(token: str, c: dict, known_campaigns: dict = None) -> dict:
    """Enriquece una sola campaña obteniendo sus metadatos y estadísticas de forma inteligente."""
    cid = c.get("campaign_id")
    name = c.get("name") or cid
    status = c.get("current_status")
    created_at = c.get("created_at") or c.get("updated_at") or ""
    date_str = created_at[:10] if created_at else None

    # Verificamos si ya tenemos datos conocidos en SQLite
    known_data = (known_campaigns or {}).get(cid)
    subject = known_data.get("match_subject", "") if known_data else ""
    reply_to = known_data.get("reply_to_email", "") if known_data else ""
    primary_activity_id = known_data.get("primary_activity_id", "") if known_data else ""

    session = get_session()
    headers = _get_headers(token)

    # 1. Metadatos de Actividad (Asunto y Reply-To)
    # Si ya conocemos el asunto y el remitente de una campaña pasada, no repetimos estas 2 llamadas
    if not subject or not reply_to:
        try:
            r = session.get(f"{BASE}/emails/{cid}", headers=headers, timeout=12)
            if r.status_code == 200:
                activities = r.json().get("campaign_activities", [])
                for act in activities:
                    act_role = act.get("role", "")
                    if act_role in ("primary_email", "resend") or not subject:
                        act_id = act.get("campaign_activity_id")
                        if not primary_activity_id:
                            primary_activity_id = act_id
                        try:
                            act_r = session.get(f"{BASE}/emails/activities/{act_id}", headers=headers, timeout=12)
                            if act_r.status_code == 200:
                                act_data = act_r.json()
                                subject = act_data.get("subject", "") or subject
                                reply_to = act_data.get("reply_to_email", "") or reply_to
                                if subject:
                                    primary_activity_id = act_id
                                    break
                        except Exception:
                            pass
        except Exception:
            pass

    # 2. Estadísticas de Campaña (Enviados, Aperturas, Clics)
    stats_data = {}
    try:
        r_stats = session.get(f"{BASE}/reports/stats/email_campaigns/{cid}", headers=headers, timeout=12)
        if r_stats.status_code == 200:
            stats = r_stats.json()
            if isinstance(stats, dict):
                if "stats" in stats:
                    stats_data = stats["stats"]
                elif "results" in stats and isinstance(stats["results"], list) and len(stats["results"]) > 0:
                    stats_data = stats["results"][0].get("stats", {})
    except Exception:
        pass

    sends = stats_data.get("em_sends", 0)
    opens = stats_data.get("em_opens", 0)
    clicks = stats_data.get("em_clicks", 0)
    bounces = stats_data.get("em_bounces", 0)

    # Si la API no devolvió datos y ya teníamos métricas previas en BD, conservamos las existentes
    if known_data and sends == 0 and (known_data.get("sent_count") or 0) > 0:
        sends = known_data["sent_count"]
        opens = known_data.get("opens_count", 0)
        clicks = known_data.get("clicks_count", 0)
        bounces = known_data.get("bounces_count", 0)

    return {
        "campaign_id": cid,
        "primary_activity_id": primary_activity_id,
        "name": name,
        "status": status,
        "subject": subject,
        "reply_to": reply_to,
        "sent_count": sends,
        "opens": opens,
        "clicks": clicks,
        "bounces": bounces,
        "start_date": date_str or (known_data.get("start_date") if known_data else None),
        "updated_at": c.get("updated_at")
    }


def fetch_recent_campaigns_with_details(token: str, limit: int = 50, known_campaigns: dict = None, max_workers: int = 8):
    """
    Obtiene las campañas más recientes enriquecidas de forma altamente concurrente y optimizada.
    Utiliza ThreadPoolExecutor para consultar los detalles en paralelo en vez de en fila india.
    """
    campaigns = list_campaigns(token, limit=limit)
    if not campaigns:
        return []

    enriched = []
    # Usamos hilos concurrentes para procesar en paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_cid = {
            executor.submit(_enrich_single_campaign, token, c, known_campaigns): c.get("campaign_id")
            for c in campaigns
        }
        for future in as_completed(future_to_cid):
            try:
                res = future.result()
                if res:
                    enriched.append(res)
            except Exception:
                pass

    # Ordenar por fecha descendente
    enriched.sort(key=lambda x: x.get("start_date") or "", reverse=True)
    return enriched


def fetch_activity_tracking(token: str, activity_id: str, tracking_type: str = "clicks", limit: int = 100):
    """
    Descarga la lista de contactos que interactuaron (clicks o opens) con una actividad.
    tracking_type: 'clicks' o 'opens'
    """
    url = f"{BASE}/reports/email_reports/{activity_id}/tracking/{tracking_type}"
    params = {"limit": limit}
    results = []
    session = get_session()
    
    # Recorremos hasta 3 páginas (máximo 300 contactos más recientes)
    for _ in range(3):
        try:
            r = session.get(url, headers=_get_headers(token), params=params, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("tracking_activities", [])
            for it in items:
                results.append({
                    "contact_id": it.get("contact_id"),
                    "interaction_type": "click" if tracking_type == "clicks" else "open",
                    "email": it.get("email_address"),
                    "first_name": it.get("first_name", ""),
                    "last_name": it.get("last_name", ""),
                    "detail": it.get("link_url") or it.get("device_type") or "",
                    "interacted_at": it.get("created_time") or "",
                })
            
            # Paginación con cursor/next link si existe
            next_link = (data.get("_links") or {}).get("next", {}).get("href")
            if not next_link or not items:
                break
            url = f"https://api.cc.email{next_link}" if next_link.startswith("/") else next_link
            params = {}
        except Exception:
            break
            
    return results
