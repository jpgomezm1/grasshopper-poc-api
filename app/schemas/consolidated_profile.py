"""Pydantic schemas for the AI Analysis Engine (Sprint 6).

Two output shapes:

  1. ConsolidatedProfile · perfil consolidado del estudiante a partir de
     los 4-6 tests psicométricos disponibles + answers del journey + datos
     demográficos (etapa · presupuesto · país preferido).

  2. RecommendedProgram · una recomendación filtrada del catálogo
     Mentoring, con razón explícita del match y score 0-100.

Ambos llegan al frontend como respuesta de los endpoints
`POST /recommendations/generate` y `GET /recommendations/me`.

GH-S6-BE-01 + GH-S6-BE-02 · added 2026-04-30.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ConsolidatedProfile · perfil consolidado IA
# ---------------------------------------------------------------------------


class PersonalityDimension(BaseModel):
    """One dimension of the personality summary (e.g. 'extraversion: alta')."""

    name: str = Field(..., description="Dimensión legible (ej. 'Extraversión')")
    level: Literal["alto", "medio", "bajo"] = Field(
        ..., description="Nivel cualitativo, derivado de los tests."
    )
    insight: str = Field(
        ..., description="Insight corto · una frase explicando qué significa."
    )

    @field_validator("level", mode="before")
    @classmethod
    def _al_vocabulario_cerrado(cls, v):
        """Un matiz del modelo no puede costarle el perfil entero al estudiante.

        Visto en vivo el 2026-09-19: el modelo devolvió `"medio-alto"` para una
        dimensión y **toda** la generación del perfil falló por validación —
        `ConsolidationFailure`, "Análisis no disponible", sin recomendaciones.
        Y es no determinista: le pasa a unos estudiantes y a otros no, con los
        mismos datos.

        Perder catorce campos buenos por un guion en el decimoquinto es un mal
        negocio. Se traduce al vocabulario cerrado tomando el ÚLTIMO nivel
        reconocido del texto, que es la convención del compuesto en español:
        "medio-alto" tira hacia alto, "bajo-medio" hacia medio.

        Lo que NO se hace es inventar: si no se reconoce nada se queda en
        "medio" —el neutro— y se deja constancia en el log, porque un modelo que
        empieza a devolver vocabulario nuevo es algo que alguien debe mirar, no
        algo que se deba tapar en silencio.
        """
        if v in ("alto", "medio", "bajo"):
            return v
        texto = str(v or "").strip().lower()
        reconocidos = [
            p for p in re.split(r"[^a-záéíóúñ]+", texto)
            if p in ("alto", "alta", "medio", "media", "bajo", "baja")
        ]
        if reconocidos:
            return {"alta": "alto", "media": "medio", "baja": "bajo"}.get(
                reconocidos[-1], reconocidos[-1]
            )
        logger.warning(
            "nivel de personalidad fuera del vocabulario · se usa 'medio'",
            extra={"valor": texto[:40]},
        )
        return "medio"


class StrengthEvidence(BaseModel):
    """JR-7 · Una fortaleza y en qué se apoya.

    "Liderazgo" a secas no le dice nada a nadie. "Porque contaste que fuiste
    capitana del equipo de vóleibol" le demuestra al estudiante que lo que
    escribió se leyó — que es exactamente lo que la clienta reclamó que faltaba.
    """

    strength: str = Field(..., description="La fortaleza · igual que en `strengths`.")
    evidence: str = Field(
        ...,
        max_length=240,
        description="De dónde sale, en 2da persona. Empieza por 'Porque…'.",
    )


class HollandCode(BaseModel):
    """Top-3 RIASEC · el orden siempre existe, el puntaje no siempre.

    `score` es opcional a propósito. Varios reportes oficiales (el iStartStrong,
    sin ir más lejos) NO publican escalas numéricas: publican el orden de
    preferencia de los seis temas. Cuando el campo era obligatorio, el modelo
    cumplía el contrato inventando porcentajes plausibles a partir de ese orden
    —"Emprendedor 95"— y ese número terminaba en la tarjeta del estudiante y en
    el PDF de la familia con la misma apariencia que un puntaje medido.

    Los perfiles generados antes de este cambio traen score y siguen siendo válidos.
    """

    code: Literal["R", "I", "A", "S", "E", "C"]
    label: str = Field(..., description="Etiqueta humana (Realista, Investigador, ...)")
    score: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Score 0-100 · null si el test no publicó puntajes numéricos.",
    )


class CareerFamily(BaseModel):
    """Una familia profesional, aconsejada · no solo nombrada.

    `suggested_career_paths` existía desde el Sprint 6 y es una lista de nombres
    sueltos. `ReporteIntermedioPdfLayout` ya lo tenía anotado como deuda: "son
    3-5 caminos y sin porqué […] pedir una explicación por cada uno es cambiar
    ese prompt, y ese prompt alimenta también al recomendador, al dossier del
    asesor y a la hoja de vida: es una decisión de producto".

    La clienta la pidió explícitamente (2026-09-06): "no sé cómo hacer una
    descripción y una consejería de las familias que serían más adecuadas para
    esta persona". Cuatro nombres en una fila son un resultado; un consejero
    explica por qué cada uno calza, cómo se ve por dentro y qué mirar antes de
    decidir. Eso es lo que este modelo obliga a producir.

    `suggested_career_paths` se conserva y se mantiene en sync (son los `name`
    de estas familias) porque de él dependen el recomendador de programas, el
    dossier, el CV y el panel de acudientes.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., max_length=80, description="Nombre de la familia profesional.")
    fit_level: Literal["alto", "a explorar"] = Field(
        ...,
        description="Qué tan fuerte es el calce. Cualitativo a propósito · no hay "
        "un número medido detrás y fabricar un porcentaje lo haría parecer que sí.",
    )
    why_it_fits: str = Field(
        ...,
        max_length=400,
        description="Por qué le calza A ESTA persona · anclado en algo suyo, 2da persona.",
    )
    what_its_like: str = Field(
        ...,
        max_length=300,
        description="Cómo se ve el día a día de esa familia.",
    )
    careers: List[str] = Field(
        default_factory=list,
        max_length=6,
        description="Carreras o roles concretos que viven en esta familia.",
    )
    watch_out: Optional[str] = Field(
        None,
        max_length=300,
        description="La tensión honesta · qué mirar antes de decidirse. None si no hay.",
    )

    @field_validator("careers", mode="before")
    @classmethod
    def _coerce_careers(cls, v):
        if v is None:
            return []
        return v


