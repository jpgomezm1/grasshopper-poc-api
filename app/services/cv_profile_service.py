"""A3 · Las preguntas previas y las ediciones de la Hoja de Vida.

Feedback literal de la clienta:

    "Hoja de vida: antes de generarla debe preguntar QUÉ HAGO ACTUALMENTE y EN QUÉ
     COLEGIO ESTUDIO (si estoy en colegio). El resto (integrar perfiles + tests +
     lo subido) está muy chévere. Además DEBE PODER EDITARSE (habrá cosas que uno
     quiera quitar o mejorar)."

Tres cosas, y las tres se implementan al pie de la letra:

1. **Antes de generarla** → `is_ready()` es falso hasta que responda, y el endpoint
   del PDF se niega a generar. No es un aviso que se pueda saltar: ella dijo
   "antes".
2. **"si estoy en colegio"** → el colegio se pregunta *condicionalmente*. A quien
   ya trabaja o terminó el colegio no se le pide. Pedirle el colegio a alguien que
   no estudia sería justo el tipo de pregunta sin sentido que criticó Sandra.
3. **"debe poder editarse"** → `apply_overrides()` deja cambiar cada campo y
   *quitar* actividades y tests. Ella dijo "quitar o mejorar": las dos.

Lo que NO se toca es el resto del CV: sobre integrar perfil + tests + lo subido
dijo textualmente "está muy chévere".
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import CVProfile

# Las opciones de "¿qué haces actualmente?". `requires_school` marca cuáles
# disparan la segunda pregunta — el "si estoy en colegio" de su feedback.
OCCUPATION_CHOICES: List[Dict[str, Any]] = [
    {
        "value": "school",
        "label": "Estoy en el colegio",
        "detail_label": "¿En qué colegio estudias?",
        "requires_school": True,
    },
    {
        "value": "gap_year",
        "label": "Terminé el colegio y estoy definiendo qué sigue",
        "detail_label": "¿En qué colegio te graduaste? (opcional)",
        "requires_school": False,
    },
    {
        "value": "university",
        "label": "Estoy estudiando en la universidad",
        "detail_label": "¿Qué estudias y dónde?",
        "requires_school": False,
    },
    {
        "value": "working",
        "label": "Estoy trabajando",
        "detail_label": "¿En qué trabajas?",
        "requires_school": False,
    },
    {
        "value": "studying_and_working",
        "label": "Estudio y trabajo",
        "detail_label": "Cuéntanos dónde estudias y en qué trabajas",
        "requires_school": False,
    },
    {
        "value": "other",
        "label": "Otra cosa",
        "detail_label": "¿Qué estás haciendo?",
        "requires_school": False,
    },
]

_VALID_OCCUPATIONS = {o["value"] for o in OCCUPATION_CHOICES}
_SCHOOL_OCCUPATIONS = {o["value"] for o in OCCUPATION_CHOICES if o["requires_school"]}

# Campos de texto que el estudiante puede reescribir.
_TEXT_FIELDS = ("headline", "summary")
# Campos de lista que puede reescribir (quitar ítems o mejorar la redacción).
_LIST_FIELDS = ("strengths", "interests", "values", "career_paths")
# Lo que puede quitar del CV sin reescribirlo.
_EXCLUSION_FIELDS = ("excluded_activity_ids", "excluded_test_ids")


class CVProfileIncomplete(RuntimeError):
    """Todavía no respondió las preguntas previas · A3."""


def get_profile(db: DBSession, user_id: UUID) -> Optional[CVProfile]:
    return db.query(CVProfile).filter(CVProfile.user_id == user_id).first()


def requires_school(occupation: Optional[str]) -> bool:
    """El "si estoy en colegio" de su feedback."""
    return occupation in _SCHOOL_OCCUPATIONS


def is_ready(profile: Optional[CVProfile]) -> bool:
    """¿Ya respondió lo que hay que preguntar ANTES de generar la hoja de vida?

    Siempre hace falta "qué hago actualmente". El colegio solo cuando aplica: es
    literal en su texto ("si estoy en colegio").
    """
    if profile is None or not profile.current_occupation:
        return False
    if requires_school(profile.current_occupation):
        return bool((profile.school_name or "").strip())
    return True


def missing_answers(profile: Optional[CVProfile]) -> List[str]:
    """Qué falta por responder · el front lo usa para saber dónde parar."""
    faltan: List[str] = []
    if profile is None or not profile.current_occupation:
        faltan.append("current_occupation")
    elif requires_school(profile.current_occupation) and not (
        profile.school_name or ""
    ).strip():
        faltan.append("school_name")
    return faltan


def _clean_text(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:limite] if texto else None


def _clean_list(valor: Any, limite_items: int = 12, limite_texto: int = 300) -> List[str]:
    if not isinstance(valor, list):
        return []
    limpias = []
    for item in valor:
        texto = _clean_text(item, limite_texto)
        if texto:
            limpias.append(texto)
    return limpias[:limite_items]


def save_answers(
    db: DBSession,
    user_id: UUID,
    *,
    current_occupation: Optional[str] = None,
    occupation_detail: Optional[str] = None,
    school_name: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> CVProfile:
    """Guarda las respuestas previas y/o las ediciones.

    Es un PUT parcial a propósito: la pantalla primero pregunta y después deja
    editar, y no tiene sentido obligar a reenviar todo en cada paso.
    """
    profile = get_profile(db, user_id)
    if profile is None:
        profile = CVProfile(user_id=user_id)
        db.add(profile)

    if current_occupation is not None:
        if current_occupation not in _VALID_OCCUPATIONS:
            raise ValueError(f"ocupación desconocida: {current_occupation}")
        profile.current_occupation = current_occupation
        # Si dejó de estar en el colegio, el nombre del colegio deja de aplicar y
        # arrastrarlo pondría un dato viejo en el PDF.
        if not requires_school(current_occupation) and current_occupation != "gap_year":
            profile.school_name = None
        profile.studies_at_school = requires_school(current_occupation)

    if occupation_detail is not None:
        profile.occupation_detail = _clean_text(occupation_detail, 200)

    if school_name is not None:
        profile.school_name = _clean_text(school_name, 200)

    if overrides is not None:
        limpio: Dict[str, Any] = dict(profile.overrides or {})
        for campo in _TEXT_FIELDS:
            if campo in overrides:
                limpio[campo] = _clean_text(overrides[campo], 2000)
        for campo in _LIST_FIELDS:
            if campo in overrides:
                limpio[campo] = _clean_list(overrides[campo])
        for campo in _EXCLUSION_FIELDS:
            if campo in overrides:
                limpio[campo] = [str(x) for x in (overrides[campo] or [])][:200]
        profile.overrides = limpio

    if is_ready(profile) and profile.answered_at is None:
        profile.answered_at = datetime.utcnow()
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)
    return profile


def save_formato(
    db: DBSession,
    user_id: UUID,
    *,
    estandar: Optional[str] = None,
    estilo: Optional[str] = None,
    incluir_foto: Optional[bool] = None,
) -> CVProfile:
    """Guarda a qué destino va la hoja de vida y cómo se ve · migración 063.

    Va aparte de `save_answers` porque son decisiones de otra naturaleza: las de
    allá son las preguntas que la clienta pidió *antes* de generar el CV, y sin
    ellas no se genera. Estas son preferencias — sin ellas el CV sale igual, en
    `latam` + `clásico`.

    Las claves se validan contra `cv_variants` y no contra una lista repetida
    aquí: dos listas de estándares que se desincronizan es exactamente el bug
    que este repo ya pagó dos veces.
    """
    from app.services.cv_variants import ESTANDARES, ESTILOS

    profile = get_profile(db, user_id)
    if profile is None:
        profile = CVProfile(user_id=user_id)
        db.add(profile)

    if estandar is not None:
        if estandar not in ESTANDARES:
            raise ValueError(f"estándar desconocido: {estandar}")
        profile.estandar = estandar

    if estilo is not None:
        if estilo not in ESTILOS:
            raise ValueError(f"estilo desconocido: {estilo}")
        profile.estilo = estilo

    if incluir_foto is not None:
        profile.incluir_foto = bool(incluir_foto)

    profile.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return profile


def preferencias_formato(profile: Optional[CVProfile]) -> Dict[str, Any]:
    """Lo que eligió el estudiante, con los valores por defecto ya resueltos."""
    from app.services.cv_variants import ESTANDAR_POR_DEFECTO, ESTILO_POR_DEFECTO

    return {
        "estandar": getattr(profile, "estandar", None) or ESTANDAR_POR_DEFECTO,
        "estilo": getattr(profile, "estilo", None) or ESTILO_POR_DEFECTO,
        # Sin decisión explícita se incluye: quien subió una foto la subió para
        # que salga. El estándar `us` la omite igual, sin preguntar.
        "incluir_foto": (
            True if getattr(profile, "incluir_foto", None) is None
            else bool(profile.incluir_foto)
        ),
    }


def occupation_line(profile: Optional[CVProfile]) -> Optional[str]:
    """Una línea para el encabezado del CV: "Estoy en el colegio · Colegio Cumbres"."""
    if profile is None or not profile.current_occupation:
        return None
    etiqueta = next(
        (o["label"] for o in OCCUPATION_CHOICES if o["value"] == profile.current_occupation),
        None,
    )
    if not etiqueta:
        return None
    detalle = (profile.occupation_detail or "").strip()
    if not detalle and requires_school(profile.current_occupation):
        detalle = (profile.school_name or "").strip()
    return f"{etiqueta} · {detalle}" if detalle else etiqueta


def apply_overrides(cv: Any, profile: Optional[CVProfile]) -> Any:
    """Aplica sobre el `CVData` ya construido lo que el estudiante editó o quitó.

    Se aplica DESPUÉS de `build_cv_data` en vez de dentro: así el generador sigue
    siendo la única fuente del contenido base, y lo del estudiante es una capa
    encima que se puede quitar entera si algo sale mal.
    """
    if profile is None:
        return cv

    # El colegio que él escribió manda sobre el del registro: puede haberse
    # cambiado de colegio, o no tener uno asignado en la plataforma.
    if (profile.school_name or "").strip():
        cv.school_name = profile.school_name.strip()

    linea = occupation_line(profile)
    if linea:
        cv.current_occupation = linea

    overrides = profile.overrides or {}
    if not isinstance(overrides, dict):
        return cv

    for campo in _TEXT_FIELDS:
        if campo in overrides:
            # Una cadena vacía es una decisión válida: "quitar" esa sección.
            setattr(cv, campo, overrides[campo] or None)

    for campo in _LIST_FIELDS:
        if campo in overrides:
            setattr(cv, campo, list(overrides[campo] or []))

    excluidas = {str(x) for x in (overrides.get("excluded_activity_ids") or [])}
    if excluidas:
        cv.activities = [
            a for a in cv.activities if str(getattr(a, "activity_id", "")) not in excluidas
        ]

    tests_fuera = {str(x).lower() for x in (overrides.get("excluded_test_ids") or [])}
    if tests_fuera:
        cv.test_highlights = [
            h for h in cv.test_highlights
            if str(h[3] if len(h) > 3 else "").lower() not in tests_fuera
        ]

    return cv
