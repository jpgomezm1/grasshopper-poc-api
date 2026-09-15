"""El intérprete de búsqueda · lo que un vector no puede hacer solo.

Los tres casos de abajo están **medidos contra el catálogo real**, no imaginados:

  negación ....... "no quiero estar sentado en una oficina" devolvía
                   `Postgrado en Diseño del Espacio Interior`. Y no era cuestión
                   de afinar: `Outdoor Adventure Leadership` puntuaba 0.217
                   contra 0.281 del programa de oficinas, o sea que la respuesta
                   correcta puntuaba PEOR que la absurda.
  dos intereses .. "animales pero también dibujar" daba 0.346 y diez programas
                   de dibujo. Separando los conceptos: 0.618 y las dos cosas.
  fuera de alcance "cuánto cuesta" no tiene respuesta en este catálogo, y decirlo
                   es mejor que devolver programas como si la hubiera.

Se mockea en la **frontera** (`AsyncOpenAI`), no la función que se prueba.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services import busqueda_programas as bp, interprete_busqueda as ib


def _modelo_que_responde(payload, monkeypatch):
    """Sustituye el cliente de OpenAI por uno que devuelve lo que se le diga."""
    class _Msg:
        content = payload if isinstance(payload, str) else json.dumps(payload)

    class _Completions:
        async def create(self, **k):
            return SimpleNamespace(choices=[SimpleNamespace(message=_Msg())])

    class _Cli:
        def __init__(self, **k):
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr("openai.AsyncOpenAI", _Cli)
    monkeypatch.setattr(ib, "get_settings",
                        lambda: SimpleNamespace(openai_api_key="sk-prueba"))


def test_una_negacion_se_convierte_en_lo_que_la_persona_si_quiere(monkeypatch):
    """Un embedding no puede representar un "no" · hay que darle la vuelta."""
    _modelo_que_responde({
        "conceptos": ["trabajo al aire libre y en terreno",
                      "oficios prácticos con las manos"],
        "filtros": {}, "fuera_de_alcance": [],
        "entendi": "Buscas algo al aire libre",
    }, monkeypatch)

    r = asyncio.run(ib.interpretar("no quiero estar sentado en una oficina"))

    assert r.conceptos
    # Lo que NO puede pasar: que la negación sobreviva en el concepto, porque
    # entonces se busca por parecido con "oficina" y vuelve el error original.
    assert not any("no " in c.lower() for c in r.conceptos)
    assert not any("oficina" in c.lower() for c in r.conceptos)


def test_dos_intereses_salen_como_dos_conceptos(monkeypatch):
    _modelo_que_responde({
        "conceptos": ["animales y veterinaria", "dibujo e ilustración"],
        "filtros": {}, "fuera_de_alcance": [], "entendi": "Animales y dibujo",
    }, monkeypatch)

    r = asyncio.run(ib.interpretar("me gustan los animales pero también dibujar"))

    assert len(r.conceptos) == 2


def test_un_filtro_inventado_por_el_modelo_se_descarta(monkeypatch):
    """Los vocabularios van cerrados en el prompt, pero eso no basta.

    Un filtro que no existe no acota: **esconde el catálogo entero**, porque
    ninguna fila lo cumple. Y el estudiante no tendría forma de saber por qué la
    pantalla se quedó vacía.
    """
    _modelo_que_responde({
        "conceptos": ["diseño"],
        "filtros": {"paises": ["Wakanda", "Canadá"],
                    "areas": ["Ciencias Ocultas"],
                    "niveles": ["superdoctorado", "maestria"]},
        "fuera_de_alcance": ["horóscopo"], "entendi": "",
    }, monkeypatch)

    r = asyncio.run(ib.interpretar("diseño"))

    assert r.paises == ["Canadá"]
    assert r.areas == []
    assert r.niveles == ["maestria"]
    assert r.fuera_de_alcance == []


def test_sin_interes_no_se_inventa_lo_que_se_entendio(monkeypatch):
    """El caso que se vio de verdad: escribiendo "hola", el modelo devolvía
    `conceptos: []` —correcto— y a la vez copiaba **el ejemplo del prompt** en
    `entendi`: "Buscas algo al aire libre, lejos del escritorio".

    Esa frase se le muestra al estudiante para que confirme si le entendimos, así
    que una alucinación ahí es de las que más confunden. Los modelos pequeños
    copian los ejemplos cuando la entrada no les da de qué agarrarse, y pedirles
    que no lo hagan no alcanza: se corta en el código.
    """
    _modelo_que_responde({
        "conceptos": [], "filtros": {}, "fuera_de_alcance": [],
        "entendi": "Buscas algo al aire libre, lejos del escritorio",
    }, monkeypatch)

    r = asyncio.run(ib.interpretar("hola"))

    assert r.conceptos == []
    assert r.entendi == ""


def test_si_el_modelo_falla_la_busqueda_sigue(monkeypatch):
    """La IA mejora la búsqueda, no la sostiene · el mismo criterio del resto."""
    class _Completions:
        async def create(self, **k):
            raise RuntimeError("proveedor caido")

    class _Cli:
        def __init__(self, **k):
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr("openai.AsyncOpenAI", _Cli)
    monkeypatch.setattr(ib, "get_settings",
                        lambda: SimpleNamespace(openai_api_key="sk-prueba"))

    r = asyncio.run(ib.interpretar("quiero estudiar diseño"))

    assert r.interpretada is False
    # Cae al texto original: se busca como se buscaba antes de este módulo.
    assert r.conceptos == ["quiero estudiar diseño"]


def test_un_json_roto_no_tumba_la_busqueda(monkeypatch):
    _modelo_que_responde("esto no es json, es una disculpa", monkeypatch)
    r = asyncio.run(ib.interpretar("diseño"))
    assert r.interpretada is False
    assert r.conceptos == ["diseño"]


def test_el_json_envuelto_en_markdown_se_lee_igual(monkeypatch):
    """Los modelos pequeños envuelven en ```json aunque se les pida que no."""
    _modelo_que_responde(
        '```json\n{"conceptos": ["enfermería"], "filtros": {}, '
        '"fuera_de_alcance": [], "entendi": "Enfermería"}\n```', monkeypatch)

    r = asyncio.run(ib.interpretar("quiero ser enfermera"))

    assert r.interpretada is True
    assert r.conceptos == ["enfermería"]


