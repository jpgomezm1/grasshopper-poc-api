"""Lo que contó en el bot gratuito llega a su cuenta (B-7, Sprint 4).

Verónica, feedback de Sprint 4: *"Todo esto que te conté acá, luego cuando me
logueo o abro cuenta no me trae esta información que yo ya le di y vuelve y me
pregunta"*.

Antes había un puente por `localStorage` desde el quiz viejo (que guardaba con
otras claves, así que el onboarding igual no las reconocía) y ninguno desde el
bot conversacional. Ahora el prospecto vive en el servidor (`bot_conversations`,
B-4) y al registrarse se enlaza con la cuenta:

1. por el id que quedó en la pestaña (mismo dispositivo), o
2. por el correo, si se registró en otro (el prospecto más reciente sin cuenta).

## Solo lo que tiene equivalencia exacta

Las respuestas pasan a los hechos del onboarding (`onboarding_hechos.py`) y se
guardan con el mismo camino que usa el chat (`onboarding_chat._persistir`), así
que llegan también a las columnas que lee el recomendador. Lo que no tiene
equivalencia exacta NO se pasa: el onboarding lo pregunta normal.

- **Presupuesto:** los tramos del bot (10k / 25k) no coinciden con los del
  onboarding (5k / 15k / 30k). Pasarlo sería inventar un tramo.
- **Papá o mamá:** quien llenó el bot no es el estudiante. Se enlaza el
  prospecto (la bandeja sabe que se convirtió) pero no se le asigna una etapa.
- **"Ya me gradué" del colegio:** no dice si está en la universidad, trabajando
  o en pausa.
- **Colegio alemán o francés:** el onboarding no tiene esa opción.

Nunca pisa lo que la cuenta ya tenía: solo llena huecos.

## La bienvenida no se pierde

Los hechos que vinieron del bot quedan listados en `onboarding_answers`
(`_desde_bot_gratuito`). El onboarding lo usa para seguir mostrando la pantalla
de bienvenida (C-1) a quien solo trae eso, y para abrir el chat sin repetir lo
que ya contó.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from app.db.models import BotConversation, User

FUENTE = "bot_gratuito"
CLAVE_IMPORTADOS = "_desde_bot_gratuito"

_ETAPA_COLEGIO = {"9": "high_school_early", "10": "high_school_early", "11": "high_school", "12": "high_school"}
_ETAPA_UNIVERSIDAD = {"u1": "university", "u2": "university", "u3": "university", "u4": "recent_grad"}
_INTERES_INTERNACIONAL = {"ext": "intl_yes", "both": "intl_maybe", "local": "intl_no"}
_TIPO_COLEGIO = {"ib": "ib", "us": "american", "local": "local"}


def hechos_desde_respuestas(respuestas: Dict[str, str]) -> Dict[str, Any]:
    """Las respuestas del bot como hechos del onboarding · solo los exactos."""
    who = respuestas.get("who")
    stage = respuestas.get("stage", "")
    hechos: Dict[str, Any] = {}

    if who == "padre":
        return hechos

    if who == "colegio" and stage in _ETAPA_COLEGIO:
        hechos["life_stage"] = _ETAPA_COLEGIO[stage]
        hechos["grade"] = stage
        if respuestas.get("extra") in _TIPO_COLEGIO:
            hechos["school_accreditation"] = _TIPO_COLEGIO[respuestas["extra"]]
        if stage == "9" and respuestas.get("materias"):
            hechos["g9_materias_favoritas"] = respuestas["materias"]
    elif who == "uni" and stage in _ETAPA_UNIVERSIDAD:
        hechos["life_stage"] = _ETAPA_UNIVERSIDAD[stage]
    elif who == "pro":
        hechos["life_stage"] = "working"

    if respuestas.get("dest") in _INTERES_INTERNACIONAL:
        hechos["international_interest"] = _INTERES_INTERNACIONAL[respuestas["dest"]]
    if respuestas.get("flow"):
        hechos["voice_passion"] = respuestas["flow"]
    return hechos


def _buscar_prospecto(db: Any, user: User, lead_id: Optional[UUID]) -> Optional[BotConversation]:
    def es_suyo_o_libre(lead: BotConversation) -> bool:
        return lead.converted_user_id in (None, user.id)

    if lead_id is not None:
        lead = db.query(BotConversation).filter(BotConversation.id == lead_id).first()
        if lead is not None and (lead.hechos or {}).get("_fuente") == FUENTE and es_suyo_o_libre(lead):
            return lead

    email = (user.email or "").strip().lower()
    if not email:
        return None
    candidatos = (
        db.query(BotConversation)
        .filter(BotConversation.email == email, BotConversation.converted_user_id.is_(None))
        .order_by(BotConversation.created_at.desc())
        .all()
    )
    return next((c for c in candidatos if (c.hechos or {}).get("_fuente") == FUENTE), None)


def traspasar(db: Any, user: User, lead_id: Optional[UUID] = None) -> Dict[str, Any]:
    """Enlaza el prospecto con la cuenta y pasa lo que tiene equivalencia.

    Devuelve qué hechos se pasaron. Idempotente: si ya estaba enlazado a esta
    cuenta, no duplica nada.
    """
    from app.api.v1.onboarding_chat import _hechos_del_usuario, _persistir

    lead = _buscar_prospecto(db, user, lead_id)
    if lead is None:
        return {"importado": False, "hechos": []}

    ya_tiene = _hechos_del_usuario(user)
    nuevos = {
        k: v for k, v in hechos_desde_respuestas((lead.hechos or {}).get("respuestas") or {}).items()
        if k not in ya_tiene
    }

    lead.converted_user_id = user.id
    if nuevos:
        importados: List[str] = sorted(
            set((user.onboarding_answers or {}).get(CLAVE_IMPORTADOS) or []) | set(nuevos)
        )
        user.onboarding_answers = {**(user.onboarding_answers or {}), CLAVE_IMPORTADOS: importados}
        _persistir(db, user, nuevos)  # hace commit
    else:
        db.commit()
    return {"importado": True, "hechos": sorted(nuevos)}


def solo_trae_lo_del_bot(user: User, conocidos: Dict[str, Any]) -> bool:
    """True si todo lo que se sabe de esta persona vino del bot gratuito.

    Para el onboarding: a esa persona se le sigue mostrando la bienvenida (C-1),
    porque todavía no ha conversado con Hopper.
    """
    importados = set((user.onboarding_answers or {}).get(CLAVE_IMPORTADOS) or [])
    return bool(importados) and set(conocidos) <= importados
