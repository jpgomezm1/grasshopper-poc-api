"""A9 · Dónde quiere estudiar y qué área le interesa.

La clienta lo escribió así:

    "No he visto si hay algún momento donde el sistema le pregunte te gustaría
     estudiar en tu país de origen o en algún país/ciudad en especial, o si te
     interesa —después de evaluar los tests— qué área de estudio quisieras
     continuar."

Tres decisiones de diseño que conviene dejar escritas, porque no son obvias:

1. **Esto NO va en el onboarding, va después de los tests.** Ella misma dijo
   "después de evaluar los tests", y su otra queja —textual— fue "me hizo como 13
   preguntas". El onboarding ya tiene 13 pasos; sumarle uno más habría respondido
   un reclamo empeorando el otro. Además `OnboardingPage.tsx` documenta que se
   evitó a propósito añadir otra pregunta de ubicación para no alimentar la
   redundancia que ella venía señalando.

2. **La ciudad DONDE VIVE y la ciudad DONDE QUIERE ESTUDIAR son dos datos
   distintos**, y su frase mezcla los dos. Se guardan separados:
   - `city` · dónde vive hoy. Es el que ya esperaban tres sitios del backend.
   - `preferred_cities` · las ciudades donde le gustaría estudiar.
   Meter la segunda en el campo de la primera habría llenado el dossier clínico
   y el CRM con un dato falso.

3. **Se persiste dentro de `user.onboarding_answers`, no en columnas nuevas.**
   No es pereza: `crm_service._build_demographics` (:725),
   `crm_service._invoke_ai_analysis` (:1091) y
   `dossier_service._build_demographics` (:100) llevan meses leyendo
   `answers["city"]` — un campo que ninguna pregunta escribía. Escribiendo ahí,
   esos tres empiezan a mostrar el dato real sin tocar una línea de su código, y
   sin una migración que aplicar en producción.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/me/study-preferences", tags=["study-preferences"])

# Las mismas 10 áreas que ofrece el frontend (ISCED-F 2013 de UNESCO, sin el
# grupo 00 "genéricos", que no significa nada para quien está eligiendo).
# El frontend tiene su copia en `src/lib/studyAreas.ts` — si cambia una, cambia
# la otra. Se valida aquí para no guardar basura: este dato viaja al CRM.
STUDY_AREAS = (
    "education",
    "arts_humanities",
    "social_sciences",
    "business_law",
    "natural_sciences",
    "ict",
    "engineering",
    "agriculture",
    "health",
    "services",
)

# "Todavía no lo tengo claro" es una respuesta legítima, y en orientación
# vocacional es además muy común. No es lo mismo que no haber respondido.
STUDY_AREA_UNDECIDED = "undecided"

MAX_CIUDADES = 3
MAX_LARGO_CIUDAD = 80


class StudyPreferencesRequest(BaseModel):
    """Todo es opcional · se puede responder una parte y volver después."""

    city: Optional[str] = Field(default=None, max_length=MAX_LARGO_CIUDAD)
    preferred_cities: Optional[List[str]] = None
    study_area: Optional[str] = None


class StudyPreferencesResponse(BaseModel):
    city: Optional[str] = None
    preferred_cities: List[str] = []
    study_area: Optional[str] = None
    # Para que el frontend sepa si ya respondió alguna vez, sin adivinarlo
    # comparando campos vacíos.
    answered: bool = False


def _limpiar_ciudades(valores: Optional[List[str]]) -> Optional[List[str]]:
    """Quita vacíos y duplicados conservando el orden, y corta a `MAX_CIUDADES`."""
    if valores is None:
        return None
    vistas: set = set()
    limpias: List[str] = []
    for v in valores:
        if not isinstance(v, str):
            continue
        texto = v.strip()[:MAX_LARGO_CIUDAD]
        if not texto:
            continue
        clave = texto.casefold()
        if clave in vistas:
            continue
        vistas.add(clave)
        limpias.append(texto)
    return limpias[:MAX_CIUDADES]


def _leer(answers: Dict[str, Any]) -> StudyPreferencesResponse:
    ciudad = answers.get("city")
    destinos = answers.get("preferred_cities")
    area = answers.get("study_area")

    ciudad_txt = str(ciudad).strip() if isinstance(ciudad, str) and ciudad.strip() else None
    destinos_lista = _limpiar_ciudades(destinos) if isinstance(destinos, list) else []
    area_txt = str(area) if isinstance(area, str) and area.strip() else None

    return StudyPreferencesResponse(
        city=ciudad_txt,
        preferred_cities=destinos_lista or [],
        study_area=area_txt,
        answered=bool(ciudad_txt or destinos_lista or area_txt),
    )


@router.get("", response_model=StudyPreferencesResponse)
def get_study_preferences(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Lo que ya respondió · vacío si nunca respondió."""
    return _leer(dict(current_user.onboarding_answers or {}))


@router.put("", response_model=StudyPreferencesResponse)
def update_study_preferences(
    request: StudyPreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Guarda las preferencias. Todo opcional; sólo se toca lo que venga."""
    if request.study_area is not None:
        area = request.study_area.strip()
        if area and area != STUDY_AREA_UNDECIDED and area not in STUDY_AREAS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "unknown_study_area",
                    "message": "Esa área de estudio no está en la lista.",
                },
            )

    # Dict NUEVO, no mutación in-place: `onboarding_answers` es Column(JSON) sin
    # MutableDict, así que SQLAlchemy no detecta cambios sobre el mismo objeto y
    # el guardado se perdería en silencio. Es el mismo motivo por el que
    # `auth.update_onboarding` construye el dict así (ver su comentario).
    answers = {**(current_user.onboarding_answers or {})}

    if request.city is not None:
        ciudad = request.city.strip()[:MAX_LARGO_CIUDAD]
        if ciudad:
            answers["city"] = ciudad
        else:
            answers.pop("city", None)  # borrar es una acción válida

    if request.preferred_cities is not None:
        destinos = _limpiar_ciudades(request.preferred_cities) or []
        if destinos:
            answers["preferred_cities"] = destinos
        else:
            answers.pop("preferred_cities", None)

    if request.study_area is not None:
        area = request.study_area.strip()
        if area:
            answers["study_area"] = area
        else:
            answers.pop("study_area", None)

    current_user.onboarding_answers = answers
    db.commit()
    db.refresh(current_user)

    # El perfil consolidado se arma con estos datos en el contexto; si queda la
    # versión cacheada, el estudiante responde y no ve ningún cambio — que es
    # justo el reclamo de fondo ("escribo cosas y nada de eso queda").
    try:
        from app.services import consolidation_service

        invalidar = getattr(consolidation_service, "invalidate_cache", None)
        if callable(invalidar):
            invalidar(db, current_user.id)
    except Exception:  # noqa: BLE001 · nunca romper el guardado por el caché
        pass

    return _leer(answers)
