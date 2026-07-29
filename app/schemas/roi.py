"""Schemas for the program ROI calculator · F-002 etapa 1 (2026-05-21)."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class RoiCostBreakdown(BaseModel):
    """P1-19 · Los costos son OPCIONALES a propósito.

    El catálogo real (2.511 filas) trae `cost_total` en NULL — el importador nunca
    lo escribe (`build_programs_from_catalog.py`). Antes estos campos eran `int` y
    el servicio hacía `int(cost_total or 0)`, así que un costo DESCONOCIDO se
    presentaba como matrícula de **$0** y alimentaba un payback y un rating de
    "inversión positiva" ficticios.

    `None` significa "no lo sabemos" y el front lo pinta como "—". Nunca 0.
    """

    tuition_total_usd: Optional[int] = None
    living_cost_year_usd: Optional[int] = None
    living_cost_total_usd: Optional[int] = None
    total_investment_usd: Optional[int] = None


class RoiVisaInfo(BaseModel):
    type: Optional[str] = None
    max_years_work: Optional[int] = None
    requires_degree_alignment: Optional[bool] = None
    notes: Optional[str] = None


class RoiPostGrad(BaseModel):
    entry_salary_year_usd: Optional[int] = None
    years_eligible_work: Optional[int] = None
    max_potential_earnings_usd: Optional[int] = None


RoiRating = Literal["positive", "neutral", "negative", "insufficient_data"]


class RoiCalculation(BaseModel):
    """Response of GET /programs/{id}/roi."""

    program_id: UUID
    currency: str = "USD"
    cost_breakdown: RoiCostBreakdown
    visa: RoiVisaInfo
    post_grad: RoiPostGrad
    # `payback_years` = total_investment / entry_salary_year (None si insufficient data)
    payback_years: Optional[float] = None
    # `net_value_usd` = max_potential_earnings - total_investment (None si insufficient data)
    net_value_usd: Optional[int] = None
    rating: RoiRating
    # Human-readable explanation
    summary: str
