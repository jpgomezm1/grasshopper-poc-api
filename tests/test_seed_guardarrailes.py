"""Guardarraíles de `scripts/seed_test_data.py`.

Este script es el más peligroso del repo: se corre **contra producción** (es la
única forma de cargar datos de demo, porque las credenciales viven en Heroku) y
tenía dos formas de hacer daño real:

  1. `--clean` borraba las cuentas de **Verónica y Sebastián**, que son personas
     reales y cuyo historial de pruebas nadie puede regenerar.
  2. El seed metía 50 programas con **precios inventados** (Harvard a $78.000)
     en la misma tabla `programs` que sirve `/ofertas`, con `active=true` y sin
     marca que los distinga de los reales.

Los dos están corregidos. Estos tests existen para que no vuelvan: son
afirmaciones sobre el archivo, no sobre la base, así que corren sin DB y sin
riesgo de tocar nada.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "seed_test_data.py"
)


@pytest.fixture(scope="module")
def fuente() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_las_cuentas_del_cliente_estan_protegidas(fuente: str):
    """Verónica y Sebastián no pueden entrar al DELETE de `--clean`."""
    assert "CUENTAS_REALES_NO_BORRAR" in fuente
    assert "veronica@stayirrelevant.com" in fuente
    assert "sebastian@stayirrelevant.com" in fuente

    # La exclusión tiene que estar aplicada donde se arma la lista del DELETE,
    # no solo declarada arriba.
    bloque = fuente.split("def clean()")[1]
    assert "CUENTAS_REALES_NO_BORRAR" in bloque, (
        "la constante existe pero clean() no la usa · el DELETE sigue abierto"
    )


def test_el_delete_de_clean_tiene_los_parentesis_del_or(fuente: str):
    """`A AND B OR C` se evalúa como `(A AND B) OR C`.

    Funcionaba por casualidad. Con los paréntesis explícitos, agregar una
    condición nueva arriba deja de poder ampliar silenciosamente el DELETE.
    """
    bloque = fuente.split("def clean()")[1]
    assert re.search(r"WHERE\s*\(email LIKE", bloque), (
        "el WHERE del DELETE de usuarios perdió los paréntesis explícitos"
    )


def test_se_pueden_sembrar_datos_sin_tocar_el_catalogo(fuente: str):
    """Sin `--sin-programas` no hay forma segura de correrlo contra producción.

    El pedido A7 de Verónica ("no hay usuarios de un colegio y no sé cómo crear
    nuevos") no necesita programas · necesita colegios y estudiantes.
    """
    assert "--sin-programas" in fuente
    assert "def seed(con_programas" in fuente
    assert "con_programas=not args.sin_programas" in fuente


def test_el_precio_inventado_sigue_estando_marcado_como_peligroso(fuente: str):
    """Si alguien quita el aviso, que al menos falle un test.

    El precio de Harvard sigue en el archivo a propósito (es data de demo útil
    en local); lo que no puede desaparecer es la advertencia de que no va a
    producción.
    """
    assert "78000" in fuente, "cambió la data de demo · revisar este test"
    assert "precios inventados" in fuente.lower()


def test_reset_de_ingles_no_borra_sin_confirmar():
    """El reset del test de inglés es destructivo y no tiene deshacer."""
    reset = (
        Path(__file__).resolve().parent.parent / "scripts" / "reset_english_test.py"
    ).read_text(encoding="utf-8")

    assert "--confirmar" in reset
    # El borrado tiene que estar detrás del flag, no antes.
    antes_del_flag, despues = reset.split("if not args.confirmar:")
    assert "db.delete" not in antes_del_flag, (
        "se borra antes de comprobar --confirmar · el dry-run no es dry"
    )
    assert "db.delete" in despues
