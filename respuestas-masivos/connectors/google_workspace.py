"""Lector centralizado de Gmail / Google Workspace mediante Domain-Wide Delegation (Service Account).

Permite leer las respuestas de cualquier buzón corporativo (jp@, support@, ventas@, etc.)
sin requerir contraseñas de los usuarios. Solo requiere permisos de lectura en el Workspace.
"""
import base64
import email
import os
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.textutils import BOUNCE_FROM_RE, clean_reply, html_to_text, looks_auto, is_internal_email

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "google_service_account.json")


def is_service_account_available() -> bool:
    """Verifica si el archivo de Service Account existe."""
    return os.path.exists(SERVICE_ACCOUNT_FILE)


def _get_gmail_service(user_email: str):
    """Crea una conexión con la API de Gmail suplantando al usuario con DWD."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    ).with_subject(user_email)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _dec(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _extract_body_from_payload(payload) -> str:
    """Extrae el texto de la estructura multipart o simple del payload de la API de Gmail."""
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])
    
    # Si viene con cuerpo directo
    body_data = payload.get("body", {}).get("data")
    if body_data and mime_type.startswith("text/plain"):
        try:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        except Exception:
            pass

    plain_text = ""
    html_content = ""

    # Recorrer subpartes
    for part in parts:
        p_mime = part.get("mimeType", "")
        p_data = part.get("body", {}).get("data")
        if p_data:
            try:
                decoded = base64.urlsafe_b64decode(p_data).decode("utf-8", errors="replace")
                if p_mime == "text/plain" and not plain_text:
                    plain_text = decoded
                elif p_mime == "text/html" and not html_content:
                    html_content = decoded
            except Exception:
                pass
        # Recursivo si hay multipart anidado
        if part.get("parts"):
            nested = _extract_body_from_payload(part)
            if nested and not plain_text:
                plain_text = nested

    if plain_text:
        return plain_text
    if html_content:
        return html_to_text(html_content)
    return ""


def fetch_replies_for_user(user_email: str, campaigns, default_lookback_days: int = 30):
    """
    Busca respuestas a las campañas en el buzón de un usuario específico usando la Gmail API.
    Devuelve {campaign_id: [reply_dict, ...]}.
    """
    results = {c["id"]: [] for c in campaigns}
    if not campaigns:
        return results

    try:
        service = _get_gmail_service(user_email)
    except Exception as exc:
        raise RuntimeError(f"Error al conectar con buzón de {user_email}: {exc}")

    own = user_email.lower()

    for c in campaigns:
        subject_text = (c.get("match_subject") or "").strip()
        if not subject_text:
            continue

        # Limpiar caracteres que rompen el query de Gmail y signos de puntuación iniciales
        clean_kw = re.sub(r'["\']', '', subject_text).strip()
        clean_kw = re.sub(r'^[,\s\-:;]+', '', clean_kw).strip()
        if not clean_kw:
            continue

        if c.get("start_date"):
            try:
                since = date.fromisoformat(c["start_date"][:10])
            except Exception:
                since = date.today() - timedelta(days=default_lookback_days)
        else:
            since = date.today() - timedelta(days=default_lookback_days)

        # Construir consulta oficial de Gmail restringida al Asunto (Subject)
        query = f'subject:("{clean_kw}") after:{since.strftime("%Y/%m/%d")} -from:{own}'

        try:
            res = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
            messages = res.get("messages", [])
        except HttpError:
            continue

        for m_meta in messages:
            msg_id = m_meta["id"]
            try:
                m = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            except Exception:
                continue

            headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
            raw_from = headers.get("from", "")
            from_name, from_addr = parseaddr(_dec(raw_from))
            from_addr = (from_addr or "").lower()

            # Omitir si proviene de sí mismo, es interno de la organización o es rebote / daemon
            if not from_addr or from_addr == own or BOUNCE_FROM_RE.search(from_addr + " " + from_name) or is_internal_email(from_addr):
                continue

            subject = _dec(headers.get("subject", ""))
            # Verificación de seguridad en el asunto: evitar falsos positivos
            check_term = clean_kw.lower().strip("?")
            if check_term and check_term not in subject.lower():
                continue
            received_at = headers.get("date", "")
            try:
                received_iso = parsedate_to_datetime(received_at).isoformat()
            except Exception:
                received_iso = ""

            raw_body = _extract_body_from_payload(m.get("payload", {}))
            snippet = clean_reply(raw_body or m.get("snippet", ""))

            # Detección de respuestas automáticas
            is_auto = (
                headers.get("auto-submitted", "no").lower() != "no"
                or bool(headers.get("x-autoreply"))
                or bool(headers.get("x-autorespond"))
                or looks_auto(subject, snippet)
            )

            msg_key = headers.get("message-id", "").strip() or f"gmail-api-{msg_id}"

            results[c["id"]].append({
                "message_key": msg_key,
                "from_email": from_addr,
                "from_name": from_name,
                "subject": subject,
                "snippet": snippet,
                "received_at": received_iso,
                "is_auto": is_auto,
            })

    return results
