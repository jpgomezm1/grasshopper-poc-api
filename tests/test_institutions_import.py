"""GH-LOCAL-CLIENT-CATALOG · unit tests for the institutions import script.

Tests are pure: validate normalization helpers + parse logic without DB.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest


# ---------------------------------------------------------------------------
# Country / category normalization
# ---------------------------------------------------------------------------


def test_norm_country_canonicalizes_spanish_variants():
    from scripts.import_institutions import _norm_country

    assert _norm_country("Canadá") == "Canada"
    assert _norm_country("USA") == "USA"
    assert _norm_country("Estados Unidos") == "USA"
    assert _norm_country("Reino Unido") == "UK"
    assert _norm_country("Nueva Zelanda") == "New Zealand"
    assert _norm_country("España") == "Spain"
    assert _norm_country("Alemania") == "Germany"
    assert _norm_country("Internacional") == "International"


def test_norm_country_returns_none_for_broken_or_empty():
    from scripts.import_institutions import _norm_country

    assert _norm_country(None) is None
    assert _norm_country("") is None
    assert _norm_country("   ") is None
    assert _norm_country("#REF!") is None
    assert _norm_country("#N/A") is None


def test_norm_country_passthrough_for_unknown():
    from scripts.import_institutions import _norm_country

    # Unknown countries pass through (case-preserving).
    assert _norm_country("Bulgaria") == "Bulgaria"
    assert _norm_country("Saudi Arabia") == "Saudi Arabia"


def test_norm_category_canonicalizes_known():
    from scripts.import_institutions import _norm_category

    assert _norm_category("Universidad") == "Universidad"
    assert _norm_category("universidad") == "Universidad"
    assert _norm_category("College Privado") == "College Privado"
    assert _norm_category("instituto idiomas") == "Instituto Idiomas"


def test_norm_category_handles_broken():
    from scripts.import_institutions import _norm_category

    assert _norm_category(None) is None
    assert _norm_category("#N/A") is None


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------


def test_str_strips_and_normalizes_empty():
    from scripts.import_institutions import _str

    assert _str("  hello  ") == "hello"
    assert _str(None) is None
    assert _str("") is None
    assert _str("   ") is None


def test_looks_broken_detects_excel_errors():
    from scripts.import_institutions import _looks_broken

    assert _looks_broken("#REF!") is True
    assert _looks_broken("#N/A") is True
    assert _looks_broken("#NAME?") is True
    assert _looks_broken("Universidad") is False
    assert _looks_broken(None) is False  # empty handled separately


def test_parse_date_handles_multiple_formats():
    from scripts.import_institutions import _parse_date

    assert _parse_date(datetime(2024, 5, 1)) == date(2024, 5, 1)
    assert _parse_date(date(2024, 5, 1)) == date(2024, 5, 1)
    assert _parse_date("2024-05-01") == date(2024, 5, 1)
    assert _parse_date("2024-05-01 00:00:00") == date(2024, 5, 1)
    assert _parse_date(None) is None
    assert _parse_date("not-a-date") is None


def test_parse_programs_filters_broken_and_empty():
    from scripts.import_institutions import _parse_programs

    assert _parse_programs("Idiomas", "Foundation", None, "#REF!", "") == ["Idiomas", "Foundation"]
    assert _parse_programs() == []


def test_parse_commissions_skips_fully_empty_slots():
    from scripts.import_institutions import _parse_commissions

    out = _parse_commissions("0.25", "ELICOS", "0.2", "Higher Ed", None, None, None, None)
    assert out == [
        {"value": "0.25", "description": "ELICOS"},
        {"value": "0.2", "description": "Higher Ed"},
    ]


def test_dedupe_key_lowercases_and_collapses_whitespace():
    from scripts.import_institutions import _normalize_dedupe_key

    assert _normalize_dedupe_key("  University  of   Tulsa  ") == "university of tulsa"
    assert _normalize_dedupe_key("Algonquin College") == "algonquin college"


# ---------------------------------------------------------------------------
# Dedupe + merge
# ---------------------------------------------------------------------------


def test_dedupe_first_source_wins():
    from scripts.import_institutions import dedupe_and_merge

    recs_a = [{"name": "MIT", "country": "USA"}, {"name": "Stanford", "country": "USA"}]
    recs_b = [{"name": "MIT", "country": "UK"}, {"name": "Cambridge", "country": "UK"}]

    merged, reports = dedupe_and_merge([("A", recs_a), ("B", recs_b)])

    by_name = {r["name"]: r for r in merged}
    assert by_name["MIT"]["country"] == "USA"  # first source wins
    assert by_name["Cambridge"]["country"] == "UK"
    assert reports["A"].new_records == 2
    assert reports["B"].new_records == 1
    assert reports["B"].skipped_dedupe == 1
