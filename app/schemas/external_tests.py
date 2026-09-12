"""Pydantic schemas for external test uploads (Sprint 5 · GH-S5-BE-04).

Each test type has a dedicated `Parsed*` schema · the IA parser must return
JSON that conforms to this shape. Validation is strict (extra=forbid) so
hallucinated fields are rejected and forwarded to `needs_review`.

PII note: `student_name` and `test_date` are extracted from the PDF for
display, but the parser MUST NOT echo them in logs.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TestType = Literal["mbti", "istrong", "big5", "riasec"]
ParsingStatus = Literal["pending", "processing", "done", "needs_review", "failed"]


def _coerce_list_or_none(v):
    """Claude often returns null for empty lists · coerce to []."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [v]
    return v


RIASEC_LETTERS = ("R", "I", "A", "S", "E", "C")

# El reporte puede nombrar los temas en inglés o en español · el prompt pide letras,
# pero el modelo a veces devuelve el nombre completo y "Enterprising" leído letra a
# letra da "ERI", que es un código Holland distinto y verosímil. Mapeamos explícito.
_NOMBRE_A_LETRA = {
    "REALISTA": "R", "REALISTIC": "R",
    "INVESTIGADOR": "I", "INVESTIGATIVO": "I", "INVESTIGATIVE": "I",
    "ARTISTICO": "A", "ARTISTIC": "A",
    "SOCIAL": "S",
    "EMPRENDEDOR": "E", "ENTERPRISING": "E",
    "CONVENCIONAL": "C", "CONVENTIONAL": "C",
}

_SEPARADORES = re.compile(r"[\s,;/\-·|]+")


def _sin_tildes(t: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn"
    )


def _letra_riasec(token: str) -> Optional[str]:
    """Una letra RIASEC a partir de un token · letra suelta o nombre del tema."""
    t = _sin_tildes(str(token).strip().upper())
    if not t:
        return None
    if len(t) == 1:
        return t if t in RIASEC_LETTERS else None
    return _NOMBRE_A_LETRA.get(t)


def _clean_riasec_seq(v) -> Optional[List[str]]:
    """Normaliza una secuencia RIASEC a letras únicas y en orden.

    Acepta lo que en la práctica devuelve el modelo: lista de letras, lista de
    nombres ("Enterprising", "Emprendedor"), el string compacto "ECRISA" o los
    nombres separados por comas o guiones.
    """
    if v is None:
        return None
    if isinstance(v, str):
        tokens = [t for t in _SEPARADORES.split(v.strip()) if t]
        # "ECRISA" es un solo token que sí hay que abrir letra por letra · un
        # nombre como "Enterprising" no.
        if len(tokens) == 1 and _sin_tildes(tokens[0].upper()) not in _NOMBRE_A_LETRA:
            solo = tokens[0]
            if 0 < len(solo) <= 6 and all(c.upper() in RIASEC_LETTERS for c in solo):
                tokens = list(solo)
        v = tokens
    if not isinstance(v, list):
        return None

    out: List[str] = []
    for x in v:
        letra = _letra_riasec(x)
        if letra and letra not in out:
            out.append(letra)
    return out or None


def _completar_holland_code(code: str, ranking: Optional[List[str]]) -> str:
    """Devuelve un código Holland de 3 letras.

    El iStartStrong destaca solo los 2 temas top en su portada, y el modelo tiende
    a devolver "EC". La tercera letra existe: está en la lista de "los otros cuatro
    temas en tu orden de interés". Si tenemos el ranking, completamos desde ahí en
    vez de mandar a revisión manual un código que el reporte sí permite armar.
    """
    limpio = _clean_riasec_seq(code) or []
    if len(limpio) < 3 and ranking:
        for letra in ranking:
            if letra not in limpio:
                limpio.append(letra)
            if len(limpio) == 3:
                break
    return "".join(limpio[:3]) or (code or "").strip().upper()[:3]


# -----------------------------------------------------------------------------
# Per-test parsed payloads
# -----------------------------------------------------------------------------

