"""Pydantic schemas for the AI Analysis Engine (Sprint 6).

Two output shapes:

  1. ConsolidatedProfile · perfil consolidado del estudiante a partir de
     los 4-6 tests psicométricos disponibles + answers del journey + datos
     demográficos (etapa · presupuesto · país preferido).

  2. RecommendedProgram · una recomendación filtrada del catálogo
     Grasshopper, con razón explícita del match y score 0-100.

Ambos llegan al frontend como respuesta de los endpoints
`POST /recommendations/generate` y `GET /recommendations/me`.

GH-S6-BE-01 + GH-S6-BE-02 · added 2026-04-30.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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


class HollandCode(BaseModel):
    """Top-3 RIASEC type with concrete percentage from the test."""

    code: Literal["R", "I", "A", "S", "E", "C"]
    label: str = Field(..., description="Etiqueta humana (Realista, Investigador, ...)")
    score: float = Field(
        ..., ge=0, le=100, description="Score 0-100 (porcentual)."
    )


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
    """Una recomendación específica del catálogo Grasshopper.

    `program_id` MUST corresponder a un `oferta_id` del catálogo (validado en
    services/ai_service.py · si la IA inventa uno, se descarta antes de
    persistir).
    """

    program_id: str = Field(..., description="ID del catálogo Grasshopper (oferta_id)")
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

    budget_fit: Literal["under", "match", "stretch"] = Field(
        ...,
        description=(
            "under: programa está debajo del presupuesto · "
            "match: dentro del rango · "
            "stretch: por encima pero alcanzable."
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
    profile: ConsolidatedProfile
    recommendations: List[RecommendedProgram] = Field(default_factory=list)
    cached: bool = Field(
        default=False,
        description="True si el bundle viene del cache (no re-llamó a IA).",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    profile_hash: Optional[str] = Field(
        default=None, description="Hash del input usado para generar (cache key)."
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
