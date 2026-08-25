"""Recomendación de materias electivas · reunión clienta 2026-08-24 (min. 27:00).

Cita textual:

    "Si yo he puesto en decimo que quiero estudiar ingenieria, el sistema
    deberia poderme decir si en tu colegio tienes matematicas avanzadas,
    calculo, geometria avanzada, pues esas son las materias que deberias
    escoger como electivas."

## Qué SÍ hace este módulo

Cruza el área de estudio que el estudiante ya declaró (A9 ·
`app/api/v1/study_preferences.py`, guardada en
`user.onboarding_answers["study_area"]`) contra una tabla FIJA de materias
que suelen pedirse o ayudar para esa área — y, si el colegio ya cargó qué
materias ofrece (`School.subjects_offered`, cimiento agregado el 2026-08-25 en
la migración 068), marca cuáles de esas coinciden con lo que el colegio SÍ
tiene.

## Qué NO hace (deliberado)

- **No es IA.** La tabla de abajo es contenido curado a mano, no generado por
  un modelo. La clienta ya reclamó una vez por contenido inventado
  (ver `career_gap_service.py`): aquí no hay superficie para que un LLM
  invente una materia que no existe — el determinismo es la garantía
  estructural, no una instrucción de prompt que se pueda ignorar.
- **No promete admisión.** `DISCLAIMER` es un texto fijo que pone este
  módulo, igual que `career_gap_service.DISCLAIMER` — nunca depende de que
  alguien se acuerde de escribirlo.
- **No inventa qué ofrece el colegio.** Si `School.subjects_offered` es
  `None` (todavía no se cargó — el escritor de ese campo es otra fase, ver
  la migración 068), la recomendación sale marcada como general
  (`tiene_datos_colegio=False`) y lo dice explícitamente: nunca finge una
  personalización que no tiene.

## Qué NO decide este módulo

Quién llena `School.subjects_offered` y cómo (formulario de `school_admin`,
import, etc.) es una fase posterior, fuera de este alcance — este módulo sólo
LEE la columna si ya tiene datos.
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session as DBSession

from app.db.models import School, User
from app.services.vocational_bank_selector import grado_del_estudiante

# Reusa las etiquetas ya definidas para `study_area` en el pipeline del
# journey en vez de mantener una tercera copia de las 10 áreas ISCED-F +
# "undecided" (la primera vive en `study_preferences.STUDY_AREAS` como
# tupla de ids sin label; ésta ya trae el texto legible).
from app.services.ai_service import _STUDY_AREA_LABELS

DISCLAIMER = (
    "Estas son materias que SUELEN pedirse o ayudar para esta área de estudio "
    "en general — no es una lista oficial de tu colegio ni una promesa de "
    "admisión a ningún programa. Confírmalo con tu coordinación académica."
)

# La clienta: "es una recomendación útil sobre todo en grado 10 y 11, cuando
# todavía se pueden elegir". No bloquea otros grados —un estudiante de 9°
# planeando con anticipación también se beneficia— sólo marca cuándo es más
# accionable.
GRADOS_MAS_UTIL = (10, 11)

# Materias genéricas que suelen pedirse o ayudan para cada área de estudio
# (ISCED-F 2013, mismas 10 áreas de `study_preferences.STUDY_AREAS`). Curado
# a mano — nunca generado por IA — con nombres genéricos, sin ligar a ningún
# proveedor o examen con derechos de autor (nada de "AP Calculus" ni "IB Math
# AA"): son materias, no certificaciones.
RECOMENDACIONES_POR_AREA: Dict[str, List[str]] = {
    "engineering": ["Matemáticas avanzadas", "Cálculo", "Física", "Química"],
    "natural_sciences": ["Matemáticas avanzadas", "Física", "Química", "Biología avanzada"],
    "health": ["Biología avanzada", "Química", "Matemáticas avanzadas"],
    "ict": ["Matemáticas avanzadas", "Física", "Programación / Tecnología"],
    "business_law": ["Matemáticas avanzadas", "Economía", "Ciencias sociales"],
    "social_sciences": ["Ciencias sociales", "Filosofía", "Economía", "Segunda lengua"],
    "arts_humanities": ["Artes", "Literatura / Lengua avanzada", "Segunda lengua"],
    "education": ["Ciencias sociales", "Segunda lengua", "Artes"],
    "agriculture": ["Biología avanzada", "Química", "Ciencias ambientales"],
    "services": ["Economía", "Segunda lengua", "Matemáticas avanzadas"],
}


def _normaliza(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar 'Cálculo' contra 'calculo'."""
    tabla = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
    return texto.translate(tabla).strip().lower()


