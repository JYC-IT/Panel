"""Clasificador Inteligente de Intención y Sentimiento para Respuestas de Campañas.

Categoriza las respuestas recibidas en:
- 'buy': Interesados, solicitud de cotización, precio, especificaciones, fotos, ubicación o llamada.
- 'sell': Ofrecen maquinaria, flotas, inventario o preguntan si compramos equipo.
- 'optout': Solicitud de desuscripción, baja, retiro de la empresa o no interesado.
- 'general': Consultas generales, acuses de recibo o neutros.
"""

import re
from utils.textutils import looks_auto

INTENT_CONFIG = {
    "buy": {
        "key": "buy",
        "label": "Interesado / Compra",
        "short_label": "Comprador",
        "badge_class": "badge-intent-buy",
        "color": "#059669",
        "bg": "#ecfdf5",
        "border": "#a7f3d0",
        "icon": "",
        "description": "Prospecto interesado, solicita precio, fotos, ficha técnica o llamada.",
    },
    "sell": {
        "key": "sell",
        "label": "Ofrece Equipo / Venta",
        "short_label": "Venta / Oferta",
        "badge_class": "badge-intent-sell",
        "color": "#0284c7",
        "bg": "#f0f9ff",
        "border": "#bae6fd",
        "icon": "",
        "description": "Ofrece maquinaria usada, flota, inventario o pregunta si compramos.",
    },
    "optout": {
        "key": "optout",
        "label": "Baja / Desuscripción",
        "short_label": "Baja",
        "badge_class": "badge-intent-optout",
        "color": "#dc2626",
        "bg": "#fef2f2",
        "border": "#fecaca",
        "icon": "",
        "description": "Pide desuscripción, no interesado, persona equivocada o ya no labora.",
    },
    "general": {
        "key": "general",
        "label": "General / Informativo",
        "short_label": "General",
        "badge_class": "badge-intent-general",
        "color": "#64748b",
        "bg": "#f8fafc",
        "border": "#e2e8f0",
        "icon": "",
        "description": "Respuesta neutra, saludo, confirmación de recibido o consulta general.",
    },
}

# 1. Patrones de Baja / Opt-out / Negativa (Tienen prioridad alta si son explícitos)
OPTOUT_PATTERNS = [
    r"\bunsubscribe\b",
    r"\bdesuscrib(?:ir|irme|ase|anse)?\b",
    r"\bdar(?:me)? de baja\b",
    r"\bremove (?:me|us|my email)\b",
    r"\bsacar(?:me)? de la lista\b",
    r"\beliminar(?:me)? de (?:la lista|su base)\b",
    r"\bborrar(?:me)? de (?:la lista|su base)\b",
    r"\btake (?:me|us) off\b",
    r"\bstop email(?:ing)?\b",
    r"\bplease stop\b",
    r"\bdo not (?:email|contact|call) (?:me|us)?\b",
    r"\bno (?:me|nos) contacten?\b",
    r"\bno (?:me|nos) interesa\b",
    r"\bnot interested\b",
    r"\bno thanks\b",
    r"\bno gracias\b",
    r"\bnot plan(?:ning)? on buying\b",
    r"\bno planeamos comprar\b",
    r"\bdon['’]?t (?:have|need|want) (?:any|more)\b",
    r"\bno (?:tenemos|necesitamos|queremos) (?:mas|más|ninguna?)\b",
    r"\bno longer (?:employed|with|working|at)\b",
    r"\bya no (?:labora|trabaja|forma parte|pertenece)\b",
    r"\bleft the company\b",
    r"\bwrong person\b",
    r"\bpersona equivocada\b",
    r"\bwrong email\b",
    r"\bspam\b",
]

