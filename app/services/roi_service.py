"""ROI calculator service · F-002 etapa 1 (2026-05-21).

Calcula la rentabilidad estimada de un programa combinando:
  - costo total (tuition)
  - duración del programa (para multiplicar living_cost)
  - costo de vida estimado en la ciudad (USD/año)
  - salario inicial estimado en el país de destino (USD/año)
  - ventana de trabajo permitida por la visa post-grad

Sin contemplar (etapa 2+):
  - inflación / tipo de cambio
  - impuestos del país destino
  - tasa de interés del crédito si aplica
  - escalamiento salarial año a año
"""
from __future__ import annotations

import math
from typing import Optional

from app.db.models import Program
from app.schemas.roi import (
    RoiCalculation,
    RoiCostBreakdown,
    RoiPostGrad,
    RoiRating,
    RoiVisaInfo,
)


def _rate_roi(payback_years: Optional[float]) -> RoiRating:
    """Rating heurístico simple por payback."""
    if payback_years is None:
        return "insufficient_data"
    if payback_years <= 2.0:
        return "positive"
    if payback_years <= 5.0:
        return "neutral"
    return "negative"


def _summary(
    program: Program,
    payback: Optional[float],
    net_value: Optional[int],
) -> str:
    if payback is None:
        return (
            "ROI no se pudo estimar · faltan datos de salario inicial o "
            "costo de vida para este programa."
        )
    if payback <= 1.0:
        return (
            f"Recuperarías la inversión en menos de 1 año trabajando como "
            f"recién egresado en {program.country}."
        )
    if payback <= 5.0:
        years_str = f"{payback:.1f}".rstrip("0").rstrip(".") or "0.1"
        return (
            f"Recuperarías la inversión en aproximadamente {years_str} años "
            f"de trabajo post-grado en {program.country}."
        )
    return (
        f"Recuperar la inversión tomaría más de {payback:.0f} años con el "
        f"salario inicial estimado · evaluar opciones de beca o programas "
        f"de menor costo."
    )


def calculate_roi(program: Program) -> RoiCalculation:
    """Pure function: dada una row Program devuelve el cálculo ROI completo."""

    # ----- Costos -----
    tuition_total = int(program.cost_total or 0)
    living_year = int(program.living_cost_city_usd_year or 0)
    # Estudios típicamente medidos en meses; convertimos a años (mínimo 1 año
    # de costo de vida para programas cortos de algunos meses).
    duration_years = max((program.duration_months or 0) / 12.0, 1.0) if living_year else 0
    living_total = int(round(living_year * duration_years)) if living_year else 0
    total_investment = tuition_total + living_total

    cost_breakdown = RoiCostBreakdown(
        tuition_total_usd=tuition_total,
        living_cost_year_usd=living_year,
        living_cost_total_usd=living_total,
        total_investment_usd=total_investment,
    )

    # ----- Visa -----
    visa = RoiVisaInfo(
        type=program.visa_type,
        max_years_work=program.visa_max_years_work,
        requires_degree_alignment=program.visa_requires_degree_alignment,
        notes=program.visa_notes,
    )

    # ----- Post-grad earnings -----
    entry_salary = program.entry_salary_local_usd
    years_work = program.visa_max_years_work
    max_earnings: Optional[int] = None
    if entry_salary and years_work:
        max_earnings = int(entry_salary) * int(years_work)

    post_grad = RoiPostGrad(
        entry_salary_year_usd=entry_salary,
        years_eligible_work=years_work,
        max_potential_earnings_usd=max_earnings,
    )

    # ----- ROI calc -----
    payback: Optional[float] = None
    net_value: Optional[int] = None
    if entry_salary and entry_salary > 0 and total_investment > 0:
        payback = round(total_investment / float(entry_salary), 2)
    if max_earnings is not None and total_investment > 0:
        net_value = max_earnings - total_investment

    rating = _rate_roi(payback)
    summary = _summary(program, payback, net_value)

    return RoiCalculation(
        program_id=program.id,
        currency=program.currency or "USD",
        cost_breakdown=cost_breakdown,
        visa=visa,
        post_grad=post_grad,
        payback_years=payback,
        net_value_usd=net_value,
        rating=rating,
        summary=summary,
    )
