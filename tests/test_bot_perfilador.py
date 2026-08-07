"""Tests del perfilador comercial · el bot que reemplaza el Typeform.

Se mockea **la frontera** (el cliente del SDK vía `ai_client.get_client`), no las
funciones bajo prueba. Es la regla que dejó el cierre del 05-08: once tests en
verde convivían con `linkedin_import_service` roto al 100% porque mockeaban la
función en vez del SDK, y el único camino real no lo tocaba ningún test.

El test que más importa de este archivo no es ninguno de los del extractor: es
`test_contrato_con_el_seeding_del_journey`. La decisión de producto fue
conversación pura con extracción por IA, así que el único punto donde eso puede
romper el resto de la plataforma es el contrato de claves — si alguien renombra
un hecho, ese test falla antes de que el journey empiece a repreguntar.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import ai_client
from app.data import perfilador_typeform as catalogo
from app.services import bot_lead_scoring, conversation_engine, fact_extractor


# ---------------------------------------------------------------------------
# Doble de la frontera · el SDK de Anthropic
# ---------------------------------------------------------------------------


class _FakeMessages:
    def __init__(self, outcome):
        self._outcome = outcome
        self.kwargs = None
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeClient:
    def __init__(self, outcome):
        self.messages = _FakeMessages(outcome)

    def with_options(self, **kwargs):
        return self


def _patch_sdk(monkeypatch, outcome):
    client = _FakeClient(outcome)
    monkeypatch.setattr(ai_client, "get_client", lambda: client)
    return client


def _respuesta_tool(hechos, stop_reason="tool_use"):
    """Respuesta del SDK con un bloque tool_use, como la devuelve de verdad."""
    bloque = SimpleNamespace(type="tool_use", input={"hechos": hechos})
    return SimpleNamespace(
        content=[bloque],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


# ---------------------------------------------------------------------------
# 1 · La primitiva `call_claude_tool`
# ---------------------------------------------------------------------------


def test_tool_call_devuelve_el_input_parseado(monkeypatch):
    _patch_sdk(monkeypatch, _respuesta_tool([{"id": "nombre", "valor": "Ana", "confianza": "alta"}]))

    salida, meta = ai_client.call_claude_tool(
        "prompt", tool_name="t", tool_description="d",
        input_schema={"type": "object"}, session_id="s", feature="f",
    )

    assert salida == {"hechos": [{"id": "nombre", "valor": "Ana", "confianza": "alta"}]}
    assert meta["tokens_input"] == 10


def test_tool_call_fuerza_la_herramienta(monkeypatch):
    """Sin `tool_choice` forzado el modelo puede contestar prosa y no extraer nada."""
    cliente = _patch_sdk(monkeypatch, _respuesta_tool([]))

    ai_client.call_claude_tool(
        "prompt", tool_name="registrar_hechos", tool_description="d",
        input_schema={"type": "object"}, session_id="s", feature="f",
    )

    assert cliente.messages.kwargs["tool_choice"] == {
        "type": "tool", "name": "registrar_hechos"
    }


def test_tool_call_truncado_es_fallo(monkeypatch):
    """Un corte por max_tokens deja el JSON del tool call a medias · no es dato."""
    _patch_sdk(monkeypatch, _respuesta_tool([{"id": "nombre"}], stop_reason="max_tokens"))

    salida, meta = ai_client.call_claude_tool(
        "prompt", tool_name="t", tool_description="d",
        input_schema={"type": "object"}, session_id="s", feature="f",
    )

    assert salida is None
    assert meta["error_kind"] == "truncated"


def test_tool_call_sin_bloque_tool_use_no_intenta_rescatar(monkeypatch):
    """Si el modelo devuelve solo texto NO se parsea de urgencia.

    Un fallback silencioso aquí es exactamente cómo se cuelan datos inventados
    en campos que después siembran el journey.
    """
    solo_texto = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"hechos": [{"id": "nombre"}]}')],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    _patch_sdk(monkeypatch, solo_texto)

    salida, meta = ai_client.call_claude_tool(
        "prompt", tool_name="t", tool_description="d",
        input_schema={"type": "object"}, session_id="s", feature="f",
    )

    assert salida is None
    assert meta["error_kind"] == "empty_response"


# ---------------------------------------------------------------------------
# 2 · El extractor · la red que contiene la conversación pura
# ---------------------------------------------------------------------------


def test_extrae_codigo_valido(monkeypatch):
    _patch_sdk(monkeypatch, _respuesta_tool([
        {"id": "ocupacion", "valor": "high_school", "confianza": "alta"},
    ]))

    validos, descartados = fact_extractor.extraer("estoy en once", {}, session_id="s")

    assert validos == {"ocupacion": "high_school"}
    assert descartados == []


def test_valor_fuera_del_vocabulario_no_se_escribe(monkeypatch):
    """El caso que rompería `seed_answers_from_onboarding` si pasara."""
    _patch_sdk(monkeypatch, _respuesta_tool([
        {"id": "inversion", "valor": "como veinte lucas", "confianza": "alta"},
    ]))

    validos, descartados = fact_extractor.extraer("veinte lucas", {}, session_id="s")

    assert "inversion" not in validos
    assert "inversion" in descartados


def test_confianza_baja_no_se_persiste(monkeypatch):
    _patch_sdk(monkeypatch, _respuesta_tool([
        {"id": "pasaporte", "valor": "yes", "confianza": "baja"},
    ]))

    validos, descartados = fact_extractor.extraer("creo que sí", {}, session_id="s")

    assert validos == {}
    assert descartados == ["pasaporte"]


def test_acepta_la_etiqueta_y_la_normaliza_a_codigo(monkeypatch):
    """El modelo a veces devuelve la etiqueta que leyó en el catálogo."""
    _patch_sdk(monkeypatch, _respuesta_tool([
        {"id": "pasaporte", "valor": "Sí, vigente", "confianza": "alta"},
    ]))

    validos, _ = fact_extractor.extraer("tengo pasaporte", {}, session_id="s")

    assert validos == {"pasaporte": "yes"}


def test_multi_deduplica_conservando_orden(monkeypatch):
    _patch_sdk(monkeypatch, _respuesta_tool([
        {"id": "destino_interes", "valores": ["canada", "Canadá", "usa"], "confianza": "alta"},
    ]))

    validos, _ = fact_extractor.extraer("Canadá o Estados Unidos", {}, session_id="s")

    assert validos == {"destino_interes": ["canada", "usa"]}


def test_si_la_ia_falla_no_se_inventa_nada(monkeypatch):
    _patch_sdk(monkeypatch, RuntimeError("boom"))

    validos, descartados = fact_extractor.extraer("lo que sea", {}, session_id="s")

    assert validos == {}
    assert descartados == []


def test_id_desconocido_se_descarta(monkeypatch):
    """El enum del schema lo hace improbable, pero no imposible."""
    _patch_sdk(monkeypatch, _respuesta_tool([
        {"id": "campo_inventado", "valor": "x", "confianza": "alta"},
    ]))

    validos, descartados = fact_extractor.extraer("hola", {}, session_id="s")

    assert validos == {}
    assert descartados == ["campo_inventado"]


def test_el_schema_del_tool_es_estable_entre_turnos():
    """No debe depender de qué falta · si cambia, invalida la caché del prompt.

    Las definiciones de tools se renderizan en la posición 0. Acotar el enum a
    los hechos pendientes «para guiar al modelo» haría que cambiara en cada
    turno y que nada de lo que va después se cachee nunca.
    """
    vacio = fact_extractor._tool_schema()
    con_datos = fact_extractor._tool_schema()

    assert vacio == con_datos
    ids = vacio["properties"]["hechos"]["items"]["properties"]["id"]["enum"]
    assert set(ids) == {h.id for h in catalogo.HECHOS}


# ---------------------------------------------------------------------------
# 3 · EL CONTRATO · lo que impide que el bot rompa el resto de la plataforma
# ---------------------------------------------------------------------------


def test_contrato_con_el_seeding_del_journey():
    """Los hechos del bot tienen que hablar el idioma de la plataforma.

    `journey_service.seed_answers_from_onboarding` traduce `onboarding_answers`
    a las respuestas del journey. Si el bot escribe una clave que esa función no
    conoce, el journey vuelve a preguntar lo mismo — que es la queja S9 de
    Sandra, y el bot la reintroduciría en vez de arreglarla.
    """
    from app.services.journey_service import seed_answers_from_onboarding

    recolectado = {
        "ocupacion": "high_school",
        "cuando_viajar": "asap",
        "inversion": "15k_30k",
        "destino_interes": ["canada"],
        "pasaporte": "yes",
        "ciudad": "Medellín",
        "que_estudiar": "diseño",
        "modalidad": "in_person",
    }
    onboarding = catalogo.mapa_a_onboarding(recolectado)

    # Las claves son las que la plataforma ya usa.
    assert onboarding["life_stage"] == "high_school"
    assert onboarding["timeline"] == "asap"
    assert onboarding["budget"] == "15k_30k"
    assert onboarding["passport"] == "yes"
    assert onboarding["city"] == "Medellín"

    # Y el seeding del journey las entiende de verdad · no solo "no explota".
    sembrado = seed_answers_from_onboarding(onboarding)
    assert sembrado["lifeStage"] == "Terminando el colegio"
    assert sembrado["timeHorizon"] == "En los próximos meses"
    assert sembrado["budgetBand"] == "Flexible"


def test_toda_opcion_mapeable_es_traducible_por_la_plataforma():
    """Barrido: ninguna opción del catálogo puede quedar huérfana.

    Recorre TODAS las opciones de los hechos que viajan al onboarding y verifica
    que los mapas de `journey_service` las traducen. Es el camino incómodo: un
    test que probara solo `high_school` pasaría con el resto roto.
    """
    from app.services.journey_service import (
        _ONBOARDING_BUDGET_TO_JOURNEY,
        _ONBOARDING_LIFE_STAGE_MAP,
        _ONBOARDING_TIMELINE_MAP,
    )

    mapas = {
        "life_stage": _ONBOARDING_LIFE_STAGE_MAP,
        "timeline": _ONBOARDING_TIMELINE_MAP,
        "budget": _ONBOARDING_BUDGET_TO_JOURNEY,
    }
    for hecho in catalogo.HECHOS:
        mapa = mapas.get(hecho.onboarding_key or "")
        if mapa is None or not hecho.opciones:
            continue
        for codigo in hecho.opciones:
            assert codigo in mapa, (
                f"`{hecho.id}` ofrece `{codigo}` pero {hecho.onboarding_key} no lo traduce"
            )


def test_city_ya_no_es_un_campo_fantasma():
    """`answers['city']` se leía en tres sitios sin que nada lo escribiera.

    A9 lo cerró desde la plataforma; el perfilador es la otra fuente. Si alguien
    le quita el `onboarding_key` a `ciudad`, el dossier del asesor vuelve a
    pintar un campo vacío.
    """
    assert catalogo.get_hecho("ciudad").onboarding_key == "city"
    assert catalogo.mapa_a_onboarding({"ciudad": "Cali"}) == {"city": "Cali"}


def test_no_se_deriva_main_goal_ni_birthdate():
    """Dos omisiones deliberadas · ver `mapa_a_onboarding`.

    `main_goal` forzado desde `tipo_experiencia` registraría que la persona
    eligió algo que no eligió; `birthdate` desde una edad declarada da ±1 año en
    el campo que alimenta el gate de menores.
    """
    salida = catalogo.mapa_a_onboarding({"tipo_experiencia": "pregrado", "edad": 17})

    assert "main_goal" not in salida
    assert "birthdate" not in salida


# ---------------------------------------------------------------------------
# 4 · Scoring · los arquetipos que describió la clienta
# ---------------------------------------------------------------------------


def test_arquetipo_que_califica_va_al_asesor():
    veredicto = bot_lead_scoring.evaluar({
        "inversion": "15k_30k", "cuando_viajar": "asap",
        "destino_interes": ["canada"], "pasaporte": "yes",
        "tipo_experiencia": "pregrado", "nivel_ingles": "intermedio",
    })

    assert veredicto.ruta == "asesor"
    assert veredicto.banda == "hot"
    assert veredicto.alarmas == []


def test_mil_dolares_se_descarta_aunque_el_score_sea_alto():
    """Verónica (12:03): "no, mil dólares → de una que ha muerto".

    El presupuesto inviable manda sobre el promedio ponderado. Sin esta regla el
    lead sale `warm` y el equipo pierde una llamada.
    """
    veredicto = bot_lead_scoring.evaluar({
        "inversion": "under_5k", "cuando_viajar": "asap",
        "destino_interes": ["usa"], "pasaporte": "yes",
        "tipo_experiencia": "pregrado",
    })

    assert veredicto.ruta == "descartar"
    assert veredicto.score >= 40  # el score NO es el que lo descarta
    assert any("Presupuesto" in a for a in veredicto.alarmas)


def test_visa_negada_alerta_pero_no_mata():
    """Ella dijo "me prende una alarma", no "lo descarto"."""
    veredicto = bot_lead_scoring.evaluar({
        "inversion": "15k_30k", "cuando_viajar": "asap",
        "destino_interes": ["usa"], "pasaporte": "yes",
        "tipo_experiencia": "pregrado", "nivel_ingles": "intermedio",
        "visa_usa_negada": True,
    })

    assert veredicto.ruta == "asesor"
    assert any("visa" in a.lower() for a in veredicto.alarmas)


def test_explorando_sin_datos_es_frio():
    veredicto = bot_lead_scoring.evaluar({
        "cuando_viajar": "exploring", "pasaporte": "no",
    })

    assert veredicto.ruta == "descartar"
    assert veredicto.banda == "cold"


def test_la_miga_de_pan_detecta_al_lead_de_grasshopper():
    assert bot_lead_scoring.quiere_orientacion({"tipo_experiencia": "orientacion"})
    assert not bot_lead_scoring.quiere_orientacion({"tipo_experiencia": "pregrado"})


def test_cada_punto_del_score_deja_su_motivo():
    """El equipo comercial va a discutir el criterio, no el número."""
    veredicto = bot_lead_scoring.evaluar({
        "inversion": "15k_30k", "pasaporte": "yes",
    })

    assert any("presupuesto" in m for m in veredicto.motivos)
    assert any("pasaporte" in m for m in veredicto.motivos)


# ---------------------------------------------------------------------------
# 5 · El motor
# ---------------------------------------------------------------------------


def test_prioriza_los_obligatorios():
    pendientes = conversation_engine._faltantes_priorizados({})
    obligatorios = set(catalogo.ids_obligatorios())

    primeros = pendientes[: len(obligatorios)]
    assert set(primeros) == obligatorios


def test_no_le_muestra_al_modelo_los_25_hechos_de_una():
    """Mostrárselos todos lo empuja a encadenar preguntas · la queja de fondo.

    El tope se compara contra un número **fijo**, no contra
    `MAX_FALTANTES_VISIBLES`: la primera versión de este test usaba la constante
    y por eso seguía pasando aunque alguien la subiera a 99. Un test que se mide
    contra la variable que debería vigilar no vigila nada.
    """
    pendientes = conversation_engine._faltantes_priorizados({})
    bloque = conversation_engine._bloque_faltantes(pendientes)
    lineas = [l for l in bloque.splitlines() if l.startswith("- ")]

    assert len(pendientes) >= 20, "el catálogo debería tener muchos hechos pendientes"
    assert len(lineas) <= 6, f"al modelo le llegaron {len(lineas)} preguntas de una"


def test_no_insiste_con_la_pregunta_que_no_respondieron():
    """Regresión de un defecto encontrado conversando con el modelo real.

    En la primera corrida en vivo el bot preguntó por el pasaporte **tres turnos
    seguidos** mientras la persona le daba destino, presupuesto y tipo de
    programa. Pedirlo en el prompt mejoró el tono pero no lo evitó; el freno
    tiene que estar en el motor.
    """
    mismos = ["pasaporte", "tipo_experiencia", "destino_interes"]

    rotado = conversation_engine._rotar_si_no_respondieron(mismos, list(mismos))

    assert rotado[0] != "pasaporte", "volvió a encabezar con lo que ya preguntó"
    assert "pasaporte" in rotado, "no se pierde · se retoma más adelante"


def test_si_respondieron_no_rota():
    """Rotar siempre sería igual de malo: perdería la prioridad del catálogo."""
    antes = ["nombre", "correo", "celular"]
    ahora = ["correo", "celular"]  # dio el nombre

    assert conversation_engine._rotar_si_no_respondieron(antes, ahora)[0] == "correo"


def test_no_rota_en_el_primer_turno():
    """Sin historial no hubo pregunta previa · nada que rotar."""
    ahora = ["nombre", "correo"]

    assert conversation_engine._rotar_si_no_respondieron([], ahora) == ahora


def test_si_falla_la_respuesta_no_se_pierden_los_hechos(monkeypatch):
    """La persona ya dijo lo que dijo · perderlo la obliga a repetirse."""
    monkeypatch.setattr(
        conversation_engine, "extraer",
        lambda *a, **k: ({"nombre": "Ana"}, []),
    )
    monkeypatch.setattr(
        conversation_engine, "call_claude_chat",
        lambda *a, **k: (None, {"error_kind": "api_error", "model": "m"}),
    )

    respuesta, hechos, _ = conversation_engine.responder(
        "soy Ana", [], {}, session_id="s",
    )

    assert hechos == {"nombre": "Ana"}
    assert respuesta == conversation_engine.MENSAJE_FALLBACK


def test_las_correcciones_pisan_lo_extraido(monkeypatch):
    """El momento de confirmación es la red de la extracción · tiene que pisar."""
    monkeypatch.setattr(
        conversation_engine, "extraer",
        lambda *a, **k: ({"inversion": "over_30k"}, []),
    )
    monkeypatch.setattr(
        conversation_engine, "call_claude_chat",
        lambda *a, **k: ("listo", {"model": "m"}),
    )

    _, hechos, _ = conversation_engine.responder(
        "no, en realidad son más de 30 mil", [], {"inversion": "under_5k"}, session_id="s",
    )

    assert hechos["inversion"] == "over_30k"


def test_el_cierre_no_lo_decide_el_modelo():
    """Si dependiera de que el modelo lo declare, cerraría sin correo ni celular."""
    casi = {h: "x" for h in catalogo.ids_obligatorios() if h != "correo"}

    assert not conversation_engine.listo_para_cerrar(casi)
    assert conversation_engine.listo_para_cerrar({**casi, "correo": "a@b.co"})