class ConsolidatedProfile(BaseModel):
    """Perfil consolidado IA · output del prompt master de análisis cruzado.

    Construido cruzando los resultados de:

      - holland (RIASEC)            · interno
      - bigfive (OCEAN)             · interno
      - values (Work Values)        · interno (D-012)
      - mbti                        · interno (S4) o externo (S5)
      - istrong                     · interno (S4) o externo (S5)
      - big5                        · externo (S5) si lo subió el psicólogo

    Los campos que vienen de tests externos parseados por IA (S5) tienen
    `source = "external_upload"` en la tabla VocationalTestResult · el
    prompt los recibe igual que los internos.
    """

    # Narrative summary (~150 palabras de español)
    summary_narrative: str = Field(
        ...,
        min_length=200,
        max_length=2000,
        description="Resumen narrativo en español, ~150 palabras, dirigido al estudiante.",
    )

    # Top fortalezas detectadas (3-5 máximo)
    strengths: List[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="Top 3-5 fortalezas en lenguaje natural.",
    )

    # JR-7 · De dónde salió cada fortaleza.
    #
    # La clienta señaló que el estudiante escribe cosas a conciencia —su ejemplo
    # textual: "capitana del equipo de vóleibol"— y siente que "nada de eso
    # queda". Antes de esto tenía razón: la tarjeta de perfil mostraba fortalezas
    # sueltas y el encabezado sólo las atribuía a "N tests", nunca a lo que la
    # persona había escrito.
    #
    # Es OPCIONAL a propósito: los perfiles generados antes de este cambio no lo
    # traen, y deben seguir siendo válidos. El frontend muestra la evidencia sólo
    # cuando existe.
    strengths_evidence: List[StrengthEvidence] = Field(
        default_factory=list,
        max_length=5,
        description="Por cada fortaleza, en qué se apoya. Vacío en perfiles antiguos.",
    )

    # Áreas afines (campos profesionales / industrias / disciplinas)
    interests: List[str] = Field(
        ...,
        min_length=3,
        max_length=8,
        description="Áreas de interés afines (ej. 'Diseño UX', 'Ingeniería ambiental').",
    )

    # Valores que mueven al estudiante
    values: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Top valores derivados del Work Values + bigfive.",
    )

    # Estilo de aprendizaje + work style
    learning_style: Optional[str] = Field(
        default=None,
        description="Estilo de aprendizaje preferido (ej. 'Práctico-experiencial').",
    )
    work_style: Optional[str] = Field(
        default=None,
        description="Estilo de trabajo (ej. 'Colaborativo y estructurado').",
    )

    # Top 3 Holland codes con score
    holland_codes: List[HollandCode] = Field(
        default_factory=list,
        max_length=3,
        description="Top 3 RIASEC codes con score 0-100.",
    )

    # Personalidad descompuesta en dimensiones (typically 5 OCEAN + 4 MBTI)
    personality_dimensions: List[PersonalityDimension] = Field(
        default_factory=list,
        max_length=10,
    )

    # Constraints relevantes detectados (presupuesto · idioma · país)
    constraints: List[str] = Field(
        default_factory=list,
        description="Constraints prácticos detectados que afectan recomendación.",
    )

    # Lista corta de rutas profesionales sugeridas (no programs · esto va en
    # RecommendedProgram). Aquí la idea es áreas de carrera generales.
    suggested_career_paths: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="3-5 caminos profesionales sugeridos (ej. 'Producto digital · UX/UI').",
    )

    # La versión aconsejada de `suggested_career_paths` · ver CareerFamily.
    #
    # Opcional a propósito: los perfiles cacheados antes de este cambio no lo
    # traen y deben seguir siendo válidos. El frontend cae a las etiquetas
    # sueltas cuando la lista viene vacía.
    career_families: List[CareerFamily] = Field(
        default_factory=list,
        max_length=5,
        description="3-5 familias profesionales con su consejería. Vacío en perfiles antiguos.",
    )

    # Metadata
    tests_used: List[str] = Field(
        default_factory=list,
        description="Lista de test_ids efectivamente usados al generar el perfil.",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: Optional[str] = Field(
        default=None, description="Modelo IA · ej. claude-sonnet-4-5."
    )
    prompt_version: str = Field(default="consolidate_v1")

    @field_validator("strengths", "interests")
    @classmethod
    def _strip_and_dedupe(cls, v: List[str]) -> List[str]:
        seen = []
        for item in v:
            cleaned = (item or "").strip()
            if cleaned and cleaned.lower() not in {s.lower() for s in seen}:
                seen.append(cleaned)
        return seen


# ---------------------------------------------------------------------------
# RecommendedProgram · output del recomendador filtrado por catálogo
# ---------------------------------------------------------------------------


class BudgetFit(str):
    """Helper · sentinel for valid budget_fit values."""

    UNDER = "under"
    MATCH = "match"
    STRETCH = "stretch"


class RecommendedProgram(BaseModel):
    """Una recomendación específica del catálogo Mentoring.

    `program_id` MUST corresponder a un `oferta_id` del catálogo (validado en
    services/ai_service.py · si la IA inventa uno, se descarta antes de
    persistir).
    """

    program_id: str = Field(..., description="ID del catálogo Mentoring (oferta_id)")
    program_slug: Optional[str] = Field(default=None, description="Slug para link FE.")
    program_name: str = Field(..., description="Nombre legible del programa.")

    why_match: str = Field(
        ...,
        min_length=40,
        max_length=600,
        description="Razón concreta del match · 2-3 frases dirigidas al estudiante.",
    )

    match_score: int = Field(
        ..., ge=0, le=100, description="Score de afinidad 0-100."
    )

    budget_fit: Literal["under", "match", "stretch", "unknown"] = Field(
        ...,
        description=(
            "under: programa está debajo del presupuesto · "
            "match: dentro del rango · "
            "stretch: por encima pero alcanzable · "
            "unknown: no conocemos el costo del programa, no se afirma nada."
        ),
    )

    # Útiles para el FE sin re-fetch
    countries: List[str] = Field(default_factory=list)
    duration_label: Optional[str] = Field(default=None)
    budget_tier: Optional[str] = Field(default=None)

    # Dimensiones del perfil que más pesaron en este match
    matching_dimensions: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Dimensiones (ej. 'Realista', 'Apertura alta') que justifican el match.",
    )