class ParsedMBTI(BaseModel):
    """MBTI parsed result.

    Sample shapes accepted (from samples/external-tests/mbti/):
        - 16personalities tabular (with E/I, S/N, T/F, J/P percentages + identity A/T)
        - Truity narrative
        - Clinical 1-pager
    """

    model_config = ConfigDict(extra="forbid")

    type_code: str = Field(..., description="4-letter type · ENFJ, INTP, etc.")
    identity: Optional[Literal["A", "T"]] = Field(
        None, description="16personalities-only · Asertivo / Turbulento"
    )

    # Dimension scores · 0-100 (percentage of preference for first letter of pair)
    e_score: Optional[float] = Field(None, ge=0, le=100, description="% Extraversion (E vs I)")
    s_score: Optional[float] = Field(None, ge=0, le=100, description="% Sensing (S vs N)")
    t_score: Optional[float] = Field(None, ge=0, le=100, description="% Thinking (T vs F)")
    j_score: Optional[float] = Field(None, ge=0, le=100, description="% Judging (J vs P)")

    # Preference clarity index · escala 0-30 del MBTI Career Report oficial.
    # NO es un porcentaje y no se puede convertir a uno: mide qué tan CLARA fue la
    # preferencia, no cuánta. Vive aparte de los `*_score` justamente para que nadie
    # los mezcle. La dirección de cada pci la da la letra correspondiente de `type_code`.
    pci_ei: Optional[float] = Field(None, ge=0, le=30, description="pci del par E/I")
    pci_sn: Optional[float] = Field(None, ge=0, le=30, description="pci del par S/N")
    pci_tf: Optional[float] = Field(None, ge=0, le=30, description="pci del par T/F")
    pci_jp: Optional[float] = Field(None, ge=0, le=30, description="pci del par J/P")

    strengths: Optional[List[str]] = Field(default_factory=list, max_length=10)
    suggested_careers: Optional[List[str]] = Field(default_factory=list, max_length=15)

    @field_validator("strengths", "suggested_careers", mode="before")
    @classmethod
    def _coerce_lists(cls, v):
        return _coerce_list_or_none(v)


class ParsedIStrong(BaseModel):
    """iStrong / Strong Interest Inventory parsed result.

    Variants accepted: CPP tabular, narrative summary, simple table.
    """

    model_config = ConfigDict(extra="forbid")

    holland_code: str = Field(..., description="3 letters · e.g. 'IER'")

    # Orden de preferencia de los 6 temas · lo que publica el iStartStrong en vez
    # de puntajes numéricos. Es información real del reporte, no una estimación.
    theme_ranking: Optional[List[str]] = Field(
        None, max_length=6, description="Los 6 temas RIASEC de mayor a menor interés"
    )

    # GOTs · 0-100
    realistic: Optional[float] = Field(None, ge=0, le=100)
    investigative: Optional[float] = Field(None, ge=0, le=100)
    artistic: Optional[float] = Field(None, ge=0, le=100)
    social: Optional[float] = Field(None, ge=0, le=100)
    enterprising: Optional[float] = Field(None, ge=0, le=100)
    conventional: Optional[float] = Field(None, ge=0, le=100)

    # Top Basic Interest Scales (free text · max 5)
    top_basic_interests: Optional[List[str]] = Field(default_factory=list, max_length=10)
    suggested_careers: Optional[List[str]] = Field(default_factory=list, max_length=15)

    @field_validator("top_basic_interests", "suggested_careers", mode="before")
    @classmethod
    def _coerce_lists(cls, v):
        return _coerce_list_or_none(v)

    @field_validator("theme_ranking", mode="before")
    @classmethod
    def _limpiar_ranking(cls, v):
        return _clean_riasec_seq(v)

    @model_validator(mode="after")
    def _normalizar_codigo(self):
        self.holland_code = _completar_holland_code(self.holland_code, self.theme_ranking)
        return self


