"""Clinical analysis service · GH-ADVISOR-CLINICAL Bloque C+D.

Generates a deep clinical interpretation of a student's profile for the
gh_advisor (psychologist) to use in session. NOT shown to the student.

Inputs: demographics + consolidated profile (existing) + raw tests +
journey answers + journal entries.

Output: ClinicalAnalysis (narrative + strengths + growth_areas + risks +
session_suggestions + behavioral_patterns + referral flag).

Cache: 30 days TTL on `users.clinical_analysis_cache` JSONB. Regenerable.

Model: Claude Sonnet 4.5 (settings.ai_model). Temperature low (0.2) to
favor reproducibility over creativity. Max tokens 4500 to give space for
the long narrative + structured JSON.

Determinism overlay: we run a small rule-based scorer on the inputs that
boosts/dampens behavioral_pattern confidence based on signals the LLM may
miss (e.g. journal keywords, response volatility). The final list is the
union of rule-based detections (with their score) merged with LLM output.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.core.ai_client import get_client, load_prompt
from app.db.models import (
    ConsolidatedProfileCache,
    JournalEntry,
    Session,
    User,
    VocationalTestResult,
)
from app.schemas.clinical import (
    BehavioralPattern,
    ClinicalAnalysis,
)

logger = logging.getLogger(__name__)
settings = get_settings()

CACHE_TTL = timedelta(days=30)
PROMPT_VERSION = "clinical_analysis_v1"


# ---------------------------------------------------------------------------
# Input gathering
# ---------------------------------------------------------------------------


def _format_demographic(student: User) -> str:
    rows = []
    if student.name:
        rows.append(f"- Nombre: {student.name}")
    if student.email:
        rows.append(f"- Email: {student.email}")
    if getattr(student, "birthdate", None):
        rows.append(f"- Fecha nac.: {student.birthdate}")
    if student.english_cefr_level:
        rows.append(f"- Inglés (CEFR): {student.english_cefr_level}")
    if student.budget_band:
        rows.append(f"- Presupuesto: {student.budget_band}")
    if student.preferred_countries:
        rows.append(f"- Países preferidos: {', '.join(student.preferred_countries)}")
    return "\n".join(rows) if rows else "- (Sin demografía adicional)"


def _format_consolidated(cache: Optional[ConsolidatedProfileCache]) -> str:
    if not cache or cache.invalidated_at is not None or not cache.profile_data:
        return "(El estudiante aún no tiene perfil consolidado público generado.)"
    try:
        data = dict(cache.profile_data)
    except Exception:
        return "(Perfil consolidado existe pero no se pudo deserializar.)"
    lines = []
    if data.get("summary_narrative"):
        lines.append(f"Narrativa pública: {data['summary_narrative']}")
    if data.get("strengths"):
        lines.append(f"Fortalezas declaradas: {', '.join(data['strengths'])}")
    if data.get("interests"):
        lines.append(f"Intereses: {', '.join(data['interests'])}")
    if data.get("values"):
        lines.append(f"Valores: {', '.join(data['values'])}")
    if data.get("learning_style"):
        lines.append(f"Estilo de aprendizaje: {data['learning_style']}")
    if data.get("work_style"):
        lines.append(f"Estilo de trabajo: {data['work_style']}")
    if data.get("personality_dimensions"):
        dims = []
        for d in data.get("personality_dimensions") or []:
            try:
                dims.append(f"{d.get('name')} ({d.get('level')}) · {d.get('insight','')}")
            except Exception:
                continue
        if dims:
            lines.append("Dimensiones: " + " | ".join(dims))
    return "\n".join(lines) if lines else "(Perfil consolidado vacío.)"


def _format_tests(rows: List[VocationalTestResult]) -> str:
    if not rows:
        return "(Sin tests registrados.)"
    parts = []
    for r in rows:
        scores = json.dumps(r.scores or {}, ensure_ascii=False, sort_keys=True)
        parts.append(f"### {r.test_id} · source={r.source or 'internal'}\nscores: {scores}")
    return "\n\n".join(parts)


def _format_journey_answers(answers: Dict[str, Any]) -> str:
    if not answers:
        return "(Sin journey de onboarding.)"
    rows = []
    for k in sorted(answers.keys()):
        v = answers[k]
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v) or "—"
        elif isinstance(v, dict):
            try:
                v = json.dumps(v, ensure_ascii=False)
            except Exception:
                v = str(v)
        rows.append(f"- {k}: {v}")
    return "\n".join(rows)


def _format_journal(entries: List[JournalEntry], limit: int = 30) -> str:
    if not entries:
        return "(Sin entradas de journal.)"
    rows = []
    for e in entries[:limit]:
        rows.append(
            f"- [{e.entry_type.value if hasattr(e.entry_type, 'value') else e.entry_type}] "
            f"({e.created_at.date()}) {e.content[:300]}"
        )
    return "\n".join(rows)


def _gather_inputs(db: DBSession, student: User) -> Dict[str, Any]:
    cache = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == student.id)
        .first()
    )
    tests = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == student.id)
        .order_by(VocationalTestResult.test_id.asc())
        .all()
    )
    sess = (
        db.query(Session)
        .filter(Session.user_id == student.id)
        .order_by(Session.updated_at.desc())
        .first()
    )
    journey_answers = (sess.answers if sess else {}) or {}
    journal_rows: List[JournalEntry] = []
    if sess:
        journal_rows = (
            db.query(JournalEntry)
            .filter(JournalEntry.session_id == sess.id)
            .order_by(JournalEntry.created_at.desc())
            .all()
        )
    return {
        "demographic_block": _format_demographic(student),
        "consolidated_block": _format_consolidated(cache),
        "tests_block": _format_tests(tests),
        "journey_answers_block": _format_journey_answers(journey_answers),
        "journal_block": _format_journal(journal_rows),
        "_tests_count": len(tests),
        "_journal_count": len(journal_rows),
    }


# ---------------------------------------------------------------------------
# Rule-based pattern booster (deterministic overlay)
# ---------------------------------------------------------------------------

# Lowercased keywords scanned across journal + journey free-text answers
NEGATIVE_KEYWORDS = (
    "triste",
    "deprim",
    "ansied",
    "panic",
    "miedo",
    "no puedo",
    "no quiero",
    "presion",
    "obligad",
    "quier morir",
    "sin sentido",
    "vacio",
)

DECISION_VOLATILITY_KEYWORDS = (
    "no se",
    "no sé",
    "no estoy seguro",
    "estoy confundid",
    "cambi de opin",
    "ya no quiero",
)

FAMILY_PRESSURE_KEYWORDS = (
    "mis papas",
    "mis padres",
    "mi mama",
    "mi papa",
    "familia quiere",
    "familia espera",
    "familia dice",
    "obligan",
)


def _scan_keywords(corpus: str, kws: Tuple[str, ...]) -> int:
    if not corpus:
        return 0
    lower = corpus.lower()
    return sum(1 for k in kws if k in lower)


def _build_corpus(student: User, journey_answers: Dict[str, Any], journal_rows: List[JournalEntry]) -> str:
    parts = []
    for v in journey_answers.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(str(x) for x in v if isinstance(x, str))
    for e in journal_rows:
        parts.append(e.content or "")
    return " | ".join(parts)


def _rule_based_patterns(
    db: DBSession, student: User
) -> List[BehavioralPattern]:
    sess = (
        db.query(Session)
        .filter(Session.user_id == student.id)
        .order_by(Session.updated_at.desc())
        .first()
    )
    journey_answers = (sess.answers if sess else {}) or {}
    journal_rows: List[JournalEntry] = []
    if sess:
        journal_rows = (
            db.query(JournalEntry)
            .filter(JournalEntry.session_id == sess.id)
            .all()
        )
    corpus = _build_corpus(student, journey_answers, journal_rows)

    out: List[BehavioralPattern] = []

    # señales_clinicas
    neg_hits = _scan_keywords(corpus, NEGATIVE_KEYWORDS)
    if neg_hits >= 2:
        out.append(
            BehavioralPattern(
                pattern="señales_clinicas",
                confidence=min(0.9, 0.4 + 0.15 * neg_hits),
                evidence=f"Se detectan {neg_hits} marcadores emocionales negativos en journal/onboarding.",
                severity="high" if neg_hits >= 3 else "medium",
                suggested_intervention=(
                    "Considerar derivación clínica externa antes de continuar con orientación vocacional. "
                    "Verificar protocolo de derivación · documentar en notas privadas."
                ),
            )
        )

    # ansiedad_decision
    vol_hits = _scan_keywords(corpus, DECISION_VOLATILITY_KEYWORDS)
    if vol_hits >= 2:
        out.append(
            BehavioralPattern(
                pattern="ansiedad_decision",
                confidence=min(0.85, 0.45 + 0.1 * vol_hits),
                evidence=f"Lenguaje recurrente de incertidumbre / cambio de opinión ({vol_hits} marcadores).",
                severity="medium" if vol_hits < 4 else "high",
                suggested_intervention=(
                    "Trabajar herramientas de toma de decisiones bajo incertidumbre · "
                    "ejercicios de descomposición de la decisión."
                ),
            )
        )

    # complacencia_familiar
    fam_hits = _scan_keywords(corpus, FAMILY_PRESSURE_KEYWORDS)
    if fam_hits >= 2:
        out.append(
            BehavioralPattern(
                pattern="complacencia_familiar",
                confidence=min(0.85, 0.4 + 0.12 * fam_hits),
                evidence=f"Referencias frecuentes a expectativas/presiones familiares ({fam_hits}).",
                severity="medium",
                suggested_intervention=(
                    "Explorar separación entre aspiraciones propias vs heredadas. "
                    "Considerar sesión con familia si aplica."
                ),
            )
        )

    return out


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


# Fase C/A · helpers centralizados en app/core/ai_json (re-export con el
# mismo nombre privado para no romper call-sites ni tests existentes).
from app.core.ai_json import extract_first_json as _extract_first_json  # noqa: E402
from app.core.ai_json import strip_code_fences as _strip_code_fences  # noqa: E402


def _call_llm(prompt: str, user_id: str) -> Tuple[Optional[str], Dict[str, Any]]:
    client = get_client()
    metadata: Dict[str, Any] = {"model": settings.ai_model, "prompt_version": PROMPT_VERSION}
    start = time.time()
    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=4500,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else None
        metadata["latency_ms"] = int((time.time() - start) * 1000)
        if hasattr(response, "usage") and response.usage is not None:
            metadata["tokens_input"] = getattr(response.usage, "input_tokens", None)
            metadata["tokens_output"] = getattr(response.usage, "output_tokens", None)
        logger.info(
            "Clinical analysis LLM OK",
            extra={
                "user_id": user_id,
                "latency_ms": metadata.get("latency_ms"),
                "input_size": len(prompt),
                "output_size": len(text or ""),
            },
        )
        return text, metadata
    except Exception as e:
        logger.error(
            "Clinical analysis LLM failed",
            extra={"user_id": user_id, "error": str(e)},
        )
        metadata["error"] = str(e)
        return None, metadata


# ---------------------------------------------------------------------------
# Pattern merging · LLM + rule-based
# ---------------------------------------------------------------------------


def _merge_patterns(
    llm: List[BehavioralPattern], rules: List[BehavioralPattern]
) -> List[BehavioralPattern]:
    """Union by `pattern` key. Take whichever has higher confidence; merge
    evidence text. If only one source has it · include it."""
    by_key: Dict[str, BehavioralPattern] = {}
    for p in llm + rules:
        key = p.pattern
        if key not in by_key:
            by_key[key] = p
        else:
            existing = by_key[key]
            # Merge: pick higher confidence + concat evidence (prefer rule-based as anchor)
            higher = p if p.confidence > existing.confidence else existing
            other = existing if higher is p else p
            merged_evidence = higher.evidence
            if other.evidence and other.evidence not in merged_evidence:
                merged_evidence = f"{merged_evidence} || {other.evidence}"
            severity_rank = {"low": 1, "medium": 2, "high": 3}
            sev = (
                higher.severity
                if severity_rank.get(higher.severity, 0) >= severity_rank.get(other.severity, 0)
                else other.severity
            )
            by_key[key] = BehavioralPattern(
                pattern=higher.pattern,
                confidence=higher.confidence,
                evidence=merged_evidence,
                severity=sev,  # type: ignore[arg-type]
                suggested_intervention=higher.suggested_intervention,
            )
    return list(by_key.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ClinicalAnalysisFailure(RuntimeError):
    pass


def get_cached(student: User) -> Optional[ClinicalAnalysis]:
    """Return the cached ClinicalAnalysis if still within TTL, else None.

    GH-F1-SECURITY · Tarea 4: reads from `clinical_analysis_cache_enc`
    (EncryptedJSON column, AES-256-GCM) with fallback to the legacy plaintext
    `clinical_analysis_cache` column for rows created before the migration.
    New writes always go to `_enc`; the plaintext column is kept read-only
    as a migration bridge.
    """
    if not student.clinical_analysis_cached_at:
        return None
    age = datetime.utcnow() - student.clinical_analysis_cached_at
    if age > CACHE_TTL:
        return None

    # Prefer the encrypted column (post-migration rows)
    raw = (
        getattr(student, "clinical_analysis_cache_enc", None)
        or student.clinical_analysis_cache
    )
    if not raw:
        return None

    try:
        return ClinicalAnalysis(**raw)
    except Exception as e:
        logger.warning("Clinical cache corrupted · ignoring", extra={"error": str(e)})
        return None


def is_stale(student: User) -> bool:
    if not student.clinical_analysis_cached_at:
        return False
    return (datetime.utcnow() - student.clinical_analysis_cached_at) > CACHE_TTL


def insufficient_inputs_reason(db: DBSession, student: User) -> Optional[str]:
    tests_count = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == student.id)
        .count()
    )
    if tests_count < 2:
        return "El estudiante necesita al menos 2 tests psicométricos completados para análisis clínico."
    return None


def generate(
    db: DBSession,
    student: User,
    force: bool = False,
) -> ClinicalAnalysis:
    """Generate (or reuse cached) clinical analysis."""
    if not force:
        cached = get_cached(student)
        if cached:
            return cached

    reason = insufficient_inputs_reason(db, student)
    if reason:
        raise ClinicalAnalysisFailure(reason)

    inputs = _gather_inputs(db, student)
    template = load_prompt("clinical_analysis")
    prompt = template.format(
        demographic_block=inputs["demographic_block"],
        consolidated_block=inputs["consolidated_block"],
        tests_block=inputs["tests_block"],
        journey_answers_block=inputs["journey_answers_block"],
        journal_block=inputs["journal_block"],
    )

    raw, metadata = _call_llm(prompt, str(student.id))
    if raw is None:
        raise ClinicalAnalysisFailure("El motor de análisis IA no respondió · reintenta en breve.")

    cleaned = _strip_code_fences(raw)
    parsed_json = None
    try:
        parsed_json = json.loads(cleaned)
    except Exception:
        recovered = _extract_first_json(cleaned)
        if recovered:
            try:
                parsed_json = json.loads(recovered)
            except Exception:
                pass
    if parsed_json is None:
        logger.error(
            "Failed to parse clinical analysis JSON",
            extra={"user_id": str(student.id), "raw_preview": (raw or "")[:300]},
        )
        raise ClinicalAnalysisFailure("Análisis no disponible · respuesta del modelo inválida.")

    try:
        analysis = ClinicalAnalysis(**parsed_json)
    except Exception as e:
        logger.error(
            "ClinicalAnalysis schema validation failed",
            extra={"user_id": str(student.id), "error": str(e)},
        )
        raise ClinicalAnalysisFailure("Análisis no disponible · estructura inválida.") from e

    # Overlay deterministic patterns
    rule_patterns = _rule_based_patterns(db, student)
    analysis.behavioral_patterns = _merge_patterns(
        analysis.behavioral_patterns or [], rule_patterns
    )

    # Re-evaluate referral flag if rule-based patterns surface señales_clinicas
    if any(
        p.pattern == "señales_clinicas" and p.severity in ("medium", "high")
        for p in analysis.behavioral_patterns
    ):
        if not analysis.requires_clinical_referral:
            analysis.requires_clinical_referral = True
            if not analysis.referral_reason:
                analysis.referral_reason = (
                    "Se detectan marcadores emocionales que ameritan derivación clínica externa."
                )

    analysis.model_used = metadata.get("model")
    analysis.prompt_version = PROMPT_VERSION
    analysis.generated_at = datetime.utcnow()

    # Persist cache — write to encrypted column (GH-F1-SECURITY · Tarea 4)
    # clinical_analysis_cache_enc uses EncryptedJSON TypeDecorator (AES-256-GCM).
    # The legacy plaintext column is left untouched so existing rows remain
    # readable during the migration window. Both columns share clinical_analysis_cached_at.
    payload = analysis.model_dump(mode="json")
    student.clinical_analysis_cache_enc = payload
    # Keep legacy column cleared for new rows (NULL signals "use _enc")
    student.clinical_analysis_cache = None
    student.clinical_analysis_cached_at = datetime.utcnow()
    db.commit()

    return analysis