# 2. Patrones de Venta / Ofrece Equipo
SELL_PATTERNS = [
    r"\b(?:we|i) have (?:equipment|machinery|machines|units|trucks|excavators|forklifts|inventory|for sale)\b",
    r"\btenemos (?:equipo|maquinaria|maquinas|máquinas|unidades|camiones|inventario|para la venta|en venta)\b",
    r"\b(?:we|i) (?:are )?selling\b",
    r"\bvendemos\b",
    r"\bofrecemos(?: para la venta| en venta)?\b",
    r"\bfor sale\b",
    r"\bpara la venta\b",
    r"\ben venta\b",
    r"\bdo you buy\b",
    r"\bustedes compran\b",
    r"\bcompran (?:maquinaria|equipo|usado)\b",
    r"\bare you buying\b",
    r"\bour fleet\b",
    r"\bnuestra flota\b",
    r"\bour inventory\b",
    r"\bnuestro inventario\b",
    r"\btrade[- ]?in\b",
    r"\bretoma\b",
    r"\bsurplus (?:equipment|machinery)\b",
    r"\bliquidating\b",
    r"\bauction\b",
    r"\bsubasta\b",
    r"\bremate\b",
]

# 3. Patrones de Compra / Interesado
BUY_PATTERNS = [
    r"\bhow much\b",
    r"\bprice\b",
    r"\bpricing\b",
    r"\bcost\b",
    r"\bquote\b",
    r"\bcotizac(?:ion|ión|iones)\b",
    r"\bcotizar\b",
    r"\bprecio\b",
    r"\bvalores\b",
    r"\bcu[aá]nto (?:cuesta|vale|piden|es)\b",
    r"\bspecs?\b",
    r"\bspecifications?\b",
    r"\bespecificaciones\b",
    r"\bficha t[eé]cnica\b",
    r"\bfotos?\b",
    r"\bpictures?\b",
    r"\bphotos?\b",
    r"\bvideos?\b",
    r"\binterested\b",
    r"\binteresad[oa]s?\b",
    r"\bme interesa\b",
    r"\bnos interesa\b",
    r"\bcall me\b",
    r"\bcontact me\b",
    r"\bll[aá]mame\b",
    r"\bll[aá]menos\b",
    r"\bcont[aá]ctame\b",
    r"\bcont[aá]ctenos\b",
    r"\bphone\b",
    r"\bcelular\b",
    r"\btel[eé]fono\b",
    r"\bwhatsapp\b",
    r"\bsend (?:me |us )?(?:info|information|details|pictures|pricing)\b",
    r"\b(?:envi|mand)(?:ar|ame|enos|eme) (?:info|informaci[oó]n|detalles|fotos|precio)\b",
    r"\bpas(?:es|ar|ame|anos|eme) (?:info|informaci[oó]n|valores|precio)\b",
    r"\bcatalo[gu]e?\b",
    r"\bcat[aá]logo\b",
    r"\bbrochure\b",
    r"\bavailable\b",
    r"\bdisponible\b",
    r"\bstill available\b",
    r"\bsigue disponible\b",
    r"\bwhere is (?:the|this|it)\b",
    r"\bd[oó]nde (?:est[aá]|queda|se encuentra)\b",
    r"\blocation\b",
    r"\bubicaci[oó]n\b",
    r"\bhours?\b",
    r"\bhoras\b",
    r"\byear\b",
    r"\ba[nñ]o\b",
    r"\bshipping\b",
    r"\bdelivery\b",
    r"\bflete\b",
    r"\benv[ií]o\b",
    r"\bwant to buy\b",
    r"\blooking to buy\b",
    r"\blooking for\b",
    r"\bbusco\b",
    r"\bbuscamos\b",
    r"\bestamos buscando\b",
    r"\bin stock\b",
    r"\ben stock\b",
]

_OPTOUT_COMPILED = [re.compile(p, re.I) for p in OPTOUT_PATTERNS]
_SELL_COMPILED = [re.compile(p, re.I) for p in SELL_PATTERNS]
_BUY_COMPILED = [re.compile(p, re.I) for p in BUY_PATTERNS]

# Patrones para detectar que un empleado ya no trabaja en la empresa en mensajes automáticos
NO_LONGER_EMPLOYED_RE = re.compile(
    r"(no longer (with|employed|working|at)|ya no (labora|trabaja|forma parte)|left the company|se retira|retirado)",
    re.I
)


def _clean_text(s: str) -> str:
    return " ".join((s or "").split())


