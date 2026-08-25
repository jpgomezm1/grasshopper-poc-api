"""Schemas de `GET /api/v1/year-checkin` · memoria entre años.

Contrato con el frontend:
  - `has_memory=False` (caso normal hoy, ver `year_memory_service`): no hay
    snapshot del año pasado todavía · el frontend debe usar el flujo normal
    de onboarding (`/onboarding-chat/inicio`), no este check-in.
  - `has_memory=True, is_new_grade=False`: hay memoria pero el grado no
    cambió (mismo año) · tampoco hay check-in que mostrar.
  - `has_memory=True, is_new_grade=True`: éste es el caso que dispara el
    check-in · `checkin_message` viene poblado (por IA o por la plantilla
    determinista de fallback, nunca `None` en este caso).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PerfilDeclaradoOut(BaseModel):
    """Lo cualitativo que el estudiante contó, en un momento dado."""

    pasion: Optional[str] = None
    hobbies: Optional[str] = None
    fortalezas: Optional[str] = None
    objetivo: Optional[str] = None
    interes_exterior: Optional[str] = None
    paises: List[str] = []
    presupuesto: Optional[str] = None


class TestTomadoOut(BaseModel):
    test_id: str
    taken_at: datetime


class AnioAnteriorOut(BaseModel):
    school_year: int
    grade: Optional[int] = None
    perfil: PerfilDeclaradoOut
    # Siempre False hoy · ver `year_memory_service` (el cimiento no versiona
    # tests ni rutas por año, sólo `grade` + `onboarding_answers_snapshot`).
    tests_available: bool = False
    route_available: bool = False


class HoyOut(BaseModel):
    grade: Optional[int] = None
    perfil: PerfilDeclaradoOut
    tests_taken: List[TestTomadoOut] = []
    active_routes: List[str] = []


class YearCheckinResponse(BaseModel):
    has_memory: bool
    is_new_grade: bool
    previous: Optional[AnioAnteriorOut] = None
    today: HoyOut
    changed_fields: List[str] = []
    checkin_message: Optional[str] = None
