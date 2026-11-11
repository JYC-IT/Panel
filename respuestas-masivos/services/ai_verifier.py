"""Motor de Verificación con IA para KPs en Close CRM (Talked to KP, #EKP y #TKP).

Combina:
1. Análisis de transcripciones de Close Notetaker AI (utterances, speakers, summary_text) y duración real.
2. Validación cruzada en tiempo real contra actividades reales de Email e SMS en el Lead de Close CRM.
3. Evaluación mediante LLM (Google Gemini 2.5 Flash vía google-genai) cuando GEMINI_API_KEY está configurada,
   con motor semántico determinista de respaldo que funciona 100% sin dependencias externas.
4. Caché persistente en SQLite (tabla `ai_verifications`) para respuestas instantáneas.
"""
import json
import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import requests
from dotenv import load_dotenv

import db
from connectors import close_crm

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

BASE_URL = close_crm.BASE_URL


def _get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def _get_cached_verifications(activity_ids):
    if not activity_ids:
        return {}
    placeholders = ",".join("?" for _ in activity_ids)
    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM ai_verifications WHERE activity_id IN ({placeholders})",
            list(activity_ids),
        ).fetchall()
    return {r["activity_id"]: dict(r) for r in rows}


def _save_verification(record):
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO ai_verifications
               (activity_id, activity_type, user_id, verdict, category, score, reason, evidence, summary, model_used, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(activity_id) DO UPDATE SET
                   verdict=excluded.verdict,
                   category=excluded.category,
                   score=excluded.score,
                   reason=excluded.reason,
                   evidence=excluded.evidence,
                   summary=excluded.summary,
                   model_used=excluded.model_used,
                   analyzed_at=CURRENT_TIMESTAMP""",
            (
                record["activity_id"],
                record["activity_type"],
                record.get("user_id", ""),
                record["verdict"],
                record.get("category", ""),
                int(record.get("score", 0)),
                record.get("reason", ""),
                record.get("evidence", ""),
                record.get("summary", ""),
                record.get("model_used", "Close-AI-Audit"),
            ),
        )


def _format_utterances_dialogue(utterances, max_chars=4500):
    lines = []
    total = 0
    for u in utterances or []:
        side = "Asesor" if u.get("speaker_side") == "close-user" else "Contacto"
        label = u.get("speaker_label") or side
        txt = (u.get("text") or "").strip()
        if not txt:
            continue
        line = f"[{side} - {label}]: {txt}"
        lines.append(line)
        total += len(line)
        if total >= max_chars:
            break
    return "\n".join(lines)


def _analyze_call_with_gemini(client, duration, note, summary_text, dialogue):
    prompt = f"""Eres un auditor comercial experto en ventas B2B de maquinaria pesada y equipos médicos (JYC Equipment).
Debes verificar si esta llamada telefónica, marcada por el asesor como "Talked to KP" (Habló con Persona Clave / Tomador de Decisión), realmente fue una conversación real con el KP.

Datos de la llamada:
- Duración total: {duration} segundos
- Nota del asesor: {note or "(sin nota)"}
- Resumen automático Close: {summary_text or "(sin resumen)"}
- Transcripción parcial:
{dialogue or "(sin transcripción)"}

Reglas estrictas de clasificación:
1. "INVALIDO": Si fue buzón de voz / contestadora (voicemail), menú automático / operadora / música en espera (IVR), llamada cortada antes de hablar, o si no hubo interacción humana real.
2. "SOSPECHOSO": Si solo habló con una recepcionista / asistente / gatekeeper que tomó un mensaje o dijo que el KP no estaba, o si la conversación fue demasiado breve o ambigua sin validar interés/decisión del KP.
3. "VERIFICADO": Si realmente existió diálogo bilateral directo con el tomador de decisión / persona clave sobre equipos, necesidades, cotización, inventario, compra/venta o seguimiento comercial (incluso si el KP dijo que no tiene equipos por ahora, siempre y cuando sea el KP real quien respondió).

Responde ÚNICAMENTE con un objeto JSON válido (sin markdown ni texto extra) con estas claves exactas:
{{
  "verdict": "VERIFICADO" | "SOSPECHOSO" | "INVALIDO",
  "category": "KP Real" | "Buzón de Voz" | "Sistema IVR / Espera" | "Recepcionista / Gatekeeper" | "Llamada Corta / Sin Diálogo",
  "score": <entero de 0 a 100>,
  "reason": "<explicación directa y concisa en español en 1 o 2 frases>"
}}"""
    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
        data = json.loads(raw)
        if data.get("verdict") in ("VERIFICADO", "SOSPECHOSO", "INVALIDO"):
            return data
    except Exception:
        pass
    return None


def _analyze_call_heuristic(duration, disposition, note, rt):
    """Analizador semántico basado en Close Notetaker AI (utterances, speakers, summary_text) y reglas de negocio."""
    summary_text = (rt.get("summary_text") or "").strip()
    utterances = rt.get("utterances") or []
    speakers = rt.get("speakers") or []

    user_talk_s = sum(float(s.get("talk_time") or 0) for s in speakers if s.get("speaker_side") == "close-user")
    contact_talk_s = sum(float(s.get("talk_time") or 0) for s in speakers if s.get("speaker_side") == "contact")

    user_turns = [u for u in utterances if u.get("speaker_side") == "close-user" and len((u.get("text") or "").strip()) > 3]
    contact_turns = [u for u in utterances if u.get("speaker_side") == "contact" and len((u.get("text") or "").strip()) > 3]

    combined_lower = (summary_text + "\n" + " ".join((u.get("text") or "") for u in utterances)).lower()
    summary_lower = summary_text.lower()
    note_lower = (note or "").lower()

    # 1. Llamadas vacías o ultracortas (< 10s)
    if duration < 10 or disposition in ("no-answer", "busy", "failed", "canceled"):
        return {
            "verdict": "INVALIDO",
            "category": "Llamada Corta / Sin Diálogo",
            "score": 5,
            "reason": f"Duración insuficiente ({duration}s) o sin conexión; no pudo existir diálogo real con un KP.",
            "model_used": "Close-AI-Audit",
        }

    # 2. Detección de buzón de voz / contestadora
    vm_markers = (
        "voicemail", "voice mail", "leave a message", "leave your message",
        "after the tone", "after the beep", "not available to take your call",
        "mailbox", "reached the voicemail", "buzón de voz", "deje su mensaje"
    )
    if disposition == "voicemail" or any(m in summary_lower for m in ("voicemail", "left a message", "voice mail", "not reached")):
        return {
            "verdict": "INVALIDO",
            "category": "Buzón de Voz",
            "score": 10,
            "reason": "La transcripción indica que la llamada cayó en buzón de voz (voicemail) y no habló con el KP.",
            "model_used": "Close-AI-Audit",
        }

    # 3. Sin transcripción
    if not rt or (not summary_text and not utterances):
        if duration < 25:
            return {
                "verdict": "INVALIDO",
                "category": "Sin Audio / Muy Corta",
                "score": 20,
                "reason": f"Llamada de apenas {duration}s sin transcripción ni evidencia de diálogo con KP.",
                "model_used": "Close-AI-Audit",
            }
        return {
            "verdict": "SOSPECHOSO",
            "category": "Sin Transcripción",
            "score": 50,
            "reason": f"Llamada de {duration}s sin transcripción automática disponible. Se recomienda escuchar el audio.",
            "model_used": "Close-AI-Audit",
        }

    # 4. Sistema automático / IVR / Música de espera sin diálogo del asesor
    ivr_markers = (
        "automated system", "promotional messaging", "press 1", "press 2", "press 0",
        "if you know your party's extension", "operator will be with you", "thank you for holding"
    )
    if any(m in summary_lower for m in ("automated system", "promotional messaging", "menu")) and len(user_turns) <= 2:
        return {
            "verdict": "INVALIDO",
            "category": "Sistema IVR / Espera",
            "score": 12,
            "reason": "La llamada quedó atrapada en un sistema automático o menú telefónico sin llegar al KP.",
            "model_used": "Close-AI-Audit",
        }

    if len(user_turns) == 0 or user_talk_s < 4.0:
        if any(m in combined_lower for m in vm_markers):
            return {
                "verdict": "INVALIDO",
                "category": "Buzón de Voz",
                "score": 10,
                "reason": "Solo se detectó grabación de buzón de voz; el asesor no interactuó con el KP.",
                "model_used": "Close-AI-Audit",
            }
        return {
            "verdict": "INVALIDO",
            "category": "Sin Diálogo Bilateral",
            "score": 15,
            "reason": f"El asesor prácticamente no habló en la grabación ({int(user_talk_s)}s), probable menú IVR o llamada en espera.",
            "model_used": "Close-AI-Audit",
        }

    # 5. Recepcionista / Gatekeeper (no habló con el KP objetivo)
    gk_phrases = (
        "seeking to speak with", "indicated that", "is not in", "is unavailable",
        "out of the office", "stepped away", "take a message", "send an email",
        "not at his desk", "not at her desk", "receptionist", "assistant",
        "forward your call", "transferred to voicemail"
    )
    kp_business_phrases = (
        "equipment", "forklift", "machinery", "mri", "imaging", "trade-in",
        "surplus", "quote", "price", "buy", "sell", "purchasing", "inventory",
        "not involved in", "nothing for sale", "currently has no", "available for sale",
        "follow up", "reach out in", "upgrade", "fleet", "crane", "loader", "skid steer"
    )
    has_gk_hit = any(p in summary_lower for p in gk_phrases)
    has_business_hit = any(p in combined_lower for p in kp_business_phrases)

    if has_gk_hit and not has_business_hit and len(contact_turns) <= 5:
        return {
            "verdict": "SOSPECHOSO",
            "category": "Recepcionista / Gatekeeper",
            "score": 38,
            "reason": "Parece haber hablado solo con recepción o asistente sin llegar directamente al KP.",
            "model_used": "Close-AI-Audit",
        }

    if any(m in summary_lower for m in ("voicemail",)) and has_gk_hit:
        return {
            "verdict": "INVALIDO",
            "category": "Gatekeeper -> Buzón de Voz",
            "score": 18,
            "reason": "La llamada fue transferida por recepción al buzón de voz sin contactar al KP.",
            "model_used": "Close-AI-Audit",
        }

    # 6. Conversación real confirmada
    if len(user_turns) >= 2 and len(contact_turns) >= 2 and (contact_talk_s >= 12.0 or has_business_hit):
        first_bullet = ""
        if summary_text:
            clean_bullets = [b.strip("- ").strip() for b in summary_text.splitlines() if b.strip().startswith("-")]
            if clean_bullets:
                first_bullet = clean_bullets[0]
        reason = f"Diálogo real bilateral ({int(user_talk_s)}s asesor / {int(contact_talk_s)}s contacto)."
        if first_bullet:
            reason = f"{first_bullet[:160]}"
        return {
            "verdict": "VERIFICADO",
            "category": "KP Real",
            "score": 92 if has_business_hit else 80,
            "reason": reason,
            "model_used": "Close-AI-Audit",
        }

    return {
        "verdict": "SOSPECHOSO",
        "category": "Diálogo Muy Breve",
        "score": 48,
        "reason": f"Interacción corta ({int(user_talk_s)}s asesor / {int(contact_talk_s)}s contacto) sin claridad de haber hablado con el KP.",
        "model_used": "Close-AI-Audit",
    }


def verify_kp_calls_batch(call_records, force=False):
    """Audita con IA una lista de llamadas marcadas como 'Talked to KP'."""
    if not call_records:
        return []

    ids = [c["id"] for c in call_records if c.get("id")]
    cached = {} if force else _get_cached_verifications(ids)
    missing_ids = [cid for cid in ids if cid not in cached]

    gemini_client = _get_gemini_client() if missing_ids else None

    # Fetch full details with recording_transcript for missing IDs in parallel
    auth = close_crm._get_auth()
    detailed_map = {}

    def _fetch_detail(cid):
        if not auth:
            return cid, None
        try:
            r = requests.get(
                f"{BASE_URL}/activity/call/{cid}/",
                auth=auth,
                params={"_fields": "id,user_id,lead_id,duration,direction,disposition,note,date_created,recording_url,recording_transcript"},
                timeout=15,
            )
            if r.status_code == 200:
                return cid, r.json()
        except Exception:
            pass
        return cid, None

    if missing_ids:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for cid, detail in pool.map(_fetch_detail, missing_ids):
                if detail:
                    detailed_map[cid] = detail

    results = []
    for base_c in call_records:
        cid = base_c.get("id")
        if not cid:
            continue

        if cid in cached and not force:
            audit = cached[cid]
        else:
            c = detailed_map.get(cid) or base_c
            duration = int(c.get("duration") or 0)
            disposition = c.get("disposition") or ""
            note = c.get("note") or ""
            rt = c.get("recording_transcript") or {}
            summary_text = (rt.get("summary_text") or "").strip()
            utterances = rt.get("utterances") or []
            dialogue = _format_utterances_dialogue(utterances)

            llm_out = None
            if gemini_client and duration >= 10 and (summary_text or dialogue):
                llm_out = _analyze_call_with_gemini(gemini_client, duration, note, summary_text, dialogue)
                if llm_out:
                    llm_out["model_used"] = "Gemini-2.5-Flash"

            if not llm_out:
                llm_out = _analyze_call_heuristic(duration, disposition, note, rt)

            audit = {
                "activity_id": cid,
                "activity_type": "call_kp",
                "user_id": c.get("user_id") or base_c.get("user_id", ""),
                "verdict": llm_out["verdict"],
                "category": llm_out["category"],
                "score": int(llm_out.get("score", 50)),
                "reason": llm_out["reason"],
                "evidence": dialogue[:1200] if dialogue else note[:400],
                "summary": summary_text[:600],
                "model_used": llm_out.get("model_used", "Close-AI-Audit"),
            }
            _save_verification(audit)

        results.append({
            "id": cid,
            "user_id": base_c.get("user_id"),
            "user_name": base_c.get("user_name"),
            "lead_id": base_c.get("lead_id"),
            "lead_name": base_c.get("lead_name") or base_c.get("lead_id") or "Sin Lead",
            "date": (base_c.get("date_created") or "")[:16].replace("T", " "),
            "duration": int(base_c.get("duration") or 0),
            "direction": base_c.get("direction") or "outbound",
            "has_recording": bool(base_c.get("recording_url") or base_c.get("has_recording")),
            "verdict": audit["verdict"],
            "category": audit["category"],
            "score": audit["score"],
            "reason": audit["reason"],
            "summary": audit.get("summary") or "",
            "evidence": audit.get("evidence") or "",
            "model_used": audit.get("model_used") or "Close-AI-Audit",
        })

    # Order: INVALIDO first, then SOSPECHOSO, then VERIFICADO
    order_rank = {"INVALIDO": 0, "SOSPECHOSO": 1, "VERIFICADO": 2}
    results.sort(key=lambda x: (order_rank.get(x["verdict"], 9), -x["score"], x["date"]))
    return results


def _analyze_tag_with_gemini(client, tag_type, note_text, emails, sms_list):
    if tag_type == "EKP":
        ev_lines = [
            f"- [{e.get('direction', '').upper()}] Fecha: {(e.get('date_created') or '')[:10]} | Asunto: {e.get('subject') or ''} | Texto: {(e.get('body_text') or e.get('snippet') or '')[:250]}"
            for e in (emails or [])[:6]
        ]
    else:
        ev_lines = [
            f"- [{s.get('direction', '').upper()}] Fecha: {(s.get('date_created') or '')[:10]} | Texto: {(s.get('text') or '')[:250]}"
            for s in (sms_list or [])[:8]
        ]
    ev_block = "\n".join(ev_lines) if ev_lines else "(Sin actividades registradas en el Lead)"

    prompt = f"""Eres un auditor comercial de JYC Equipment. Debes verificar si este registro marcado como #{tag_type} es legítimo según el CRM.
Reglas:
- Un #EKP (Email KP) requiere evidencia de interacción real por correo electrónico con la Persona Clave (idealmente correo entrante/respuesta del cliente o conversación documentada seria sobre maquinaria/negocio).
- Un #TKP (Text KP) requiere evidencia de interacción real por SMS/texto con la Persona Clave (idealmente SMS entrante del cliente o diálogo bilateral).
- Si no hay correos/SMS en el Lead que respalden el tag, o si solo hay envíos salientes masivos sin respuesta, o la nota está vacía sin explicar qué respondió el KP, debe marcarse como INVALIDO o SOSPECHOSO.

Registro:
- Tipo: #{tag_type}
- Nota del asesor: {note_text}
- Historial real en Close CRM del Lead:
{ev_block}

Responde ÚNICAMENTE JSON válido:
{{
  "verdict": "VERIFICADO" | "SOSPECHOSO" | "INVALIDO",
  "category": "Confirmado con Respuesta" | "Solo Saliente / Sin Respuesta" | "Nota Insuficiente" | "Sin Evidencia en CRM",
  "score": <entero 0-100>,
  "reason": "<explicación clara en español de 1 a 2 frases>"
}}"""
    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
        data = json.loads(raw)
        if data.get("verdict") in ("VERIFICADO", "SOSPECHOSO", "INVALIDO"):
            return data
    except Exception:
        pass
    return None


def _analyze_tag_heuristic(tag_type, note_text, emails, sms_list):
    clean_note = re.sub(r"#(ekp|tkp)\b", "", note_text or "", flags=re.IGNORECASE).strip(" :-\n\t")
    note_len = len(clean_note)

    if tag_type == "EKP":
        incoming = [e for e in (emails or []) if e.get("direction") == "incoming"]
        outgoing = [e for e in (emails or []) if e.get("direction") == "outgoing"]
        if not emails:
            return {
                "verdict": "INVALIDO",
                "category": "Sin Evidencia en CRM",
                "score": 10,
                "reason": "El lead no registra ningún correo electrónico (ni entrante ni saliente) en Close CRM que respalde el #EKP.",
                "evidence": "0 emails en Close CRM",
                "model_used": "Close-AI-Audit",
            }
        if incoming:
            latest = incoming[0]
            subj = latest.get("subject") or "(sin asunto)"
            if note_len < 12:
                return {
                    "verdict": "SOSPECHOSO",
                    "category": "Nota Insuficiente",
                    "score": 60,
                    "reason": f"Hay {len(incoming)} email(s) entrante(s), pero la nota no detalla qué respondió el KP.",
                    "evidence": f"{len(incoming)} entrantes | Último: {subj[:80]}",
                    "model_used": "Close-AI-Audit",
                }
            return {
                "verdict": "VERIFICADO",
                "category": "Confirmado con Respuesta",
                "score": 95,
                "reason": f"Respaldado con {len(incoming)} correo(s) entrante(s) reales del cliente y nota comercial descriptiva.",
                "evidence": f"{len(incoming)} entrantes, {len(outgoing)} salientes | {subj[:80]}",
                "model_used": "Close-AI-Audit",
            }
        # Solo salientes
        return {
            "verdict": "SOSPECHOSO",
            "category": "Solo Saliente / Sin Respuesta",
            "score": 40,
            "reason": f"El lead solo registra {len(outgoing)} email(s) saliente(s) sin respuesta entrante del KP en Close CRM.",
            "evidence": f"0 entrantes, {len(outgoing)} salientes",
            "model_used": "Close-AI-Audit",
        }

    else:  # TKP
        inbound = [s for s in (sms_list or []) if s.get("direction") == "inbound"]
        outbound = [s for s in (sms_list or []) if s.get("direction") == "outbound"]
        if not sms_list:
            return {
                "verdict": "INVALIDO",
                "category": "Sin Evidencia en CRM",
                "score": 10,
                "reason": "El lead no registra ningún SMS en Close CRM que respalde este #TKP.",
                "evidence": "0 SMS en Close CRM",
                "model_used": "Close-AI-Audit",
            }
        if inbound:
            latest_txt = (inbound[0].get("text") or "").strip() or "(imagen/archivo)"
            if note_len < 12:
                return {
                    "verdict": "SOSPECHOSO",
                    "category": "Nota Insuficiente",
                    "score": 60,
                    "reason": f"Hay {len(inbound)} SMS entrante(s), pero la nota del asesor carece de contexto.",
                    "evidence": f"{len(inbound)} SMS entrantes | Último: {latest_txt[:70]}",
                    "model_used": "Close-AI-Audit",
                }
            return {
                "verdict": "VERIFICADO",
                "category": "Confirmado con Respuesta",
                "score": 95,
                "reason": f"Respaldado con {len(inbound)} SMS entrante(s) reales del contacto en Close CRM y nota detallada.",
                "evidence": f"{len(inbound)} entrantes, {len(outbound)} salientes | Último: {latest_txt[:70]}",
                "model_used": "Close-AI-Audit",
            }
        return {
            "verdict": "SOSPECHOSO",
            "category": "Solo Saliente / Sin Respuesta",
            "score": 40,
            "reason": f"El lead solo registra {len(outbound)} SMS saliente(s) sin respuesta entrante del contacto.",
            "evidence": f"0 entrantes, {len(outbound)} salientes",
            "model_used": "Close-AI-Audit",
        }


def verify_tagged_kps_batch(tagged_records, force=False):
    """Audita con IA los registros marcados con #EKP y #TKP cruzando Email y SMS reales en Close CRM."""
    if not tagged_records:
        return []

    # Generate stable activity_id if missing
    for idx, r in enumerate(tagged_records):
        if not r.get("activity_id"):
            r["activity_id"] = f"tag_{r.get('type')}_{r.get('user_id')}_{r.get('lead_id')}_{(r.get('date') or '')[:19]}"

    ids = [r["activity_id"] for r in tagged_records]
    cached = {} if force else _get_cached_verifications(ids)
    missing_records = [r for r in tagged_records if r["activity_id"] not in cached]

    lead_ids_needed = list({r["lead_id"] for r in missing_records if r.get("lead_id")})
    lead_evidence_map = {}

    auth = close_crm._get_auth()

    def _fetch_lead_comms(lid):
        emails, sms = [], []
        if not auth:
            return lid, emails, sms
        try:
            r_em = requests.get(
                f"{BASE_URL}/activity/email/",
                auth=auth,
                params={"lead_id": lid, "_limit": 10, "_fields": "id,direction,subject,body_text,date_created"},
                timeout=12,
            )
            if r_em.status_code == 200:
                emails = r_em.json().get("data", [])
        except Exception:
            pass
        try:
            r_sm = requests.get(
                f"{BASE_URL}/activity/sms/",
                auth=auth,
                params={"lead_id": lid, "_limit": 10, "_fields": "id,direction,text,date_created"},
                timeout=12,
            )
            if r_sm.status_code == 200:
                sms = r_sm.json().get("data", [])
        except Exception:
            pass
        return lid, emails, sms

    if lead_ids_needed:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for lid, ems, sms_l in pool.map(_fetch_lead_comms, lead_ids_needed):
                lead_evidence_map[lid] = (ems, sms_l)

    gemini_client = _get_gemini_client() if missing_records else None

    results = []
    for r in tagged_records:
        aid = r["activity_id"]
        if aid in cached and not force:
            audit = cached[aid]
        else:
            lid = r.get("lead_id")
            ems, sms_l = lead_evidence_map.get(lid, ([], []))
            heur = _analyze_tag_heuristic(r["type"], r.get("text", ""), ems, sms_l)

            llm_out = None
            if gemini_client:
                llm_out = _analyze_tag_with_gemini(gemini_client, r["type"], r.get("text", ""), ems, sms_l)
                if llm_out:
                    llm_out["model_used"] = "Gemini-2.5-Flash"
                    llm_out["evidence"] = heur.get("evidence", "")

            final = llm_out or heur
            audit = {
                "activity_id": aid,
                "activity_type": f"tag_{r['type'].lower()}",
                "user_id": r.get("user_id", ""),
                "verdict": final["verdict"],
                "category": final["category"],
                "score": int(final.get("score", 50)),
                "reason": final["reason"],
                "evidence": final.get("evidence", ""),
                "summary": "",
                "model_used": final.get("model_used", "Close-AI-Audit"),
            }
            _save_verification(audit)

        results.append({
            "activity_id": aid,
            "type": r["type"],
            "user_id": r.get("user_id"),
            "user_name": r.get("user_name"),
            "lead_id": r.get("lead_id"),
            "lead_name": r.get("lead_name") or r.get("lead_id") or "Sin Lead",
            "date": (r.get("date") or "")[:16].replace("T", " "),
            "text": r.get("text") or "",
            "verdict": audit["verdict"],
            "category": audit["category"],
            "score": audit["score"],
            "reason": audit["reason"],
            "evidence": audit.get("evidence") or "",
            "model_used": audit.get("model_used") or "Close-AI-Audit",
        })

    order_rank = {"INVALIDO": 0, "SOSPECHOSO": 1, "VERIFICADO": 2}
    results.sort(key=lambda x: (order_rank.get(x["verdict"], 9), -x["score"], x["date"]))
    return results
