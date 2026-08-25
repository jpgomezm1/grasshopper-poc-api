"""Schemas de la recomendación de materias electivas.

Reunión clienta 2026-08-24 (minuto 27:00) · ver `app/services/electives_service.py`
para el porqué de cada campo.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ElectiveRecommendation(BaseModel):
    subject: str
    # True/False = el colegio SÍ cargó qué ofrece y esta materia coincide o no.
    # None = no sabemos: el colegio todavía no cargó `subjects_offered`, así
    # que no podemos afirmar nada sobre SU oferta puntual (regla "no prometas").
    ofrecida_por_colegio: Optional[bool] = None


class ElectivesResponse(BaseModel):
    study_area: Optional[str] = None
    study_area_label: Optional[str] = None
    grade: Optional[int] = None
    # La clienta: "es una recomendación útil sobre todo en grado 10 y 11,
    # cuando todavía se pueden elegir". No bloquea otros grados, sólo informa.
    especialmente_util_ahora: bool = False
    # False = la recomendación es general (no se sabe qué ofrece el colegio
    # del estudiante); True = se cruzó contra `School.subjects_offered`.
    tiene_datos_colegio: bool = False
    recomendaciones: List[ElectiveRecommendation] = []
    mensaje: str
    disclaimer: str
