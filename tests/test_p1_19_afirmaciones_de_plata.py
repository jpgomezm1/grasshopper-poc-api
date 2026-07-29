"""P1-19 · No afirmar lo que no sabemos sobre plata y becas · Sprint 3 (2026-07-28).

El catálogo real son ~2.511 filas cuyo importador (build_programs_from_catalog.py)
deja `cost_total` y `scholarships_for_latam` en NULL de forma incondicional. El
sistema convertía esos NULL en afirmaciones POSITIVAS:

  - costo desconocido  -> matrícula "$0" y "Recuperarías la inversión en menos de
                          1 año" (roi_service)
  - costo desconocido  -> budget_fit "match" = "Dentro del presupuesto"
  - beca sin curar     -> "beca_latam=no" al modelo, para el 100% del catálogo

Estos tests fijan que un dato ausente se comunique como ausente.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.roi_service import calculate_roi


def _programa(**kw):
    base = dict(
        id=uuid.uuid4(), country="Canadá", currency="USD",
        cost_total=None, living_cost_city_usd_year=15000, duration_months=24,
        entry_salary_local_usd=45000, visa_max_years_work=3,
        visa_type="PGWP", visa_requires_degree_alignment=False, visa_notes=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# ROI · el hallazgo más grave: cifras en dólares inventadas
# ---------------------------------------------------------------------------


def test_sin_matricula_no_se_inventa_un_cero():
    """`int(cost_total or 0)` presentaba una matrícula DESCONOCIDA como $0."""
    r = calculate_roi(_programa(cost_total=None))
    assert r.cost_breakdown.tuition_total_usd is None
    assert r.cost_breakdown.total_investment_usd is None


def test_sin_matricula_no_hay_payback_ni_rating_positivo():
    """Lo peligroso no era el $0 en sí, sino el retorno que se derivaba de él."""
    r = calculate_roi(_programa(cost_total=None))
    assert r.payback_years is None
    assert r.net_value_usd is None
    assert r.rating == "insufficient_data"
    assert "no tenemos el costo confirmado" in r.summary.lower()


def test_el_resumen_distingue_falta_de_precio_de_falta_de_salario():
    sin_precio = calculate_roi(_programa(cost_total=None))
    sin_salario = calculate_roi(_programa(cost_total=40000, entry_salary_local_usd=None))
    assert "costo confirmado" in sin_precio.summary.lower()
    assert "salario" in sin_salario.summary.lower()
    assert sin_precio.summary != sin_salario.summary


def test_con_matricula_conocida_el_roi_sigue_calculando():
    """El fix no puede apagar la funcionalidad para los datos que sí tenemos."""
    r = calculate_roi(_programa(cost_total=40000))
    assert r.cost_breakdown.tuition_total_usd == 40000
    assert r.cost_breakdown.total_investment_usd == 70000  # 40k + 15k*2 años
    assert r.payback_years is not None
    assert r.rating != "insufficient_data"


def test_matricula_cero_real_no_se_confunde_con_desconocida():
    """Un programa GRATIS de verdad (cost_total=0) sí debe calcular."""
    r = calculate_roi(_programa(cost_total=0))
    assert r.cost_breakdown.tuition_total_usd == 0
    assert r.cost_breakdown.total_investment_usd == 30000  # solo costo de vida


# ---------------------------------------------------------------------------
# budget_fit · "Dentro del presupuesto" sin conocer el precio
# ---------------------------------------------------------------------------


def test_el_schema_admite_unknown():
    """Sin este valor en el Literal, era imposible ser honesto sin romper Pydantic."""
    from app.schemas.consolidated_profile import RecommendedProgram

    p = RecommendedProgram(
        program_id="x",
        program_name="Test",
        why_match=(
            "Encaja con tus intereses de diseño; el costo del programa todavía "
            "está por confirmar con la institución."
        ),
        match_score=80,
        budget_fit="unknown",
    )
    assert p.budget_fit == "unknown"


# ---------------------------------------------------------------------------
# Becas · tri-estado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor,esperado",
    [(True, "sí"), (False, "no"), (None, "sin_curar")],
)
def test_beca_sin_curar_no_se_reporta_como_no(valor, esperado):
    """Decirle "no" al modelo cuando el dato falta lo habilita a escribir
    "este programa no cuenta con beca" como si fuera un hecho verificado."""
    from app.services.recommendation_service import _beca_label

    assert _beca_label(valor) == esperado
