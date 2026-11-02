"""Recorridos Sprint 4 · los bancos de tests se leen con tildes.

En producción, el Big Five decía "Evalua las 5 dimensiones… Extraversion",
"Tengo una imaginacion muy activa" y "el mas aceptado en psicologia". Es lo
primero que lee un estudiante (y su familia) antes de responder 50 preguntas, y
la clienta revisa la copy. Este test vigila las palabras que estaban mal; si
alguien agrega un ítem sin tildes, falla y dice cuál.
"""
from __future__ import annotations

import re

from app.data.holland_junior import get_holland_junior
from app.data.vocational_tests import VOCATIONAL_TESTS

SIN_TILDE = re.compile(
    r"\b(atencion|demas|educacion|facilmente|tecnologia|dificiles|informacion|logica|"
    r"imaginacion|musica|grafico|extraversion|academicos|filosoficos|publico|cientificos|"
    r"matematicas|numeros|evalua|psicologia|exito|rapidamente|segun|tambien|ademas|despues)\b",
    re.IGNORECASE,
)


def _textos(obj):
    if isinstance(obj, str):
        if " " in obj:  # ids y claves no llevan espacios
            yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _textos(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _textos(v)


def test_los_bancos_de_tests_llevan_tildes():
    malos = sorted(
        {m.group(0) for t in _textos([VOCATIONAL_TESTS, get_holland_junior()]) for m in SIN_TILDE.finditer(t)}
    )
    assert not malos, f"palabras sin tilde en los bancos de tests: {malos}"
