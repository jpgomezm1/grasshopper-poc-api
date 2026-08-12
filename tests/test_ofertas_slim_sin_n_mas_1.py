"""El `slim=true` del catálogo no puede dejarse columnas fuera (2026-08-10).

## Qué pasó

`GET /v1/ofertas?slim=true` es lo que pide la lista del catálogo. Para no traer
los JSON pesados usa `load_only(...)` con una lista explícita de columnas — y esa
lista **se había quedado sin `subject` ni `area`**, que el mapper sí lee.

SQLAlchemy no falla cuando eso pasa: carga la columna que falta *en cuanto se
toca*, con una consulta suelta por fila. Dos columnas × 2.508 filas = 5.016
consultas extra a Neon, a unos 169 ms cada una.

**Medido: 7 minutos en vez de 2 segundos.** Y sin un solo error en consola ni en
los logs: desde el navegador se veía como una lista que carga para siempre.

## Por qué este test y no otro

Un test de "el endpoint responde 200" habría pasado igual de verde con el bug
puesto — sólo que tardando siete minutos. Lo que hay que fijar no es la respuesta
sino la **ausencia de N+1**, así que se comprueba la única causa posible: que
todo lo que el mapper lee esté en la lista de `load_only`.

El aviso ya estaba escrito en el propio endpoint ("cualquier columna nueva que
`_program_to_oferta` empiece a leer debe agregarse acá"). No bastó: un comentario
no falla el build. Esto sí.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import app.api.v1.ofertas as ofertas_mod


def _columnas_del_load_only() -> set[str]:
    """Las columnas que el endpoint declara en su `load_only(...)`.

    Se leen del AST y no ejecutando el endpoint: no hace falta base de datos, y
    así el test corre en cualquier sitio y en milisegundos.
    """
    fuente = Path(inspect.getfile(ofertas_mod)).read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        if getattr(nodo.func, "id", None) != "load_only":
            continue
        return {
            arg.attr
            for arg in nodo.args
            if isinstance(arg, ast.Attribute) and getattr(arg.value, "id", "") == "Program"
        }
    raise AssertionError("No se encontró la llamada a load_only() en ofertas.py")


def _columnas_que_lee_el_mapper() -> set[str]:
    """Los `Program.<algo>` que toca `_program_to_oferta`, sacados de su código."""
    fuente = inspect.getsource(ofertas_mod._program_to_oferta)
    arbol = ast.parse(fuente.lstrip())

    # El parámetro con el que el mapper recibe la fila (`p`, `program`, …).
    fn = next(n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef))
    fila = fn.args.args[0].arg

    return {
        nodo.attr
        for nodo in ast.walk(fn)
        if isinstance(nodo, ast.Attribute)
        and isinstance(nodo.value, ast.Name)
        and nodo.value.id == fila
    }


def test_slim_trae_todas_las_columnas_que_el_mapper_lee():
    """Si esto falla, el catálogo se vuelve N+1 y tarda minutos, no segundos."""
    declaradas = _columnas_del_load_only()
    leidas = _columnas_que_lee_el_mapper()

    # Sólo interesan los atributos que son columnas de verdad del modelo: el
    # mapper también llama métodos y lee cosas que no vienen de la tabla.
    from app.db.models import Program

    columnas_reales = {c.key for c in Program.__table__.columns}
    faltantes = (leidas & columnas_reales) - declaradas

    assert not faltantes, (
        "El `load_only` de slim=true no trae estas columnas y el mapper sí las "
        f"lee: {sorted(faltantes)}. SQLAlchemy las pediría una por una (una "
        "consulta por fila y columna), y con 2.508 filas eso son minutos de "
        "espera sin ningún error visible. Agrégalas a la lista en `list_ofertas`."
    )


def test_subject_y_area_siguen_en_la_lista():
    """El caso concreto que se escapó · prueba de regresión, no de forma.

    Va aparte del test de arriba a propósito: si alguien cambia el mapper para
    dejar de leerlas, aquel test pasaría a verde sin ellas y perderíamos la
    memoria de qué falló. Éste obliga a borrarlo a mano y a preguntarse por qué.
    """
    declaradas = _columnas_del_load_only()

    assert {"subject", "area"} <= declaradas
