"""Unit tests · scoring_service (GH-S4-QA-01).

Validates deterministic scoring for MBTI and iStrong with synthetic
answer payloads designed to land on known target outputs.
"""
from __future__ import annotations

import pytest

from app.data.vocational_tests import get_test_by_id
from app.services.scoring_service import (
    ISTRONG_GOT_BIS,
    MBTI_DIMENSIONS,
    calculate_istrong,
    calculate_mbti,
    derive_test_extras,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_mbti_answers(target: dict[str, int]) -> dict[str, int]:
    """Build an MBTI answer payload that targets specific raw scores per
    dimension. ``target`` maps dimension code -> desired Likert value
    applied to **forward-keyed** items (reversed items get ``6 - target``)
    so the calculator returns roughly the same value for both poles.
    """
    test = get_test_by_id("mbti")
    answers: dict[str, int] = {}
    for q in test["questions"]:
        cat = q["category"]
        base = target.get(cat, 3)
        # for reversed items, send the symmetric value (6-base) so they
        # contribute the same as forward items (calculator does 6-value)
        # this lets us get a uniform pole strength per dimension
        answers[q["id"]] = 6 - base if q.get("reversed") else base
    return answers


def _build_istrong_answers(per_bis: dict[str, int]) -> dict[str, int]:
    """Build iStrong answers with a Likert value per BIS code."""
    test = get_test_by_id("istrong")
    answers: dict[str, int] = {}
    for q in test["questions"]:
        answers[q["id"]] = per_bis.get(q["category"], 3)
    return answers


# ---------------------------------------------------------------------------
# MBTI tests
# ---------------------------------------------------------------------------


def test_mbti_all_high_yields_estj():
    """Likert 5 on all forward items -> E, S, T, J -> ESTJ."""
    answers = _build_mbti_answers({"EI": 5, "SN": 5, "TF": 5, "JP": 5})
    result = calculate_mbti(answers)
    assert result["type"] == "ESTJ"
    assert all(d["score"] == 100 for d in result["dimensions"].values())
    assert all(d["preference"] == 100 for d in result["dimensions"].values())


def test_mbti_all_low_yields_infp():
    """Likert 1 on all forward items -> I, N, F, P -> INFP."""
    answers = _build_mbti_answers({"EI": 1, "SN": 1, "TF": 1, "JP": 1})
    result = calculate_mbti(answers)
    assert result["type"] == "INFP"
    assert all(d["letter"] in ("I", "N", "F", "P") for d in result["dimensions"].values())


def test_mbti_mixed_enfj():
    """Target ENFJ: high E, low S(=N), low T(=F), high J."""
    answers = _build_mbti_answers({"EI": 5, "SN": 1, "TF": 1, "JP": 5})
    result = calculate_mbti(answers)
    assert result["type"] == "ENFJ"
    assert result["dimensions"]["EI"]["letter"] == "E"
    assert result["dimensions"]["SN"]["letter"] == "N"
    assert result["dimensions"]["TF"]["letter"] == "F"
    assert result["dimensions"]["JP"]["letter"] == "J"
    # type_info should populate for known types
    assert result["type_info"].get("name") == "Protagonista"


def test_mbti_neutral_resolves_deterministically():
    """All Likert 3 -> 60% on every dimension (3/5 = 60).

    The Likert scale is 1..5 where the neutral midpoint is 3 -> 60% on
    a 0..100 normalisation. Since 60 >= 50, the tie-break still leans
    toward the first-pole letters -> ESTJ.
    """
    answers = _build_mbti_answers({"EI": 3, "SN": 3, "TF": 3, "JP": 3})
    result = calculate_mbti(answers)
    assert result["type"] == "ESTJ"
    for d in result["dimensions"].values():
        assert d["score"] == 60
        # preference = abs(60-50)*2 = 20 (mild lean to first letter)
        assert d["preference"] == 20


def test_mbti_dimension_count_matches_bank():
    """Each MBTI dimension should have 15 questions (60/4)."""
    test = get_test_by_id("mbti")
    counts = {code: 0 for code, _, _ in MBTI_DIMENSIONS}
    for q in test["questions"]:
        counts[q["category"]] += 1
    assert all(c == 15 for c in counts.values()), counts


def test_mbti_dimension_balance_reversed_items():
    """At least 6 reversed items per dimension (so we can swing both ways)."""
    test = get_test_by_id("mbti")
    reversed_counts = {code: 0 for code, _, _ in MBTI_DIMENSIONS}
    for q in test["questions"]:
        if q.get("reversed"):
            reversed_counts[q["category"]] += 1
    assert all(c >= 6 for c in reversed_counts.values()), reversed_counts


# ---------------------------------------------------------------------------
# iStrong tests
# ---------------------------------------------------------------------------


def test_istrong_uniform_high_yields_balanced_profile():
    """All Likert 5 -> every GOT and BIS at 100."""
    answers = _build_istrong_answers({})  # default 3 ignored, override below
    answers = _build_istrong_answers({bis: 5 for bis_list in ISTRONG_GOT_BIS.values() for bis in bis_list})
    result = calculate_istrong(answers)
    for got, score in result["got"].items():
        assert score == 100, f"GOT {got} expected 100, got {score}"
    for bis, score in result["bis"].items():
        assert score == 100, f"BIS {bis} expected 100, got {score}"


def test_istrong_targeted_profile_iat():
    """Mark high I + A + S, low rest -> three-letter code IAS (or similar)."""
    high_bis = {
        "I:ciencias": 5, "I:tecnologia": 5,
        "A:visual": 5, "A:performativa": 5,
        "S:educacion": 5, "S:salud-mental": 5,
    }
    low_bis = {
        "R:mecanica": 1, "R:naturaleza": 1,
        "E:negocios": 1, "E:liderazgo": 1,
        "C:datos": 1, "C:logistica": 1,
    }
    answers = _build_istrong_answers({**high_bis, **low_bis})
    result = calculate_istrong(answers)
    assert result["primary_got"] in ("I", "A", "S")
    assert result["secondary_got"] in ("I", "A", "S")
    assert result["tertiary_got"] in ("I", "A", "S")
    assert set(result["three_letter_code"]) == {"I", "A", "S"}
    # top BIS should belong to I/A/S
    for bis in result["top_bis"]:
        assert bis.split(":")[0] in {"I", "A", "S"}


def test_istrong_got_aggregates_from_bis():
    """Set R:mecanica = 5, R:naturaleza = 1 -> GOT R averages the two BIS.

    Internal scale: each question normalised to (raw / 5) * 100. So
    Likert 5 -> 100, Likert 1 -> 20 (NOT zero · the calculator never
    produces 0 unless all answers are missing). Average -> 60.
    """
    bis_targets = {
        "R:mecanica": 5,
        "R:naturaleza": 1,
    }
    answers = _build_istrong_answers(bis_targets)
    result = calculate_istrong(answers)
    # mecanica likert 5 -> 100, naturaleza likert 1 -> 20, average = 60
    assert result["got"]["R"] == 60
    assert result["bis"]["R:mecanica"] == 100
    assert result["bis"]["R:naturaleza"] == 20


def test_istrong_bis_count_matches_bank():
    """Each BIS should have exactly 5 questions (60 total / 12 BIS)."""
    test = get_test_by_id("istrong")
    counts: dict[str, int] = {}
    for q in test["questions"]:
        counts.setdefault(q["category"], 0)
        counts[q["category"]] += 1
    expected_bis = [b for bis_list in ISTRONG_GOT_BIS.values() for b in bis_list]
    for bis in expected_bis:
        assert counts.get(bis, 0) == 5, f"BIS {bis} has {counts.get(bis, 0)} questions"
    assert sum(counts.values()) == 60


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_derive_extras_returns_none_for_legacy_tests():
    assert derive_test_extras("holland", {}) is None
    assert derive_test_extras("bigfive", {}) is None
    assert derive_test_extras("values", {}) is None
    assert derive_test_extras("career-anchors", {}) is None


def test_derive_extras_returns_payload_for_mbti_and_istrong():
    answers = _build_mbti_answers({"EI": 5, "SN": 5, "TF": 5, "JP": 5})
    extras = derive_test_extras("mbti", answers)
    assert extras is not None
    assert "type" in extras
    assert "dimensions" in extras

    extras_is = derive_test_extras("istrong", _build_istrong_answers({}))
    assert extras_is is not None
    assert "got" in extras_is
    assert "bis" in extras_is


def test_derive_extras_unknown_test_returns_none():
    assert derive_test_extras("nonexistent", {}) is None


# ---------------------------------------------------------------------------
# Bank integrity
# ---------------------------------------------------------------------------


def test_mbti_question_ids_are_unique():
    test = get_test_by_id("mbti")
    ids = [q["id"] for q in test["questions"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 60


def test_istrong_question_ids_are_unique():
    test = get_test_by_id("istrong")
    ids = [q["id"] for q in test["questions"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 60


def test_mbti_metadata_questioncount_matches_bank():
    test = get_test_by_id("mbti")
    assert test["questionCount"] == len(test["questions"])


def test_istrong_metadata_questioncount_matches_bank():
    test = get_test_by_id("istrong")
    assert test["questionCount"] == len(test["questions"])


def test_istrong_academic_basis_disclaims_sii():
    """D-011 enforcement: academicBasis must clarify it is NOT the original SII."""
    test = get_test_by_id("istrong")
    basis = test["academicBasis"].lower()
    assert "no es" in basis or "not " in basis
    assert "strong interest inventory" in basis


def test_mbti_academic_basis_disclaims_official_mbti():
    test = get_test_by_id("mbti")
    basis = test["academicBasis"].lower()
    assert "no es" in basis or "not " in basis
