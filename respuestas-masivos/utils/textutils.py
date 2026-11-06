"""Utilidades de texto compartidas: limpieza de cuerpo y detección de respuestas automáticas."""
import html
import re

AUTO_SUBJECT_RE = re.compile(
    r"(fuera de (la )?oficina|respuesta autom[aá]tica|auto[- ]?respuesta|out of (the )?office|"
    r"automatic reply|auto[- ]?reply|autoreply|vacaciones|vacation|ausente|ausencia|"
    r"ya no forma parte|se retira de la empresa|ya no labora|no longer with|has left the company)",
    re.I,
)
# Remitentes que no son personas: rebotes, notificaciones, antispam
BOUNCE_FROM_RE = re.compile(
    r"(mailer-daemon|postmaster|mail delivery|no-?reply|do-?not-?reply|notifications?@|boxbe)", re.I
)

# Dominios y patrones de correo propios de la organización que nunca deben contarse como respuestas externas de clientes
INTERNAL_DOMAINS = (
    "jyc",
    "jycexports.com",
    "jycmedical.com",
    "jycmachinery.com",
    "jycequipment.com",
    "equipmentjyc.com",
    "jyccorporation.com",
    "jycexportsglobal.com",
    "jycworld.com",
    "jyccncmachinery.com",
    "jycmedicalimaging.com",
    "shared1.ccsend.com",
    "constantcontact.com",
)


def is_internal_email(email_addr: str) -> bool:
    """Verifica si una dirección de correo pertenece a la organización interna o a rebotes técnicos."""
    if not email_addr:
        return False
    addr = email_addr.lower().strip()
    domain = addr.split("@")[-1] if "@" in addr else addr
    # Verificar si el dominio o dirección contiene cualquiera de los identificadores internos
    for d in INTERNAL_DOMAINS:
        if d in domain or d in addr:
            return True
    return False

# Líneas donde empieza el texto citado del correo original
QUOTE_START_RE = re.compile(
    r"^(El .{0,120}escribi[oó]:|On .{0,120}wrote:|-{2,}\s*(Mensaje original|Original Message)|"
    r"De:\s|From:\s|Enviado desde mi|Sent from my)",
    re.I,
)


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw_html or "")
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def clean_reply(text: str, max_len: int = 400) -> str:
    """Quita el texto citado del correo original y deja solo lo que escribió la persona."""
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith(">") or QUOTE_START_RE.match(s):
            break
        if s:
            lines.append(s)
    out = " ".join(lines)
    out = re.sub(r"\s+", " ", out).strip()
    return out[:max_len] + ("…" if len(out) > max_len else "")


def looks_auto(subject: str, body: str = "") -> bool:
    return bool(AUTO_SUBJECT_RE.search(subject or "") or AUTO_SUBJECT_RE.search((body or "")[:300]))
