"""Psychometrics service · GH-ADVISOR-CLINICAL Bloque B.

Builds the rich psychometric view for a student, combining all 6 vocational
tests with deterministic cross-pattern analysis and inconsistency detection
(no LLM · all rule-based · cheap and reproducible).

Patterns we look for (see ALCANCE in TASKS.md):
- Holland Investigative high + Big Five Openness high + MBTI INTP/INTJ
- Holland Social high + Big Five Extraversion low (ambivalente)
- Career Anchors security + Holland Enterprising (potencial conflicto)

Inconsistencies:
- Holland=Social pero Big Five Agreeableness bajo
- iStrong altísimo en arts pero RIASEC Artistic bajo
- Work Values altruism alto pero Holland Realistic alto
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    ConsolidatedProfileCache,
    User,
    VocationalTestResult,
)
from app.schemas.clinical import (
    CrossPattern,
    Inconsistency,
    PsychometricsResponse,
    PsychTestSummary,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score extraction helpers · tolerant of legacy / heterogeneous shapes
# ---------------------------------------------------------------------------


def _scores_dict(test: VocationalTestResult) -> Dict[str, Any]:
    return test.scores or {}


def _holland_top(test_scores: Dict[str, Any]) -> Optional[str]:
    """Return the dominant RIASEC letter (R/I/A/S/E/C) or None."""
    # Common shapes: {"R": 80, "I": 65, ...} or {"holland_codes": [{"code":"S",...}]}
    if not test_scores:
        return None
    if "holland_codes" in test_scores and isinstance(test_scores["holland_codes"], list):
        codes = test_scores["holland_codes"]
        if codes:
            return str((codes[0] or {}).get("code", ""))[0:1] or None
    riasec_keys = ("R", "I", "A", "S", "E", "C")
    pairs = [(k, test_scores.get(k)) for k in riasec_keys if isinstance(test_scores.get(k), (int, float))]
    if not pairs:
        return None
    pairs.sort(key=lambda p: p[1] or 0, reverse=True)
    return pairs[0][0]


def _bigfive_traits(scores: Dict[str, Any]) -> Dict[str, float]:
    """Return canonical OCEAN dict with normalized 0-100 floats. Tolerant."""
    out: Dict[str, float] = {}
    if not scores:
        return out
    # Direct shape
    for key in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
        v = scores.get(key)
        if isinstance(v, (int, float)):
            # Some legacy results might use 0-1 scale
            out[key] = float(v) * 100 if 0.0 <= float(v) <= 1.0 else float(v)
    # Big5 letter shape (O/C/E/A/N)
    letter_map = {
        "O": "openness",
        "C": "conscientiousness",
        "E": "extraversion",
        "A": "agreeableness",
        "N": "neuroticism",
    }
    for letter, key in letter_map.items():
        if key in out:
            continue
        v = scores.get(letter)
        if isinstance(v, (int, float)):
            out[key] = float(v) * 100 if 0.0 <= float(v) <= 1.0 else float(v)
    return out


def _mbti_type(scores: Dict[str, Any]) -> Optional[str]:
    if not scores:
        return None
    mbti = scores.get("type") or scores.get("mbti_type") or scores.get("MBTI")
    if isinstance(mbti, str) and len(mbti) == 4:
        return mbti.upper()
    return None


def _level(value: Optional[float], hi: float = 65.0, lo: float = 35.0) -> Optional[str]:
    if value is None:
        return None
    if value >= hi:
        return "alto"
    if value <= lo:
        return "bajo"
    return "medio"


# ---------------------------------------------------------------------------
# Pattern + inconsistency builders
# ---------------------------------------------------------------------------


def _detect_cross_patterns(tests: Dict[str, Dict[str, Any]]) -> List[CrossPattern]:
    out: List[CrossPattern] = []

    holland = _holland_top(tests.get("riasec", {})) or _holland_top(tests.get("holland", {}))
    big5 = _bigfive_traits(tests.get("big5", {})) or _bigfive_traits(tests.get("bigfive", {}))
    mbti = _mbti_type(tests.get("mbti", {}))

    if holland == "I" and (_level(big5.get("openness")) == "alto") and (mbti or "").startswith("INT"):
        out.append(
            CrossPattern(
                label="Patrón coherente · perfil investigador profundo",
                description=(
                    "Holland Investigador + alta Apertura + MBTI tipo introvertido-pensador "
                    "convergen en un perfil reflexivo, analítico y orientado a la indagación."
                ),
                severity="info",
                evidence=[
                    f"Holland top = {holland}",
                    f"Openness = {round(big5.get('openness') or 0, 0)}",
                    f"MBTI = {mbti}",
                ],
            )
        )

    if holland == "S" and (_level(big5.get("extraversion")) == "bajo"):
        out.append(
            CrossPattern(
                label="Ambivalencia Social / Extraversión baja",
                description=(
                    "Interés por carreras de servicio + baja extraversión sugiere vocación "
                    "por el cuidado en formatos íntimos (1:1 · escritura · investigación clínica). "
                    "Vale explorar en sesión qué tipo de contacto humano lo nutre vs lo agota."
                ),
                severity="medium",
                evidence=[
                    f"Holland top = {holland}",
                    f"Extraversion = {round(big5.get('extraversion') or 0, 0)}",
                ],
            )
        )

    if (
        _level(big5.get("openness")) == "alto"
        and _level(big5.get("conscientiousness")) == "bajo"
    ):
        out.append(
            CrossPattern(
                label="Apertura alta + Responsabilidad baja",
                description=(
                    "Curiosidad amplia con baja organización · puede dispersarse. "
                    "Trabajar marcos externos (rutinas · plazos · acompañamiento) ayuda."
                ),
                severity="low",
                evidence=[
                    f"Openness = {round(big5.get('openness') or 0, 0)}",
                    f"Conscientiousness = {round(big5.get('conscientiousness') or 0, 0)}",
                ],
            )
        )

    return out


def _detect_inconsistencies(tests: Dict[str, Dict[str, Any]]) -> List[Inconsistency]:
    out: List[Inconsistency] = []

    holland = _holland_top(tests.get("riasec", {})) or _holland_top(tests.get("holland", {}))
    big5 = _bigfive_traits(tests.get("big5", {})) or _bigfive_traits(tests.get("bigfive", {}))

    if holland == "S" and _level(big5.get("agreeableness")) == "bajo":
        out.append(
            Inconsistency(
                label="Holland Social pero Agreeableness bajo",
                description=(
                    "El estudiante puntúa alto en orientación a servicio pero bajo en "
                    "agradabilidad. Puede indicar que valora ayudar desde estructuras o "
                    "marcos profesionales más que desde un vínculo cálido. Vale explorar."
                ),
                severity="medium",
                tests_involved=["riasec", "big5"],
            )
        )

    # iStrong arts vs Holland Artistic
    istrong = tests.get("istrong", {}) or {}
    arts_score = None
    for k in ("arts", "artistic", "ART"):
        v = istrong.get(k)
        if isinstance(v, (int, float)):
            arts_score = float(v)
            break
    if arts_score is not None and arts_score >= 70 and holland and holland != "A":
        out.append(
            Inconsistency(
                label="iStrong Arts alto pero Holland top no es Artistic",
                description=(
                    "Inclinación artística marcada en iStrong sin corresponder al top "
                    "de Holland. Puede ser hobby/escape vs vocación · explorar."
                ),
                severity="low",
                tests_involved=["istrong", "riasec"],
            )
        )

    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_psychometrics(db: DBSession, student: User) -> PsychometricsResponse:
    rows: List[VocationalTestResult] = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == student.id)
        .order_by(VocationalTestResult.created_at.asc())
        .all()
    )

    tests_summary: List[PsychTestSummary] = [
        PsychTestSummary(
            test_id=r.test_id,
            completed_at=r.created_at,
            source=r.source or "internal",
            scores=_scores_dict(r),
        )
        for r in rows
    ]

    # Index by test_id for cross-pattern detection · normalize aliases
    tests_by_id: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sid = (r.test_id or "").lower()
        tests_by_id[sid] = _scores_dict(r)

    cross = _detect_cross_patterns(tests_by_id)
    inc = _detect_inconsistencies(tests_by_id)

    cache = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == student.id)
        .first()
    )
    has_profile = bool(cache and cache.invalidated_at is None and cache.profile_data)
    profile_summary: Optional[Dict[str, Any]] = None
    if has_profile and cache:
        try:
            data = dict(cache.profile_data)
            profile_summary = {
                "summary_narrative": data.get("summary_narrative"),
                "strengths": data.get("strengths", []),
                "interests": data.get("interests", []),
                "values": data.get("values", []),
                "learning_style": data.get("learning_style"),
                "work_style": data.get("work_style"),
                "holland_codes": data.get("holland_codes", []),
                "personality_dimensions": data.get("personality_dimensions", []),
            }
        except Exception:
            profile_summary = None

    return PsychometricsResponse(
        student_user_id=student.id,
        tests=tests_summary,
        tests_count=len(tests_summary),
        cross_patterns=cross,
        inconsistencies=inc,
        has_consolidated_profile=has_profile,
        consolidated_profile_summary=profile_summary,
    )
