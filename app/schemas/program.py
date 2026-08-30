"""Pydantic schemas for Program (catalogue · GH-S8-BE-06)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, List, Any, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VALID_BUDGET_TIERS = {"low", "medium", "high", "premium"}
VALID_ALLIANCES = {"preferencial", "estandar", "convenio"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "CHF", "COP"}

# Bloque B · expanded program types (migration 015)
VALID_PROGRAM_TYPES = {
    # Educación secundaria · agregado 2026-08-08.
    #
    # Faltaba, y "High School" es la categoría MAS GRANDE del catalogo del
    # cliente (647 de 2.511 fichas). Lo destapo la primera pasada de extraccion
    # de programas: un colegio de Pre-Prep a Year 12 aporto 2 filas, y una ficha
    # cuyo `puede_vender` dice literalmente "High School" perdio su producto
    # principal. `intercambio` no servia de sustituto: un semestre fuera y un
    # bachillerato completo son productos distintos.
    "secundaria",
    "pregrado",
    "posgrado",
    "maestria",
    "doctorado",
    "diplomado",
    "especializacion",
    "curso_corto",
    "vacacional",
    "intercambio",
    "bootcamp",
    "mba",
    "bachelor",  # legacy
}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ---------------------------------------------------------------------------
# Editorial nested shapes (loose · accept extra keys for forward-compat)
# ---------------------------------------------------------------------------


class ProgramImage(BaseModel):
    url: str
    alt: Optional[str] = None
    caption: Optional[str] = None
    order: int = 0

    model_config = ConfigDict(extra="allow")


class ProgramTestimonial(BaseModel):
    quote: str
    name: Optional[str] = None
    year: Optional[int] = None
    link: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramSyllabusUnit(BaseModel):
    semester: Optional[str] = None
    courses: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ProgramAcademicReq(BaseModel):
    gpa: Optional[float] = None
    courses: Optional[List[str]] = None
    exam: Optional[str] = None
    interview: Optional[bool] = None

    model_config = ConfigDict(extra="allow")


class ProgramAdmissionDate(BaseModel):
    cohort: Optional[str] = None
    application_deadline: Optional[str] = None
    start_date: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramScholarship(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    coverage_pct: Optional[int] = None
    requirements: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramEmployability(BaseModel):
    placement_rate_pct: Optional[float] = None
    avg_salary: Optional[int] = None
    top_employers: Optional[List[str]] = None
    notes: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramRanking(BaseModel):
    global_rank: Optional[int] = None
    regional_rank: Optional[int] = None
    by_area: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(extra="allow")


class ProgramLocation(BaseModel):
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    neighborhood: Optional[str] = None
    monthly_cost_usd: Optional[int] = None

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Editorial mixin · stays loose because the FE may grow these shapes.
# ---------------------------------------------------------------------------


class ProgramEditorialFields(BaseModel):
    description_long: Optional[str] = None
    institution_logo_url: Optional[str] = Field(default=None, max_length=500)
    language_requirement_detail: Optional[str] = None
    images: Optional[List[Dict[str, Any]]] = None
    highlights: Optional[List[str]] = None
    syllabus: Optional[List[Dict[str, Any]]] = None
    academic_requirements: Optional[Dict[str, Any]] = None
    admission_dates: Optional[List[Dict[str, Any]]] = None
    scholarships: Optional[List[Dict[str, Any]]] = None
    employability: Optional[Dict[str, Any]] = None
    ranking: Optional[Dict[str, Any]] = None
    testimonials: Optional[List[Dict[str, Any]]] = None
    location: Optional[Dict[str, Any]] = None
    accreditations: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    # F-002 etapa 1 (2026-05-21) · Ruta migratoria laboral + ROI
    visa_type: Optional[str] = Field(default=None, max_length=40)
    visa_max_years_work: Optional[int] = Field(default=None, ge=0, le=20)
    visa_requires_degree_alignment: Optional[bool] = None
    visa_notes: Optional[str] = None
    entry_salary_local_usd: Optional[int] = Field(default=None, ge=0)
    living_cost_city_usd_year: Optional[int] = Field(default=None, ge=0)
    # F-003 etapa 1 (2026-05-28) · Financial Fit / Becas LatAm
    scholarships_for_latam: Optional[bool] = None
    # D-002 (2026-06-04) · variables de admisión · Reach/Match/Safety.
    # NULL = no curado (no se muestra badge). acceptance_rate en % (0-100).
    acceptance_rate: Optional[float] = Field(default=None, ge=0, le=100)
    avg_admitted_gpa: Optional[float] = Field(default=None, ge=0, le=100)
    # Sobre cuánto va ese promedio · sin esto el número no se puede comparar
    # con el de un estudiante (4.2/5.0 = 84 % está por DEBAJO de 3.8/4.0 =
    # 95 %, pero crudos 4.2 > 3.8). Ver `admission_fit_service`.
    avg_admitted_gpa_scale: Optional[float] = Field(default=None, gt=0, le=100)
    min_sat: Optional[int] = Field(default=None, ge=0, le=1600)
    avg_sat: Optional[int] = Field(default=None, ge=0, le=1600)
    min_english_level: Optional[str] = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _la_escala_del_gpa_es_coherente(self):
        """Si vienen promedio Y escala, que cuadren entre sí.

        Sólo se opina cuando están los dos: esta clase la heredan tanto la
        creación como el PATCH parcial, y un update que toca sólo el promedio
        sobre una fila que YA tiene escala es legítimo — pedirle reenviar un
        dato que no cambió es la clase de fricción que hace que la gente rellene
        el Excel a la brava.

        Que no se pueda guardar un promedio HUÉRFANO se exige en `ProgramBase`,
        donde sí hay una fila completa de la que hablar.

        Las escalas se leen de `academic_profile_service` para que no haya dos
        listas que se desincronicen. El import va dentro de la función a
        propósito: un schema no debería arrastrar la capa de servicios al
        importarse.
        """
        gpa = self.avg_admitted_gpa
        escala = self.avg_admitted_gpa_scale
        if gpa is None or escala is None:
            return self

        from app.services.academic_profile_service import ESCALAS_VALIDAS

        if float(escala) not in ESCALAS_VALIDAS:
            raise ValueError(
                "Escala no reconocida. Las que manejamos: "
                + ", ".join(str(e) for e in ESCALAS_VALIDAS)
            )
        if not (0 <= float(gpa) <= float(escala)):
            raise ValueError(f"El promedio tiene que estar entre 0 y {escala}.")
        return self

    @field_validator("min_english_level")
    @classmethod
    def _validate_cefr(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if v not in {"A1", "A2", "B1", "B2", "C1", "C2"}:
            raise ValueError("min_english_level must be a CEFR level (A1..C2)")
        return v


class ProgramBase(ProgramEditorialFields):
    program_id: str = Field(..., min_length=2, max_length=120)
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    country: str = Field(..., min_length=2, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    institution: str = Field(..., min_length=2, max_length=255)
    type: str = Field(..., min_length=2, max_length=60)
    area: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = Field(default=None, max_length=255)
    duration_months: int = Field(..., ge=1, le=120)
    cost_total: int = Field(..., ge=0)
    currency: str = Field(default="USD")
    budget_tier: str = Field(...)
    alliance_type: str = Field(default="estandar")
    language_requirement: Optional[str] = Field(default=None, max_length=50)
    active: bool = True

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in VALID_PROGRAM_TYPES:
            raise ValueError(
                f"type must be one of {sorted(VALID_PROGRAM_TYPES)}"
            )
        return v

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with optional hyphens")
        return v

    @field_validator("budget_tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in VALID_BUDGET_TIERS:
            raise ValueError(f"budget_tier must be one of {sorted(VALID_BUDGET_TIERS)}")
        return v

    @field_validator("alliance_type")
    @classmethod
    def _validate_alliance(cls, v: str) -> str:
        v = (v or "estandar").strip().lower()
        if v not in VALID_ALLIANCES:
            raise ValueError(f"alliance_type must be one of {sorted(VALID_ALLIANCES)}")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        v = (v or "USD").strip().upper()
        if v not in VALID_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(VALID_CURRENCIES)}")
        return v


class ProgramCreate(ProgramBase):
    raw: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _no_se_crea_un_promedio_huerfano(self):
        """Al crear, el promedio de admisión viene con su escala o no viene.

        Aquí no hay fila previa de la que heredar la escala, así que un
        `avg_admitted_gpa` solo nace ya inservible: un 3.8 sin saber sobre
        cuánto va no se puede comparar con el de ningún estudiante (4.2/5.0 es
        84 % y está por DEBAJO de 3.8/4.0, que es 95 %). Ver la migración 074 y
        `admission_fit_service`.
        """
        gpa = self.avg_admitted_gpa
        escala = self.avg_admitted_gpa_scale
        if (gpa is None) != (escala is None):
            raise ValueError(
                "avg_admitted_gpa y avg_admitted_gpa_scale van juntos: un "
                "promedio sin saber sobre cuánto va no se puede comparar."
            )
        return self


class ProgramUpdate(ProgramEditorialFields):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=255)
    country: Optional[str] = Field(default=None, min_length=2, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    institution: Optional[str] = Field(default=None, min_length=2, max_length=255)
    type: Optional[str] = Field(default=None, min_length=2, max_length=60)
    area: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = Field(default=None, max_length=255)
    duration_months: Optional[int] = Field(default=None, ge=1, le=120)
    cost_total: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = None
    budget_tier: Optional[str] = None
    alliance_type: Optional[str] = None
    language_requirement: Optional[str] = Field(default=None, max_length=50)
    active: Optional[bool] = None
    # A8 · prioridad comercial 1-10 ("¿tengo cómo ponerle estrellas para que
    # determine qué sale primero?"). El rango se valida aquí y no sólo en la
    # UI: un 50 metido por API desbalancearía el scoring del recomendador.
    priority: Optional[int] = Field(default=None, ge=1, le=10)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_PROGRAM_TYPES:
            raise ValueError(
                f"type must be one of {sorted(VALID_PROGRAM_TYPES)}"
            )
        return v

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with optional hyphens")
        return v

    @field_validator("budget_tier")
    @classmethod
    def _validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_BUDGET_TIERS:
            raise ValueError(f"budget_tier must be one of {sorted(VALID_BUDGET_TIERS)}")
        return v

    @field_validator("alliance_type")
    @classmethod
    def _validate_alliance(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_ALLIANCES:
            raise ValueError(f"alliance_type must be one of {sorted(VALID_ALLIANCES)}")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if v not in VALID_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(VALID_CURRENCIES)}")
        return v


class ProgramResponse(ProgramBase):
    """Serialización de salida de un Program ya persistido.

    B-042: el catálogo real (importado de los convenios, migración 048) tiene
    `duration_months` / `cost_total` / `budget_tier` en NULL = "a confirmar".
    `ProgramBase` los exige como input (crear un programa a mano sí los pide),
    pero la RESPUESTA debe serializar lo que hay en BD — con los campos
    requeridos, cada página de `GET /programs` lanzaba ValidationError → 500
    y el catálogo del admin quedó caído en prod para todos los roles.
    """

    id: UUID
    created_at: datetime
    updated_at: datetime

    duration_months: Optional[int] = None
    cost_total: Optional[int] = None
    budget_tier: Optional[str] = None
    # A8 · None = sin priorizar, que NO es prioridad baja. El panel debe
    # mostrarlo como "sin priorizar" y no como un 0.
    priority: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    # Override (mismo nombre = reemplaza al de ProgramBase): la respuesta no
    # re-valida reglas de negocio sobre datos ya persistidos; solo normaliza.
    @field_validator("budget_tier")
    @classmethod
    def _validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v.strip().lower()


class ProgramListResponse(BaseModel):
    items: List[ProgramResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProgramImportReport(BaseModel):
    total_rows: int
    valid_rows: int
    inserted: int
    updated: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    committed: bool