# ---------------------------------------------------------------------------
# La mezcla de conceptos
# ---------------------------------------------------------------------------


def _r(nombre, sim):
    return bp.Resultado(
        id=nombre, nombre=nombre, institucion="X", pais=None, ciudad=None,
        nivel="bachelor", area="Artes", duracion=None, codigo_oficial=None,
        url_fuente=None, similitud=sim, puntaje=sim,
    )


def test_el_concepto_con_mas_oferta_no_se_come_al_otro():
    """Ordenar la unión por puntaje **reproduce el problema original**.

    "Dibujar" tiene 2.041 programas en el catálogo y "animales" 312, así que si
    se ordena por similitud el concepto con más oferta copa las primeras
    posiciones igual que cuando había un solo vector. La persona pidió las dos
    cosas.
    """
    dibujo = [_r(f"dibujo{i}", 0.90 - i / 100) for i in range(10)]
    animales = [_r(f"animal{i}", 0.50 - i / 100) for i in range(10)]

    mezcla = bp.mezclar_por_concepto([animales, dibujo], limite=4)

    nombres = [x.nombre for x in mezcla]
    assert sum(n.startswith("animal") for n in nombres) == 2
    assert sum(n.startswith("dibujo") for n in nombres) == 2


def test_dentro_de_cada_concepto_manda_la_pertinencia():
    a = [_r("a1", 0.9), _r("a2", 0.8)]
    b = [_r("b1", 0.7), _r("b2", 0.6)]

    mezcla = bp.mezclar_por_concepto([a, b], limite=4)

    assert [x.nombre for x in mezcla] == ["a1", "b1", "a2", "b2"]


def test_un_programa_que_sale_en_dos_conceptos_no_se_duplica():
    """Es el caso normal, no el raro: "animales" y "veterinaria" devuelven lo
    mismo muchas veces, y verlo dos veces en la lista se lee como un error."""
    comun = _r("Veterinary Nursing", 0.8)
    a = [comun, _r("a2", 0.7)]
    b = [comun, _r("b2", 0.6)]

    mezcla = bp.mezclar_por_concepto([a, b], limite=10)

    assert [x.nombre for x in mezcla].count("Veterinary Nursing") == 1


def test_sin_conceptos_no_revienta():
    assert bp.mezclar_por_concepto([], limite=5) == []
    assert bp.mezclar_por_concepto([[], []], limite=5) == []