def classify_intent(subject: str = "", snippet: str = "", is_auto: bool = False) -> dict:
    """
    Analiza una respuesta recibida y determina su intención de negocio.
    Previene falsos positivos ocasionados por el asunto citado de la campaña.
    """
    subject_clean = _clean_text(subject)
    snippet_clean = _clean_text(snippet)

    # Si es explícitamente automática o parece mensaje fuera de oficina:
    if is_auto or looks_auto(subject_clean, snippet_clean):
        # Si informa que el colaborador ya no trabaja allí, es una BAJA útil
        if NO_LONGER_EMPLOYED_RE.search(snippet_clean) or NO_LONGER_EMPLOYED_RE.search(subject_clean):
            cfg = INTENT_CONFIG["optout"]
            return {
                "intent": "optout",
                "label": cfg["label"],
                "short_label": cfg["short_label"],
                "badge_class": cfg["badge_class"],
                "icon": cfg["icon"],
                "confidence": 0.9,
                "matched_keywords": ["no longer employed / ya no labora"],
            }
        # Si es un simple fuera de oficina / vacaciones, se clasifica como general
        cfg = INTENT_CONFIG["general"]
        return {
            "intent": "general",
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "badge_class": cfg["badge_class"],
            "icon": cfg["icon"],
            "confidence": 0.8,
            "matched_keywords": ["out of office / automática"],
        }

    # Para respuestas reales de personas humanas:
    # El snippet contiene lo que realmente escribió el prospecto.
    # El asunto casi siempre es "Re: <Asunto de la Campaña>", por lo que solo se usa si
    # no empieza por Re:/Fwd: o si contiene palabras de baja/desuscripción.
    eval_text = snippet_clean
    if subject_clean and not re.match(r"^(re|fwd|rv)\s*:", subject_clean, re.I):
        eval_text = f"{subject_clean} {eval_text}"

    if not eval_text.strip():
        cfg = INTENT_CONFIG["general"]
        return {
            "intent": "general",
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "badge_class": cfg["badge_class"],
            "icon": cfg["icon"],
            "confidence": 0.0,
            "matched_keywords": [],
        }

    # 1. Comprobamos Opt-out / Baja (Prioridad alta ante rechazo explícito)
    optout_matches = [p.pattern for p in _OPTOUT_COMPILED if p.search(eval_text) or p.search(subject_clean)]
    if optout_matches:
        cfg = INTENT_CONFIG["optout"]
        return {
            "intent": "optout",
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "badge_class": cfg["badge_class"],
            "icon": cfg["icon"],
            "confidence": min(1.0, 0.6 + len(optout_matches) * 0.2),
            "matched_keywords": optout_matches[:3],
        }

    # 2. Comprobamos Sell / Ofrece equipo
    sell_matches = [p.pattern for p in _SELL_COMPILED if p.search(eval_text)]

    # 3. Comprobamos Buy / Interesado
    buy_matches = [p.pattern for p in _BUY_COMPILED if p.search(eval_text)]

    if buy_matches and not sell_matches:
        cfg = INTENT_CONFIG["buy"]
        return {
            "intent": "buy",
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "badge_class": cfg["badge_class"],
            "icon": cfg["icon"],
            "confidence": min(1.0, 0.5 + len(buy_matches) * 0.2),
            "matched_keywords": buy_matches[:3],
        }

    if sell_matches and not buy_matches:
        cfg = INTENT_CONFIG["sell"]
        return {
            "intent": "sell",
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "badge_class": cfg["badge_class"],
            "icon": cfg["icon"],
            "confidence": min(1.0, 0.5 + len(sell_matches) * 0.2),
            "matched_keywords": sell_matches[:3],
        }

    # En caso de empate, decidimos por mayor número de términos coincidentes
    if buy_matches and sell_matches:
        chosen = "buy" if len(buy_matches) >= len(sell_matches) else "sell"
        cfg = INTENT_CONFIG[chosen]
        return {
            "intent": chosen,
            "label": cfg["label"],
            "short_label": cfg["short_label"],
            "badge_class": cfg["badge_class"],
            "icon": cfg["icon"],
            "confidence": 0.65,
            "matched_keywords": (buy_matches if chosen == "buy" else sell_matches)[:3],
        }

    # 4. Por defecto, General / Informativo
    cfg = INTENT_CONFIG["general"]
    return {
        "intent": "general",
        "label": cfg["label"],
        "short_label": cfg["short_label"],
        "badge_class": cfg["badge_class"],
        "icon": cfg["icon"],
        "confidence": 0.3,
        "matched_keywords": [],
    }
