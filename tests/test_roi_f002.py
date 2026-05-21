"""F-002 etapa 1 · unit tests for roi_service.

Pure-unit tests · no DB. Usamos SimpleNamespace para mockear `Program`.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest


def _program(
    cost_total=30000,
    duration_months=24,
    currency="USD",
    country="USA",
    living_cost=15000,
    salary=65000,
    visa_type="OPT",
    visa_years=3,
    requires_alignment=True,
    notes=None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        cost_total=cost_total,
        duration_months=duration_months,
        currency=currency,
        country=country,
        visa_type=visa_type,
        visa_max_years_work=visa_years,
        visa_requires_degree_alignment=requires_alignment,
        visa_notes=notes,
        entry_salary_local_usd=salary,
        living_cost_city_usd_year=living_cost,
    )


def test_roi_happy_path_positive():
    """Programa de $30k tuition + $15k/año vida × 2 años + $65k/año salario · positivo."""
    from app.services.roi_service import calculate_roi

    p = _program()
    r = calculate_roi(p)

    # tuition 30000 + living 30000 = 60000 total
    assert r.cost_breakdown.tuition_total_usd == 30000
    assert r.cost_breakdown.living_cost_year_usd == 15000
    assert r.cost_breakdown.living_cost_total_usd == 30000
    assert r.cost_breakdown.total_investment_usd == 60000
    # 60000 / 65000 = 0.92 (≤ 2 → positive)
    assert r.payback_years is not None and r.payback_years < 1.0
    assert r.rating == "positive"
    # max earnings 65000 × 3 = 195000
    assert r.post_grad.max_potential_earnings_usd == 195000
    # net value 195000 - 60000 = 135000
    assert r.net_value_usd == 135000


def test_roi_negative_with_high_cost_low_salary():
    """Tuition $200k, salario $40k → payback >5 años → negativo."""
    from app.services.roi_service import calculate_roi

    p = _program(cost_total=200000, salary=40000, living_cost=20000)
    r = calculate_roi(p)
    # 200000 + 20000*2 = 240000 total; 240000/40000 = 6.0
    assert r.cost_breakdown.total_investment_usd == 240000
    assert r.payback_years == 6.0
    assert r.rating == "negative"


def test_roi_neutral_in_mid_range():
    """Payback entre 2 y 5 años → neutral."""
    from app.services.roi_service import calculate_roi

    # Tuition 80k + living 30k = 110k total; salary 30k → payback 3.67
    p = _program(cost_total=80000, salary=30000, living_cost=15000)
    r = calculate_roi(p)
    assert 2.0 < (r.payback_years or 0) <= 5.0
    assert r.rating == "neutral"


def test_roi_insufficient_data_without_salary():
    from app.services.roi_service import calculate_roi

    p = _program(salary=None)
    r = calculate_roi(p)
    assert r.payback_years is None
    assert r.net_value_usd is None
    assert r.rating == "insufficient_data"
    assert "no se pudo estimar" in r.summary


def test_roi_insufficient_data_without_visa_years():
    """Sin visa_max_years_work no podemos calcular max_potential_earnings."""
    from app.services.roi_service import calculate_roi

    p = _program(visa_years=None)
    r = calculate_roi(p)
    # Sí podemos calcular payback (solo necesita salary), pero NO net_value.
    assert r.payback_years is not None  # 60000/65000 = 0.92
    assert r.post_grad.max_potential_earnings_usd is None
    assert r.net_value_usd is None


def test_roi_short_program_uses_minimum_one_year_living():
    """Programa de 3 meses con living cost: usamos mínimo 1 año (no fracción)."""
    from app.services.roi_service import calculate_roi

    p = _program(duration_months=3, living_cost=15000)
    r = calculate_roi(p)
    # 3/12 = 0.25, pero el service usa max(0.25, 1.0) = 1.0
    assert r.cost_breakdown.living_cost_total_usd == 15000


def test_roi_zero_cost_program():
    """Programa con cost_total=0 (e.g., gratis) → no payback necesario."""
    from app.services.roi_service import calculate_roi

    p = _program(cost_total=0, living_cost=0)
    r = calculate_roi(p)
    assert r.cost_breakdown.total_investment_usd == 0
    # payback es None porque total_investment es 0 (no hay nada que recuperar)
    assert r.payback_years is None


def test_roi_visa_info_propagated():
    from app.services.roi_service import calculate_roi

    p = _program(
        visa_type="PGWP",
        visa_years=3,
        requires_alignment=False,
        notes="Open work permit · cualquier empleador.",
    )
    r = calculate_roi(p)
    assert r.visa.type == "PGWP"
    assert r.visa.max_years_work == 3
    assert r.visa.requires_degree_alignment is False
    assert "Open work permit" in (r.visa.notes or "")


def test_roi_summary_mentions_country():
    from app.services.roi_service import calculate_roi

    p = _program(country="Canadá")
    r = calculate_roi(p)
    assert "Canadá" in r.summary
