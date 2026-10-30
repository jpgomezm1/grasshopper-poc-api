"""Qué incluye cada plan en cada grado · la matriz, en UN solo sitio (D-2, Sprint 4).

Aprobada por JP el 2026-10-29, a partir de la malla del demo de Verónica
(`Hopper · Bot gratuito y perfilamiento (demo v2).html`, pestaña "Tests por
grado"). Si Verónica mueve un test de grado o cambia qué es pago, se cambia
AQUÍ y en ningún otro lado: el backend la aplica (`permisos_service`) y el front
la lee (`GET /me/permisos`).

## Decisiones por defecto (2026-10-29, se pueden cambiar)

- **Valores laborales y Anclas de carrera** no están en la malla del demo; van
  solo para profesionales porque son tests de trabajo.
- **Lo que el demo pide y no existe todavía** (Mentoring Profiler, estilo de
  vida y presupuesto, simulador de admisiones, análisis de LinkedIn) está en
  `NO_DISPONIBLE`: se muestra como "pronto", no se puede usar. Se construye en
  E-2…E-5.
- **Sin grado conocido** (cuentas viejas que nunca dijeron su grado) se le
  ofrecen todos los tests de su plan: quitarle tests que ya podía hacer sería
  romper D9 ("ninguna cuenta que ya existe pierde acceso").
"""
from __future__ import annotations

from typing import Dict, Tuple

from app.data.onboarding_hechos import (
    RUTA_GRADO_9,
    RUTA_GRADO_10,
    RUTA_GRADO_11,
    RUTA_GRADO_12,
    RUTA_PROFESIONAL,
)

# Orden de los planes · "requiere pago" = pago o VIP.
ORDEN_PLAN = {"gratis": 0, "pago": 1, "vip": 2}

# ---------------------------------------------------------------------------
# Funciones · el plan mínimo que las abre
# ---------------------------------------------------------------------------

FUNCIONES: Dict[str, Dict[str, str]] = {
    "onboarding": {"plan": "gratis", "nombre": "Conversación inicial con Hopper"},
    "senal_preliminar": {"plan": "gratis", "nombre": "Tu señal preliminar"},
    "tests": {"plan": "pago", "nombre": "Tests de tu etapa"},
    "lectura_tests": {"plan": "pago", "nombre": "Lectura completa de cada test"},
    "reporte_pdf": {"plan": "pago", "nombre": "Reporte en PDF"},
    "hoja_de_vida": {"plan": "pago", "nombre": "Hoja de vida"},
    "carta_motivacion": {"plan": "pago", "nombre": "Carta de motivación"},
    "chat_hopper": {"plan": "pago", "nombre": "Chat con Hopper"},
    "programas": {"plan": "pago", "nombre": "Programas y universidades"},
    "biblioteca": {"plan": "pago", "nombre": "Biblioteca de contenido y videos"},
    "practica_examenes": {"plan": "pago", "nombre": "Práctica de SAT e IELTS"},
    "profiler": {"plan": "vip", "nombre": "Mentoring Profiler"},
    "sesion_1a1": {"plan": "vip", "nombre": "Sesión 1:1 con un counsellor"},
}

# Funciones que además dependen del grado · si no está, aplica a todos.
FUNCION_SOLO_EN_TRAMOS: Dict[str, Tuple[str, ...]] = {
    "practica_examenes": (RUTA_GRADO_11, RUTA_GRADO_12, RUTA_PROFESIONAL),
}

# Lo que el demo pide y todavía no existe en la plataforma.
NO_DISPONIBLE = ("profiler",)

# ---------------------------------------------------------------------------
# Tests por grado · ids de `app/data/vocational_tests.py`
# ---------------------------------------------------------------------------

TESTS_POR_TRAMO: Dict[str, Tuple[str, ...]] = {
    # Explorador Inicial · autoconocimiento sin presión de elegir carrera.
    # Holland en 9° es la versión juvenil (`vocational_bank_selector`).
    RUTA_GRADO_9: ("vark", "motivadores", "holland"),
    # Perfil de Competencias · motivadores otra vez, para medir la evolución.
    RUTA_GRADO_10: ("bigfive", "habilidades-blandas", "motivadores"),
    # Filtro realista.
    RUTA_GRADO_11: ("istrong", "mbti", "bigfive"),
    # Plan de vuelo · re-chequeo corto de motivadores.
    RUTA_GRADO_12: ("motivadores",),
    # Reinvención y upskilling.
    RUTA_PROFESIONAL: ("mbti", "istrong", "values", "career-anchors"),
}

# El test de inglés (AMES) va aparte: no es un test vocacional. Opcional en 10°.
INGLES_EN_TRAMOS: Tuple[str, ...] = (RUTA_GRADO_10, RUTA_GRADO_11, RUTA_GRADO_12, RUTA_PROFESIONAL)