class ParsedBig5(BaseModel):
    """Big Five OCEAN parsed result.

    Variants accepted: IPIP-NEO, online Spanish summaries, clinical short-form.
    """

    model_config = ConfigDict(extra="forbid")

    openness: Optional[float] = Field(None, ge=0, le=100, description="% Openness (O)")
    conscientiousness: Optional[float] = Field(None, ge=0, le=100, description="% Conscientiousness (C)")
    extraversion: Optional[float] = Field(None, ge=0, le=100, description="% Extraversion (E)")
    agreeableness: Optional[float] = Field(None, ge=0, le=100, description="% Agreeableness (A)")
    neuroticism: Optional[float] = Field(None, ge=0, le=100, description="% Neuroticism (N)")

    interpretation_summary: Optional[str] = Field(None, max_length=2000)


class ParsedRIASEC(BaseModel):
    """Holland RIASEC parsed result.

    Variants accepted: O*NET, Truity extended, simple table.
    """

    model_config = ConfigDict(extra="forbid")

    holland_code: str = Field(..., description="3 letters · e.g. 'SAE'")

    theme_ranking: Optional[List[str]] = Field(
        None, max_length=6, description="Los 6 temas RIASEC de mayor a menor interés"
    )

    realistic: Optional[float] = Field(None, ge=0, le=100)
    investigative: Optional[float] = Field(None, ge=0, le=100)
    artistic: Optional[float] = Field(None, ge=0, le=100)
    social: Optional[float] = Field(None, ge=0, le=100)
    enterprising: Optional[float] = Field(None, ge=0, le=100)
    conventional: Optional[float] = Field(None, ge=0, le=100)

    suggested_careers: Optional[List[str]] = Field(default_factory=list, max_length=15)

    @field_validator("suggested_careers", mode="before")
    @classmethod
    def _coerce_lists(cls, v):
        return _coerce_list_or_none(v)

    @field_validator("theme_ranking", mode="before")
    @classmethod
    def _limpiar_ranking(cls, v):
        return _clean_riasec_seq(v)

    @model_validator(mode="after")
    def _normalizar_codigo(self):
        self.holland_code = _completar_holland_code(self.holland_code, self.theme_ranking)
        return self


ParsedPayload = Union[ParsedMBTI, ParsedIStrong, ParsedBig5, ParsedRIASEC]


# -----------------------------------------------------------------------------
# Wrapper that the parser service returns and that the API exposes
# -----------------------------------------------------------------------------

class ParserResult(BaseModel):
    """Full parser output · what gets persisted in `parsed_data`."""

    model_config = ConfigDict(extra="forbid")

    test_type: TestType
    student_name: Optional[str] = Field(None, max_length=200)
    test_date: Optional[str] = Field(None, max_length=50, description="Free text · raw from PDF")
    payload: ParsedPayload
    confidence: float = Field(..., ge=0.0, le=1.0)
    parser_version: str = Field("v1")
    notes: Optional[str] = Field(None, max_length=1000)


# -----------------------------------------------------------------------------
# API contracts
# -----------------------------------------------------------------------------

class UploadResponse(BaseModel):
    """Returned by POST /uploads/test-result."""

    id: UUID
    user_id: UUID
    test_type: TestType
    parsing_status: ParsingStatus
    file_path: str
    original_filename: Optional[str]
    size_bytes: Optional[int]
    uploaded_at: datetime


class UploadDetail(BaseModel):
    """Returned by GET /uploads/{id}."""

    id: UUID
    user_id: UUID
    test_type: TestType
    parsing_status: ParsingStatus
    file_path: str
    original_filename: Optional[str]
    parsed_data: Optional[dict]
    confidence_score: Optional[float]
    parser_version: Optional[str]
    error_message: Optional[str]
    uploaded_at: datetime
    parsed_at: Optional[datetime]


class ConfirmRequest(BaseModel):
    """User-corrected payload (optional) before promoting to VocationalTestResult."""

    model_config = ConfigDict(extra="forbid")

    payload: Optional[dict] = Field(
        None,
        description="If provided, replaces parsed_data before creating VocationalTestResult",
    )
