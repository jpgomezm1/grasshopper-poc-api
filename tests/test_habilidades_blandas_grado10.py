"""Mapeo de Habilidades Blandas · ruta grado 10.

Tres cosas se prueban aquí y las tres pueden romperse en silencio:

1. **Que no se presente como lo que no es.** Es un instrumento propio, sin norma
   ni validación. Si mañana alguien "mejora" el copy y escribe "test de liderazgo"
   o "tu nivel de resiliencia", el producto empieza a afirmar algo que no puede
   sostener frente a una familia. Hay tests de copy justamente por eso.

2. **El cálculo en sus bordes**: empates, empates a tres y respuestas
   incompletas. Son los casos que un banco de 9 retos y 3 opciones produce todo
   el tiempo, no rarezas.

3. **Que sólo aparezca para grado 10**, y por el camino real: el endpoint y el
   selector de banco, no la constante. Un `gradeRoutes` que nadie lee es
   exactamente el defecto de "campo que nadie lee" del CLAUDE.md.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.data.disclaimer import DISCLAIMER_VERSION
from app.data.habilidades_blandas import (
    EQUIPO,
    GRADO_OBJETIVO,
    HABILIDAD_INFO,
    HABILIDADES_ORDEN,
    LIDERAZGO,
    RESILIENCIA,
    TEST_HABILIDADES_BLANDAS,
)
from app.data.vocational_tests import (
    calculate_vocational_scores,
    disponible_para_grado,
    get_all_tests_summary,
    get_test_by_id,
)
from app.services import pdf_service, test_interpretation_service, vocational_bank_selector
from app.services.habilidades_blandas_service import (
    MINIMO_RETOS_PARA_LEER,
    PERFIL_DEFINIDO,
    PERFIL_INSUFICIENTE,
    PERFIL_MIXTO,
    PERFIL_PAREJO,
    TEST_ID,
    calcular_habilidades_blandas,
)
from app.services.scoring_service import derive_test_extras

RETOS = TEST_HABILIDADES_BLANDAS["questions"]
IDS_RETOS = [q["id"] for q in RETOS]


def _respuestas(*por_habilidad: str) -> dict:
    """Reparte las elecciones sobre los retos en orden.

    `_respuestas(LIDERAZGO, LIDERAZGO, EQUIPO)` = respondió los tres primeros
    retos eligiendo liderazgo, liderazgo y trabajo en equipo. Los demás quedan
    sin responder.
    """
    return {rid: hab for rid, hab in zip(IDS_RETOS, por_habilidad)}


def _n(**conteos: int) -> dict:
    """Respuestas con N elecciones de cada habilidad (sin importar en qué reto)."""
    secuencia = []
    for codigo, veces in conteos.items():
        secuencia.extend([codigo] * veces)
    assert len(secuencia) <= len(RETOS), "no caben más elecciones que retos"
    return _respuestas(*secuencia)


# ---------------------------------------------------------------------------
# El banco
# ---------------------------------------------------------------------------


def test_el_banco_esta_bien_formado():
    test = get_test_by_id(TEST_ID)
    assert test is not None
    assert len(RETOS) == test["questionCount"] == 9
    assert len(set(IDS_RETOS)) == len(IDS_RETOS), "ids de reto duplicados"
    for reto in RETOS:
        assert reto["type"] == "forced_choice"
        opciones = reto["options"]
        assert {o["value"] for o in opciones} == set(HABILIDADES_ORDEN)
        assert len(opciones) == 3
        assert reto["text"].strip().endswith("?"), "el reto tiene que preguntar algo"
        for o in opciones:
            assert o["label"].strip()


def test_cada_habilidad_aparece_una_vez_por_reto():
    """La medida es ipsativa: si una habilidad tuviera más opciones que otra,
    saldría más elegida por construcción y el resultado no querría decir nada."""
    for codigo in HABILIDADES_ORDEN:
        veces = sum(
            1 for r in RETOS for o in r["options"] if o["value"] == codigo
        )
        assert veces == len(RETOS)


def test_el_orden_de_las_opciones_rota():
    """Si liderazgo fuera siempre la primera opción, a los tres retos el
    estudiante estaría eligiendo la posición, no la respuesta."""
    primeras = [r["options"][0]["value"] for r in RETOS]
    assert len(set(primeras)) == 3, "la primera opción no rota entre habilidades"
    for codigo in HABILIDADES_ORDEN:
        assert primeras.count(codigo) == 3, "el sesgo de posición quedó desbalanceado"


# ---------------------------------------------------------------------------
# El copy · no puede prometer lo que no es
# ---------------------------------------------------------------------------


def test_no_se_presenta_como_un_test_psicometrico():
    base = TEST_HABILIDADES_BLANDAS["academicBasis"].lower()
    assert "no es un test psicométrico" in base
    assert "no tiene norma poblacional" in base
    # Se llama mapeo, no test ni evaluación ni prueba.
    assert "mapeo" in TEST_HABILIDADES_BLANDAS["name"].lower()
    for campo in ("name", "shortName"):
        texto = TEST_HABILIDADES_BLANDAS[campo].lower()
        assert "test" not in texto and "evaluación" not in texto


@pytest.mark.parametrize(
    "respuestas",
    [
        _n(**{LIDERAZGO: 5, RESILIENCIA: 2, EQUIPO: 2}),   # definido
        _n(**{LIDERAZGO: 4, RESILIENCIA: 4, EQUIPO: 1}),   # mixto
        _n(**{LIDERAZGO: 3, RESILIENCIA: 3, EQUIPO: 3}),   # parejo
        _n(**{LIDERAZGO: 2}),                              # insuficiente
    ],
)
def test_ninguna_lectura_suena_a_diagnostico(respuestas):
    r = calcular_habilidades_blandas(respuestas)
    texto = f"{r['label']} {r['headline']}".lower()
    for prohibida in (
        "diagnóstic",
        "trastorno",
        "puntaje",
        "percentil",
        "nota de",
        "nivel alto",
        "nivel bajo",
        "eres un ",
        "eres una ",
        "déficit",
        "carece",
    ):
        assert prohibida not in texto, f"'{prohibida}' en la lectura: {texto}"


def test_la_lectura_se_declara_tendencia_y_no_etiqueta():
    definido = calcular_habilidades_blandas(
        _n(**{LIDERAZGO: 5, RESILIENCIA: 2, EQUIPO: 2})
    )
    assert "tendencia" in definido["headline"].lower()
    assert "no una etiqueta" in definido["headline"].lower()
    assert "no es un test psicométrico" in definido["nota"].lower()


def test_el_perfil_parejo_no_se_lee_como_debilidad():
    """Ipsativo: elegir poco una opción no es no tener la habilidad. Si esto se
    pierde, un chico parejo sale del mapeo creyendo que está flojo en las tres."""
    r = calcular_habilidades_blandas(_n(**{LIDERAZGO: 3, RESILIENCIA: 3, EQUIPO: 3}))
    assert r["perfil"] == PERFIL_PAREJO
    assert "flojo" in r["headline"].lower()
    assert "no quiere decir" in r["headline"].lower()


# ---------------------------------------------------------------------------
# El cálculo
# ---------------------------------------------------------------------------


def test_tendencia_definida_cuando_una_se_despega():
    r = calcular_habilidades_blandas(_n(**{LIDERAZGO: 5, RESILIENCIA: 2, EQUIPO: 2}))
    assert r["perfil"] == PERFIL_DEFINIDO
    assert r["tendencias"] == [LIDERAZGO]
    assert r["label"] == HABILIDAD_INFO[LIDERAZGO]["name"]
    assert r["counts"] == {LIDERAZGO: 5, RESILIENCIA: 2, EQUIPO: 2}
    assert r["completo"] is True


def test_empate_exacto_nombra_las_dos():
    r = calcular_habilidades_blandas(_n(**{LIDERAZGO: 4, RESILIENCIA: 4, EQUIPO: 1}))
    assert r["perfil"] == PERFIL_MIXTO
    assert r["tendencias"] == [LIDERAZGO, RESILIENCIA]
    assert r["label"] == "Liderazgo y resiliencia"


def test_diferencia_de_un_reto_tambien_es_empate():
    """4-3-2: la de 3 entra (difiere en 1), la de 2 no. Una sola elección de
    diferencia sobre 9 retos no distingue a nadie."""
    r = calcular_habilidades_blandas(_n(**{LIDERAZGO: 4, RESILIENCIA: 3, EQUIPO: 2}))
    assert r["perfil"] == PERFIL_MIXTO
    assert r["tendencias"] == [LIDERAZGO, RESILIENCIA]
    assert EQUIPO not in r["tendencias"]


def test_empate_a_tres_por_margen_es_perfil_parejo():
    """3-3-2 (con un reto sin responder): la de 2 difiere en 1, así que entran
    las tres. No hay dominante que nombrar."""
    r = calcular_habilidades_blandas(_n(**{LIDERAZGO: 3, RESILIENCIA: 3, EQUIPO: 2}))
    assert r["perfil"] == PERFIL_PAREJO
    assert r["tendencias"] == HABILIDADES_ORDEN


def test_desempate_es_determinista_y_no_depende_del_orden_de_las_respuestas():
    """Mismos conteos, respuestas escritas en otro orden → mismo resultado."""
    a = calcular_habilidades_blandas(
        _respuestas(LIDERAZGO, LIDERAZGO, LIDERAZGO, LIDERAZGO,
                    RESILIENCIA, RESILIENCIA, RESILIENCIA, RESILIENCIA, EQUIPO)
    )
    b = calcular_habilidades_blandas(
        _respuestas(RESILIENCIA, LIDERAZGO, RESILIENCIA, LIDERAZGO,
                    EQUIPO, RESILIENCIA, LIDERAZGO, RESILIENCIA, LIDERAZGO)
    )
    assert a["tendencias"] == b["tendencias"] == [LIDERAZGO, RESILIENCIA]
    assert a["label"] == b["label"]


# --- respuestas incompletas -------------------------------------------------


def test_pocas_respuestas_no_producen_tendencia():
    r = calcular_habilidades_blandas(_n(**{LIDERAZGO: 4}))
    assert r["perfil"] == PERFIL_INSUFICIENTE
    assert r["tendencias"] == []
    assert r["skill_info"] == []
    assert "4 de 9" in r["headline"]
    assert r["label"] == "Mapeo incompleto"


def test_sin_respuestas_no_revienta():
    for vacio in ({}, None):
        r = calcular_habilidades_blandas(vacio)
        assert r["perfil"] == PERFIL_INSUFICIENTE
        assert r["respondidas"] == 0
        assert r["counts"] == {h: 0 for h in HABILIDADES_ORDEN}


def test_en_el_minimo_ya_se_lee_pero_se_avisa_que_es_parcial():
    respuestas = _n(**{LIDERAZGO: 4, EQUIPO: 1})
    assert len(respuestas) == MINIMO_RETOS_PARA_LEER
    r = calcular_habilidades_blandas(respuestas)
    assert r["perfil"] == PERFIL_DEFINIDO
    assert r["completo"] is False
    assert "parcial" in r["headline"].lower()
    assert "5 de 9" in r["headline"]


def test_respuestas_invalidas_no_cuentan_como_respondidas():
    """Un código que no existe, un reto que no existe y un None. Si contaran,
    un envío con basura se leería como un mapeo completo."""
    r = calcular_habilidades_blandas(
        {
            IDS_RETOS[0]: LIDERAZGO,
            IDS_RETOS[1]: "XXX",
            IDS_RETOS[2]: None,
            "hb-999": EQUIPO,
            IDS_RETOS[3]: 3,  # valor de escala Likert enviado por error
        }
    )
    assert r["respondidas"] == 1
    assert r["counts"] == {LIDERAZGO: 1, RESILIENCIA: 0, EQUIPO: 0}
    assert r["perfil"] == PERFIL_INSUFICIENTE


# ---------------------------------------------------------------------------
# Integración con el motor que ya existe
# ---------------------------------------------------------------------------


def test_derive_test_extras_lo_reconoce():
    """El endpoint de submit no llama al servicio directo: pasa por aquí."""
    extras = derive_test_extras(TEST_ID, _n(**{EQUIPO: 6, LIDERAZGO: 2, RESILIENCIA: 1}))
    assert extras is not None
    assert extras["kind"] == TEST_ID
    assert extras["tendencias"] == [EQUIPO]
    assert extras["skill_info"][0]["name"] == "Trabajo en equipo"
    assert extras["skill_info"][0]["description"] and extras["skill_info"][0]["tip"]


def test_los_porcentajes_son_conteo_sobre_los_nueve_retos():
    """Camino genérico `forced_choice`, el mismo de VARK: el front pinta barras
    con esto. 3 de 9 = 33%, y lo que no se respondió no infla a nadie."""
    scores = calculate_vocational_scores(
        TEST_ID, _n(**{LIDERAZGO: 3, RESILIENCIA: 3, EQUIPO: 3})
    )
    assert scores == {LIDERAZGO: 33, RESILIENCIA: 33, EQUIPO: 33}
    parcial = calculate_vocational_scores(TEST_ID, _n(**{LIDERAZGO: 3}))
    assert parcial[LIDERAZGO] == 33 and sum(parcial.values()) == 33


def test_el_pdf_de_la_familia_imprime_palabras_y_no_siglas():
    scores = calculate_vocational_scores(TEST_ID, _n(**{LIDERAZGO: 5, EQUIPO: 4}))
    scores["_extras"] = derive_test_extras(TEST_ID, _n(**{LIDERAZGO: 5, EQUIPO: 4}))
    assert TEST_ID in pdf_service._TEST_LABELS
    destacado = pdf_service._highlight_for(TEST_ID, scores)
    assert destacado == "Liderazgo y trabajo en equipo"


def test_a_la_ia_le_llega_la_restriccion_junto_con_el_dato():
    """Si al modelo sólo le llegaran los porcentajes escribiría "eres un líder
    nato", que es la afirmación que este instrumento no puede sostener."""
    respuestas = _n(**{LIDERAZGO: 6, RESILIENCIA: 2, EQUIPO: 1})
    scores = calculate_vocational_scores(TEST_ID, respuestas)
    scores["_extras"] = derive_test_extras(TEST_ID, respuestas)

    bloque = test_interpretation_service.format_scores_block(TEST_ID, scores)
    assert "RESULTADO: Liderazgo" in bloque
    assert "NO es un test psicométrico" in bloque
    assert "TENDENCIAS" in bloque
    # Y las siglas no se le pasan crudas al modelo.
    assert "Liderazgo" in bloque and "LID" not in bloque


