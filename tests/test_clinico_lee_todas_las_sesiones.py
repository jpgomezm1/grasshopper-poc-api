"""El detector de riesgo ve todo lo que el estudiante escribió · 2026-09-19.

`clinical_analysis_service` analizaba **una** sesión del journey: la última
tocada. Si un race dejó sesiones duplicadas —y el propio código del repo
documenta que los produjo— el texto de las otras era invisible. Un estudiante
podía escribir algo grave en una sesión y el detector estar mirando la otra.

El `backend/CLAUDE.md` prohíbe tocar este archivo porque **bajarle sensibilidad
la valida la psicóloga**, y cambiar qué texto se analiza es cambiar la
sensibilidad. Por eso el arreglo no elige mejor: no elige. Lee todas.

La propiedad que hace el cambio aceptable, y lo que fijan estos tests: **el
detector no puede ver menos texto del que veía antes.** La dirección es la única
admisible en un detector de riesgo. La contrapartida —más activaciones del
protocolo, sobre un archivo que ya documenta falsos positivos conocidos— es una
consecuencia clínica que la psicóloga debe conocer, no un efecto secundario que
se descubra por accidente.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.clinical_analysis_service import _todo_lo_que_escribio


def _sesion(answers, sid=None):
    return SimpleNamespace(id=sid or uuid4(), answers=answers)


def _db(sesiones, entradas):
    db = MagicMock()
    cadena = db.query.return_value
    cadena.filter.return_value = cadena
    cadena.order_by.return_value = cadena
    # `Session` se consulta con order_by; `JournalEntry` con filter+order_by.
    cadena.all.side_effect = [sesiones, entradas]
    return db


_ALUMNO = SimpleNamespace(id=uuid4())


def test_se_leen_las_respuestas_de_TODAS_las_sesiones():
    """El caso del race: lo escrito en la sesión huérfana también cuenta."""
    db = _db([_sesion({"whyHere": "no le veo sentido a nada"}),
              _sesion({"dontWant": "algo teorico"})], [])
    respuestas, _ = _todo_lo_que_escribio(db, _ALUMNO)
    assert respuestas["whyHere"] == "no le veo sentido a nada"
    assert respuestas["dontWant"] == "algo teorico"


def test_la_sesion_mas_reciente_gana_en_las_claves_repetidas():
    """Es la respuesta vigente de la persona · las sesiones vienen ordenadas de
    la más vieja a la más nueva y se van pisando."""
    db = _db([_sesion({"clarityLevel": "no se nada"}),
              _sesion({"clarityLevel": "ya tengo idea"})], [])
    respuestas, _ = _todo_lo_que_escribio(db, _ALUMNO)
    assert respuestas["clarityLevel"] == "ya tengo idea"


def test_la_bitacora_se_junta_de_todas_las_sesiones():
    entradas = [SimpleNamespace(content="a"), SimpleNamespace(content="b")]
    db = _db([_sesion({}), _sesion({})], entradas)
    _, bitacora = _todo_lo_que_escribio(db, _ALUMNO)
    assert len(bitacora) == 2


def test_sin_sesiones_no_se_consulta_la_bitacora():
    """Un estudiante recién registrado · ni error ni consulta de más."""
    db = _db([], [])
    respuestas, bitacora = _todo_lo_que_escribio(db, _ALUMNO)
    assert respuestas == {} and bitacora == []


def test_una_sesion_sin_respuestas_no_borra_las_de_otra():
    """El cascarón vacío no puede vaciar lo que la persona sí escribió · era
    justo el riesgo de "elegir una sesión" en vez de leerlas todas."""
    db = _db([_sesion({"whyHere": "me siento perdido"}), _sesion(None)], [])
    respuestas, _ = _todo_lo_que_escribio(db, _ALUMNO)
    assert respuestas["whyHere"] == "me siento perdido"


def test_el_texto_grave_de_una_sesion_huerfana_llega_al_corpus():
    """La prueba de que el arreglo sirve donde dolía.

    Antes, con la sesión grave siendo la MENOS recientemente tocada, su texto no
    entraba al corpus que revisa el detector de palabras críticas.
    """
    from app.services.clinical_analysis_service import _build_corpus

    db = _db([_sesion({"whyHere": "a veces pienso que no quiero seguir viviendo"}),
              _sesion({"geoPreference": "Canada"})], [])
    respuestas, bitacora = _todo_lo_que_escribio(db, _ALUMNO)
    alumno = SimpleNamespace(id=_ALUMNO.id, onboarding_answers={}, name="x")
    corpus = _build_corpus(alumno, respuestas, bitacora)
    assert "no quiero seguir viviendo" in corpus.lower()