class RecommendationsBundle(BaseModel):
    """Bundle final que devuelven los endpoints `/recommendations/*`."""

    user_id: UUID
    profile: Optional[ConsolidatedProfile] = Field(
        default=None,
        description=(
            "Perfil consolidado IA. Null cuando `status='empty'` (el estudiante "
            "aún no tiene tests psicométricos · semánticamente 200 OK)."
        ),
    )
    recommendations: List[RecommendedProgram] = Field(default_factory=list)
    cached: bool = Field(
        default=False,
        description="True si el bundle viene del cache (no re-llamó a IA).",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    profile_hash: Optional[str] = Field(
        default=None, description="Hash del input usado para generar (cache key)."
    )
    status: Literal["ready", "empty", "generating"] = Field(
        default="ready",
        description=(
            "`ready` → bundle generado o cacheado. `empty` → el estudiante no "
            "tiene aún tests psicométricos · profile y recommendations vacíos "
            "(B-010 QA round 2 · evita 503 espurio en `/recommendations/me`). "
            "`generating` → la generación corre en background (la llamada IA "
            "tarda ~45s y el router de Heroku corta a los 30s · el FE hace "
            "polling a GET /recommendations/me hasta ready/empty)."
        ),
    )


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class GenerateRecommendationsRequest(BaseModel):
    """Trigger explícito de regeneración (FE → BE)."""

    force_refresh: bool = Field(
        default=False,
        description="Si True ignora cache y regenera.",
    )
    limit: int = Field(default=5, ge=1, le=10)


class StudentPreferencesUpdate(BaseModel):
    """PATCH parcial del perfil · alimenta el filtro pre-IA."""

    budget_band: Optional[Literal["bajo", "medio", "alto"]] = None
    budget_max_usd: Optional[int] = Field(default=None, ge=0, le=200_000)
    preferred_countries: Optional[List[str]] = Field(default=None, max_length=10)