def test_a_la_ia_se_le_prohibe_inventar_una_dominante_en_perfil_parejo():
    respuestas = _n(**{LIDERAZGO: 3, RESILIENCIA: 3, EQUIPO: 3})
    scores = calculate_vocational_scores(TEST_ID, respuestas)
    scores["_extras"] = derive_test_extras(TEST_ID, respuestas)
    bloque = test_interpretation_service.format_scores_block(TEST_ID, scores)
    assert "no hay una dominante" in bloque.lower()
    assert "no inventes una" in bloque.lower()


def test_a_la_ia_se_le_dice_que_el_mapeo_quedo_incompleto():
    respuestas = _n(**{LIDERAZGO: 2})
    scores = calculate_vocational_scores(TEST_ID, respuestas)
    scores["_extras"] = derive_test_extras(TEST_ID, respuestas)
    bloque = test_interpretation_service.format_scores_block(TEST_ID, scores)
    assert "no nombres una tendencia" in bloque.lower()


# ---------------------------------------------------------------------------
# Sólo para la ruta de grado 10
# ---------------------------------------------------------------------------


def test_el_test_declara_su_ruta():
    assert TEST_HABILIDADES_BLANDAS["gradeRoutes"] == [10] == [GRADO_OBJETIVO]


@pytest.mark.parametrize(
    "grado,visible",
    [(10, True), ("10", True), (9, False), (11, False), (12, False), (None, False)],
)
def test_el_catalogo_solo_lo_ofrece_en_grado_10(grado, visible):
    ids = {t["id"] for t in get_all_tests_summary(grade=grado)}
    assert (TEST_ID in ids) is visible
    # Los ocho tests que ya existían no cambian para nadie.
    assert {"holland", "bigfive", "vark", "motivadores"} <= ids


