"""Lee campañas, métricas y respuestas desde Instantly (API v2).

Docs: https://developer.instantly.ai/  (requiere API key v2 con permisos de lectura)
"""
import time

import requests

from utils.textutils import BOUNCE_FROM_RE, clean_reply, html_to_text, looks_auto, is_internal_email

BASE = "https://api.instantly.ai/api/v2"


def _get(path, api_key, params=None, retries=6):
    for attempt in range(retries):
        r = requests.get(
            BASE + path,
            headers={"Authorization": f"Bearer {api_key}"},
            params=params or {},
            timeout=30,
        )
        if r.status_code == 429 and attempt < retries - 1:
            wait = float(r.headers.get("Retry-After") or 0) or min(2 ** attempt, 30)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()


def _paginate(path, api_key, params=None, max_pages=200):
    params = dict(params or {})
    params.setdefault("limit", 100)
    for _ in range(max_pages):
        data = _get(path, api_key, params)
        items = data.get("items", []) if isinstance(data, dict) else data
        yield from items
        nxt = data.get("next_starting_after") if isinstance(data, dict) else None
        if not nxt or not items:
            break
        params["starting_after"] = nxt


def list_campaigns(api_key):
    return list(_paginate("/campaigns", api_key))


def campaign_analytics(api_key):
    """Devuelve {campaign_id: {...métricas...}}."""
    data = _get("/campaigns/analytics", api_key)
    items = data.get("items", data) if isinstance(data, dict) else data
    return {a.get("campaign_id"): a for a in items or [] if a.get("campaign_id")}


def fetch_replies(api_key, campaign_external_id):
    out = []
    for e in _paginate("/emails", api_key, {"campaign_id": campaign_external_id, "email_type": "received"}):
        body = e.get("body") or {}
        text = body.get("text") or html_to_text(body.get("html") or "") or e.get("content_preview") or ""
        subject = e.get("subject") or ""
        from_email = e.get("from_address_email") or e.get("lead") or ""
        if BOUNCE_FROM_RE.search(from_email) or is_internal_email(from_email):
            continue
        out.append(
            {
                "message_key": f"instantly-{e.get('id')}",
                "from_email": from_email,
                "from_name": "",
                "subject": subject,
                "snippet": clean_reply(text),
                "received_at": e.get("timestamp_email") or e.get("timestamp_created") or "",
                "is_auto": bool(e.get("is_auto_reply")) or looks_auto(subject, text),
            }
        )
    return out
