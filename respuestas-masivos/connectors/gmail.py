"""Lee respuestas a masivos desde Gmail / Google Workspace vía IMAP (solo lectura).

Para cada campaña de tipo 'gmail' busca correos cuyo asunto contenga el texto
configurado (p. ej. "Promo Octubre" encuentra "RE: Promo Octubre 20% dcto"),
que NO hayas enviado tú, desde la fecha de inicio de la campaña.
No marca los correos como leídos (usa BODY.PEEK).
"""
import email
import imaplib
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from utils.textutils import BOUNCE_FROM_RE, clean_reply, html_to_text, looks_auto, is_internal_email

IMAP_HOST = "imap.gmail.com"
LIST_RE = re.compile(r'\((?P<flags>[^)]*)\) "(?P<delim>[^"]*)" (?P<name>.+)')


def _dec(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body_text(msg) -> str:
    plain, html_part = None, None
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart":
            continue
        if "attachment" in (part.get("Content-Disposition") or "").lower():
            continue
        ctype = part.get_content_type()
        try:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and html_part is None:
            html_part = text
    if plain:
        return plain
    return html_to_text(html_part or "")


def _is_auto_header(msg) -> bool:
    auto_sub = (msg.get("Auto-Submitted") or "no").strip().lower()
    prec = (msg.get("Precedence") or "").strip().lower()
    return (
        auto_sub != "no"
        or bool(msg.get("X-Autoreply"))
        or bool(msg.get("X-Autorespond"))
        or prec in ("auto_reply", "junk")
    )


def _find_all_mail_folder(conn) -> str:
    """Busca la carpeta 'Todos' / 'All Mail' (incluye archivados). Si no, usa INBOX."""
    typ, data = conn.list()
    if typ == "OK":
        for raw in data:
            line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            m = LIST_RE.match(line)
            if m and "\\All" in m.group("flags"):
                return m.group("name")
    return "INBOX"


def _search(conn, subject_text: str, since: date, own_email: str):
    kw = subject_text.replace('"', "").strip()
    query = f'subject:("{kw}") after:{since.strftime("%Y/%m/%d")} -from:{own_email}'
    # X-GM-RAW permite usar la misma sintaxis del buscador de Gmail; literal para soportar tildes/ñ
    conn.literal = query.encode("utf-8")
    typ, data = conn.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def fetch_replies(user, app_password, campaigns, default_lookback_days=30, folder=None):
    """Devuelve {campaign_id: [reply_dict, ...]} para las campañas gmail dadas."""
    results = {c["id"]: [] for c in campaigns}
    if not campaigns:
        return results

    own = user.lower()
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conn.login(user, app_password)
        mailbox = folder or _find_all_mail_folder(conn)
        typ, _ = conn.select(mailbox, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"No se pudo abrir la carpeta {mailbox}")

        for c in campaigns:
            if not (c["match_subject"] or "").strip():
                continue
            if c["start_date"]:
                since = date.fromisoformat(c["start_date"])
            else:
                since = date.today() - timedelta(days=default_lookback_days)

            uids = _search(conn, c["match_subject"], since, own)
            for i in range(0, len(uids), 50):
                chunk = b",".join(uids[i : i + 50])
                typ, data = conn.uid("FETCH", chunk, "(BODY.PEEK[])")
                if typ != "OK":
                    continue
                for item in data:
                    if not isinstance(item, tuple):
                        continue
                    meta, raw = item
                    msg = email.message_from_bytes(raw)
                    name, addr = parseaddr(_dec(msg.get("From")))
                    addr = (addr or "").lower()
                    if not addr or addr == own or BOUNCE_FROM_RE.search(addr + " " + name) or is_internal_email(addr):
                        continue

                    subject = _dec(msg.get("Subject"))
                    body = _body_text(msg)
                    try:
                        received = parsedate_to_datetime(msg.get("Date")).isoformat()
                    except Exception:
                        received = ""
                    uid_m = re.search(rb"UID (\d+)", meta)
                    key = (msg.get("Message-ID") or "").strip() or f"gmail-uid-{uid_m.group(1).decode() if uid_m else ''}"

                    results[c["id"]].append(
                        {
                            "message_key": key,
                            "from_email": addr,
                            "from_name": name,
                            "subject": subject,
                            "snippet": clean_reply(body),
                            "received_at": received,
                            "is_auto": _is_auto_header(msg) or looks_auto(subject, body),
                        }
                    )
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return results