def test_sin_grado_el_catalogo_es_el_de_siempre():
    """`get_all_tests_summary()` sin argumentos es el contrato viejo: ocho tests."""
    ids = {t["id"] for t in get_all_tests_summary()}
    assert TEST_ID not in ids
    assert len(ids) == 8


def test_los_tests_sin_ruta_declarada_son_de_todas_las_rutas():
    holland = get_test_by_id("holland")
    assert "gradeRoutes" not in holland
    for grado in (9, 10, 11, 12, None):
        assert disponible_para_grado(holland, grado) is True


def _usuario(**kwargs):
    base = dict(
        id="u-1",
        grade=None,
        onboarding_answers={},
        test_disclaimers={
            TEST_ID: {"accepted_at": "hoy", "version": DISCLAIMER_VERSION}
        },
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "usuario,visible",
    [
        (_usuario(grade=10), True),
        (_usuario(grade=11), False),
        # Espejo en JSON: el chat de onboarding escribe los dos lados, y hay
        # usuarios viejos que sólo tienen este.
        (_usuario(onboarding_answers={"grade": "10"}), True),
        (_usuario(onboarding_answers={"grade": "9"}), False),
        # `high_school_early` es 9° O 10°: no alcanza para ofrecerlo.
        (_usuario(onboarding_answers={"life_stage": "high_school_early"}), False),
        (_usuario(), False),
    ],
)
def test_el_selector_de_banco_respeta_la_ruta(usuario, visible):
    """Por el camino real: es la función que llama `GET /vocational-tests`."""
    ids = {t["id"] for t in vocational_bank_selector.resumen_tests_para_usuario(usuario)}
    assert (TEST_ID in ids) is visible


