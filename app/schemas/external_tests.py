"""Pydantic schemas for external test uploads (Sprint 5 · GH-S5-BE-04).

Each test type has a dedicated `Parsed*` schema · the IA parser must return
JSON that conforms to this shape. Validation is strict (extra=forbid) so
hallucinated fields are rejected and forwarded to `needs_review`.

PII note: `student_name` and `test_date` are extracted from the PDF for
display, but the parser MUST NOT echo them in logs.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
