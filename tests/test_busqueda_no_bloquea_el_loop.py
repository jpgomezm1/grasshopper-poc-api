"""Los endpoints de búsqueda tienen que ser `def`, no `async def`.

## Qué pasaba

Los escribí `async` porque esperan al proveedor de embeddings. Pero las
consultas que hacen entre medias son SQLAlchemy síncrono, y ejecutarlas dentro
de una corrutina bloquea el event loop entero: mientras una petición espera a
Neon, todas las demás del servidor se congelan.

Medido contra `/busqueda/explorar`, mismo equipo, mismo día:

    concurrentes    `async def`     `def`      /health durante la carga
    ─────────────────────────────────────────────────────────────────
         1             2,2 s        2,5 s
         8            16,3 s        4,1 s      14.199 ms  →  4 ms

Con `async`, ocho estudiantes navegando a la vez se esperaban unos a otros, y
una sola pantalla que dispara siete llamadas se autobloqueaba.

## Por qué un test y no sólo un comentario

Porque el comentario ya existía. `vector_del_perfil_sync` lo dice desde antes:
*"pasarlo a `async` metería consultas bloqueantes dentro del event loop"*. Yo
lo leí después de romperlo. Un test falla en el momento del cambio; un
comentario sólo ayuda a quien pasa por ahí.

Añadir un `async def` a este router es legítimo **si de verdad no toca la base
de datos de forma síncrona**. Si ese día llega, se añade a `PERMITIDOS` con su
razón — igual que `ONBOARDING_FUERA_DEL_PROMPT` en `ai_service`.
"""
from __future__ import annotations

import inspect

from app.api.v1 import busqueda

#: Corrutinas del router que SÍ pueden ser `async`, con su razón.
#:
#: Vacío hoy a propósito: los cuatro endpoints tocan la base sincrónicamente.
PERMITIDOS: dict[str, str] = {}


def _endpoints():
    """Las funciones que el router expone, no los ayudantes del módulo."""
    return {
        r.endpoint.__name__: r.endpoint
        for r in busqueda.router.routes
        if getattr(r, "endpoint", None) is not None
    }


def test_ningun_endpoint_de_busqueda_es_una_corrutina():
    """El test que evita repetir el error.

    FastAPI corre los endpoints `def` en un hilo del pool —que es donde debe
    vivir el I/O bloqueante— y los `async def` en el event loop, donde una
    consulta a Neon congela el servidor para todos.
    """
    culpables = sorted(
        nombre
        for nombre, fn in _endpoints().items()
        if inspect.iscoroutinefunction(fn) and nombre not in PERMITIDOS
    )
    assert not culpables, (
        f"Estos endpoints son `async def` y hacen I/O bloqueante: {culpables}. "
        "Con 8 peticiones simultáneas eso pasó de 4,1 s a 16,3 s y dejó "
        "/health sin responder 14 segundos. Hazlos `def`, o decláralos en "
        "PERMITIDOS explicando por qué no tocan la base."
    )


def test_los_cuatro_endpoints_siguen_ahi():
    """Si alguien renombra un endpoint, el test de arriba dejaría de mirarlo y
    pasaría en verde sin comprobar nada · el error #2 del `backend/CLAUDE.md`."""
    assert set(_endpoints()) >= {
        "explorar", "buscar_programas", "listar_familias", "detalle_de_programa",
    }


def test_el_ayudante_para_llamar_corrutinas_existe():
    """`buscar_con_texto` sigue siendo corrutina (espera al intérprete), así que
    el endpoint síncrono necesita una forma de llamarla. Si esto desaparece, el
    camino con texto libre deja de funcionar."""
    assert callable(getattr(busqueda, "_correr", None))


def test_hay_version_sincrona_de_los_dos_vectores():
    """Los endpoints `def` no pueden `await`. Sin estas dos, alguien "arreglaría"
    el problema volviendo a hacer `async` el endpoint."""
    from app.services import busqueda_programas as bp, familias_programas as fam

    assert callable(bp.vector_del_perfil_sync)
    assert callable(fam.vector_de_familia_sync)
    assert not inspect.iscoroutinefunction(bp.vector_del_perfil_sync)
    assert not inspect.iscoroutinefunction(fam.vector_de_familia_sync)