# --- el endpoint ------------------------------------------------------------


class _FakeDB:
    """DB mínima: controla qué devuelve la consulta de resultado previo."""

    def __init__(self, resultado_previo=None):
        self._resultado = resultado_previo
        self.agregados = []
        self.commits = 0

    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._resultado

    def add(self, obj):
        self.agregados.append(obj)

    def commit(self):
        self.commits += 1


def test_el_endpoint_no_deja_contestarlo_desde_otra_ruta():
    """Filtrar sólo el listado no basta: la URL directa seguiría abierta."""
    from app.api.v1.vocational_tests import SubmitVocationalRequest, submit_test

    with pytest.raises(HTTPException) as ei:
        submit_test(
            TEST_ID,
            SubmitVocationalRequest(answers=_n(**{LIDERAZGO: 9})),
            current_user=_usuario(grade=11),
            db=_FakeDB(),
        )
    assert ei.value.status_code == 404


def test_el_endpoint_lo_acepta_en_grado_10_y_persiste_la_lectura():
    from app.api.v1.vocational_tests import SubmitVocationalRequest, submit_test

    db = _FakeDB()
    respuesta = submit_test(
        TEST_ID,
        SubmitVocationalRequest(answers=_n(**{EQUIPO: 6, LIDERAZGO: 2, RESILIENCIA: 1})),
        current_user=_usuario(grade=10),
        db=db,
    )
    assert respuesta["extras"]["tendencias"] == [EQUIPO]
    assert db.agregados, "no se guardó el resultado"
    guardado = db.agregados[0]
    assert guardado.test_id == TEST_ID
    assert guardado.scores["_extras"]["label"] == "Trabajo en equipo"


def test_quien_ya_lo_hizo_puede_repetirlo_aunque_haya_pasado_de_grado():
    """MEMORIA SÍ, LLAVE NO: no se le cierra la puerta a algo que ya hizo."""
    from app.api.v1.vocational_tests import SubmitVocationalRequest, submit_test

    previo = SimpleNamespace(answers={}, scores={})
    respuesta = submit_test(
        TEST_ID,
        SubmitVocationalRequest(answers=_n(**{LIDERAZGO: 9})),
        current_user=_usuario(grade=11),
        db=_FakeDB(resultado_previo=previo),
    )
    assert respuesta["test_id"] == TEST_ID
    assert previo.scores["_extras"]["tendencias"] == [LIDERAZGO]


def test_leer_el_resultado_viejo_nunca_se_bloquea_por_el_grado():
    """El estudiante pasa a 11° y su mapeo de 10° tiene que seguir abriéndose;
    si `GET /{id}` devolviera 404, la pantalla de resultados quedaría muerta."""
    assert (
        vocational_bank_selector.test_para_usuario(TEST_ID, _usuario(grade=11))
        is not None
    )