def _coincide(recomendada: str, ofrecidas_normalizadas: List[str]) -> bool:
    """Coincidencia por substring en cualquier dirección.

    'Cálculo' coincide con 'Cálculo diferencial' y viceversa — no exige match
    exacto porque cada colegio nombra sus materias distinto y no tenemos un
    catálogo canónico de nombres de materias.
    """
    r = _normaliza(recomendada)
    if not r:
        return False
    return any(r in o or o in r for o in ofrecidas_normalizadas if o)


def _mensaje_sin_area() -> str:
    return (
        "Todavía no nos has contado qué área de estudio te interesa "
        "continuar. Respóndelo en 'Dónde quiero estudiar' y vuelve a esta "
        "pantalla para ver materias recomendadas."
    )


def recommend_electives(db: DBSession, user: User) -> Dict[str, Any]:
    """Arma la recomendación de electivas para `user`.

    Devuelve un dict crudo — la conversión a `ElectivesResponse` (Pydantic) es
    responsabilidad del router, igual que el resto del repo (services no
    devuelven schemas).
    """
    onboarding = user.onboarding_answers or {}
    study_area = onboarding.get("study_area")
    grado = grado_del_estudiante(user)
    especialmente_util = bool(grado is not None and grado in GRADOS_MAS_UTIL)

    if not study_area or study_area not in RECOMENDACIONES_POR_AREA:
        # Incluye el caso "undecided" (dijo explícitamente que no sabe) y
        # cualquier área sin tabla de recomendación todavía — mismo criterio
        # que el resto del repo: "no sé" no es un dato, es la ausencia de uno.
        return {
            "study_area": study_area,
            "study_area_label": _STUDY_AREA_LABELS.get(study_area) if study_area else None,
            "grade": grado,
            "especialmente_util_ahora": especialmente_util,
            "tiene_datos_colegio": False,
            "recomendaciones": [],
            "mensaje": _mensaje_sin_area(),
            "disclaimer": DISCLAIMER,
        }

    materias = RECOMENDACIONES_POR_AREA[study_area]
    area_label = _STUDY_AREA_LABELS.get(study_area, study_area)

    school = None
    if user.school_id:
        school = db.query(School).filter(School.id == user.school_id).first()

    ofrecidas = school.subjects_offered if school else None
    # NULL (todavía no se cargó) es distinto de lista vacía (colegio la cargó
    # y no ofrece ninguna electiva de esta tabla) — sólo NULL cae a "general".
    tiene_datos_colegio = isinstance(ofrecidas, list)

    if tiene_datos_colegio:
        ofrecidas_norm = [_normaliza(str(m)) for m in ofrecidas if str(m).strip()]
        recomendaciones = [
            {"subject": m, "ofrecida_por_colegio": _coincide(m, ofrecidas_norm)}
            for m in materias
        ]
        mensaje = (
            f"Según lo que tu colegio reportó que ofrece, estas son las "
            f"materias que suelen pedirse para {area_label}."
        )
    else:
        recomendaciones = [
            {"subject": m, "ofrecida_por_colegio": None} for m in materias
        ]
        mensaje = (
            "Todavía no tenemos cargada la lista de materias que ofrece tu "
            "colegio, así que esta recomendación es general — confirma con tu "
            "coordinación académica cuáles de estas puedes elegir."
        )

    return {
        "study_area": study_area,
        "study_area_label": area_label,
        "grade": grado,
        "especialmente_util_ahora": especialmente_util,
        "tiene_datos_colegio": tiene_datos_colegio,
        "recomendaciones": recomendaciones,
        "mensaje": mensaje,
        "disclaimer": DISCLAIMER,
    }
