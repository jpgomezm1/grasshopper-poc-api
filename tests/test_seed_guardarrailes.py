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


# ---------------------------------------------------------------------------
# Los alumnos demo tienen que tener resultados de verdad
# ---------------------------------------------------------------------------
#
# Encontrado en producción el 2026-08-07: la siembra insertaba
# `{"sample": "scores"}` con test_id "riasec"/"big5". Al correr el backfill de
# lecturas (A2) la IA no tenía nada que leer y escribió sobre QUÉ ES cada test
# en vez de sobre la persona — tres alumnos distintos compartían titular y
# resumen. Reprodujimos nosotros mismos la queja de la clienta ("le salen unas
# siglas y ya") justo en las cuentas que ella abre para ver el producto.


def _seed_module():
    import importlib.util

    ruta = Path(__file__).resolve().parent.parent / "scripts" / "seed_test_data.py"
    spec = importlib.util.spec_from_file_location("seed_test_data", ruta)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:  # pragma: no cover · el script parsea args al importarse
        pass
    return mod


def test_no_queda_ningun_placeholder_de_puntajes(fuente):
    """El defecto original, fijado para que no vuelva.

    Se miran sólo las líneas de CÓDIGO: el comentario que explica el defecto
    cita el placeholder a propósito, y no tiene por qué hacer fallar el test.
    """
    codigo = "\n".join(
        l for l in fuente.splitlines() if not l.strip().startswith("#")
    )
    assert '"sample": "scores"' not in codigo
    assert "'sample': 'scores'" not in codigo


def test_los_test_id_sembrados_son_los_que_el_producto_reconoce(fuente):
    """`test_interpretation_service._label_map` devuelve {} para cualquier id
    que no sea de su lista, y entonces la lectura sale sin etiquetas legibles.
    "riasec" y "big5" NO están en esa lista; "holland" y "bigfive" sí."""
    from app.services.test_interpretation_service import _label_map

    for tid in _seed_module()._DIMENSIONES:
        assert _label_map(tid), f"la siembra usa '{tid}' y el producto no lo reconoce"


def test_dos_alumnos_no_reciben_el_mismo_perfil():
    """Si todos salieran iguales, la demo volvería a mostrar el problema."""
    m = _seed_module()
    perfiles = {tuple(m._puntajes_demo("holland", a).values()) for a in range(30)}
    assert len(perfiles) == 30, "hay alumnos demo con perfiles idénticos"

    dominantes = {
        max(m._puntajes_demo("holland", a), key=m._puntajes_demo("holland", a).get)
        for a in range(30)
    }
    assert len(dominantes) >= 5, f"poca variedad de perfiles: {sorted(dominantes)}"


def test_un_alumno_no_saca_lo_mismo_en_dos_tests_distintos():
    """La primera versión de la fórmula no miraba el test_id, así que holland y
    bigfive daban los mismos números para la misma persona."""
    m = _seed_module()
    holland = list(m._puntajes_demo("holland", 4).values())
    bigfive = list(m._puntajes_demo("bigfive", 4).values())
    assert holland[: len(bigfive)] != bigfive


def test_los_puntajes_son_reproducibles_entre_corridas():
    """`hashlib` y no `hash()`, que está salteado por proceso · si no, sembrar
    dos veces da perfiles distintos y una demo deja de poder repetirse."""
    m = _seed_module()
    assert m._puntajes_demo("mbti", 9) == m._puntajes_demo("mbti", 9)


def test_los_puntajes_caen_en_el_rango_de_un_test_real():
    m = _seed_module()
    for tid in m._DIMENSIONES:
        for valor in m._puntajes_demo(tid, 3).values():
            assert 0 <= valor <= 100, f"{tid} produjo {valor}"


def test_un_test_id_desconocido_falla_ruidosamente():
    """Antes cualquier id colaba y el problema aparecía meses después en
    producción · ahora revienta al sembrar."""
    import pytest

    m = _seed_module()
    with pytest.raises(ValueError, match="sin dimensiones"):
        m._puntajes_demo("test-que-no-existe", 1)
