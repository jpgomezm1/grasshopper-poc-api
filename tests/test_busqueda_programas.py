"""La búsqueda de programas · filtro duro + semántica + RIASEC.

Lo que se protege aquí es el **orden de las tres capas**. La tentación con una
base vectorial es dejar que el coseno decida todo; si eso pasara, el sistema
devolvería programas que el estudiante no puede cursar porque su descripción se
parece a lo que pidió. Los 34 lotes de extracción existieron en buena parte para
detectar exactamente eso (programas que dicen "no aceptamos internacionales",
niveles que exigen un título que la persona no tiene).

El embedding se mockea en la **frontera** (`embeddings.embeber_uno`), no en la
función que se está probando — `backend/CLAUDE.md`, el segundo error que más se
repite en este repo.
"""
from __future__ import annotations

import pytest

from app.services import busqueda_programas as bp


# ---------------------------------------------------------------------------
# Las condiciones duras · lo que NO puede salir nunca
# ---------------------------------------------------------------------------


def test_a_quien_esta_en_el_colegio_no_se_le_ofrece_una_maestria():
    """El filtro por etapa es SQL, no similitud · es un hecho, no un parecido."""
    sql, params = bp._where(bp.Filtros(etapa_de_vida="high_school"))

    assert "NOT (nivel = ANY(:fuera))" in sql
    assert "maestria" in params["fuera"]
    assert "doctorado" in params["fuera"]


def test_la_etapa_ya_normalizada_filtra_igual_que_la_cruda():
    """`etapa_de_vida` llega de dos sitios (onboarding y journey) y uno de ellos
    la entrega ya normalizada. Cuando `normalizar_etapa` no reconocía sus propios
    valores, esta rama devolvía "sin restricciones" y reaparecían los posgrados."""
    crudo, _ = bp._where(bp.Filtros(etapa_de_vida="high_school"))
    canonico, params = bp._where(bp.Filtros(etapa_de_vida="terminando_colegio"))

    assert crudo == canonico
    assert "maestria" in params["fuera"]


def test_sin_etapa_no_se_esconde_nada():
    """De quien no sabemos en qué punto está, no se asume: "en transición / no
    seguro" es justo la persona de la que no sabemos si tiene título."""
    sql, params = bp._where(bp.Filtros())

    assert "fuera" not in params
    assert sql == "activo = true"


def test_el_filtro_por_pais_deja_pasar_las_redes_multi_destino():
    """`Varios destinos` son redes que operan en muchos países y cuyo programa no
    dice en cuál. Excluirlas escondería oferta real; afirmar que están en el país
    pedido sería inventar. Entran marcadas y el asesor confirma."""
    sql, params = bp._where(bp.Filtros(paises=["Canadá"]))

    assert "Varios destinos" in sql
    assert params["paises"] == ["Canadá"]


def test_el_nivel_explicito_manda_sobre_la_etapa():
    """Un asesor filtrando por 'maestria' quiere ver maestrías, aunque el
    estudiante esté en el colegio · el panel de la agencia lo necesita."""
    sql, params = bp._where(
        bp.Filtros(niveles=["maestria"], etapa_de_vida="high_school")
    )

    assert params["niveles"] == ["maestria"]
    assert "fuera" not in params


# ---------------------------------------------------------------------------
# El puntaje · cómo se combinan las capas
# ---------------------------------------------------------------------------


class _FilaFalsa(dict):
    """Lo que devolvería Postgres · `buscar` sólo lee por clave."""


def _db_que_devuelve(filas):
    class _Res:
        def mappings(self):
            class _M:
                def all(_self):
                    return filas
            return _M()

    class _DB:
        def execute(self, *a, **k):
            return _Res()

    return _DB()


def _fila(nombre, area, sim):
    return _FilaFalsa(
        id="11111111-1111-1111-1111-111111111111", nombre=nombre,
        institucion="X", pais="Canadá", ciudad=None, nivel="bachelor",
        area=area, duracion=None, codigo_oficial=None, url_fuente=None, sim=sim,
    )


def test_la_afinidad_reordena_pero_no_rescata_lo_ajeno():
    """El refuerzo RIASEC pesa 0.25: puede mover a un programa parecido, no subir
    uno que no tiene nada que ver con lo que la persona pidió."""
    filas = [
        _fila("Muy parecido pero de otra área", "Belleza y Estética", 0.90),
        _fila("Algo parecido y del área afín", "Salud y Medicina", 0.80),
        _fila("Nada que ver, área afín", "Salud y Medicina", 0.10),
    ]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4,
                  codigos_riasec=["I", "S"], limite=10)

    # El del área afín adelanta al de otra área pese a menor similitud…
    assert r[0].area == "Salud y Medicina"
    assert r[0].similitud == 0.80
    # …pero el irrelevante sigue último: la afinidad no lo rescata.
    assert r[-1].similitud == 0.10


def test_sin_test_vocacional_manda_solo_la_similitud():
    """Quien no ha hecho el test no recibe un orden inventado."""
    filas = [
        _fila("A", "Salud y Medicina", 0.50),
        _fila("B", "Belleza y Estética", 0.60),
    ]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4,
                  codigos_riasec=[], limite=10)

    assert [x.nombre for x in r] == ["B", "A"]
    assert all(x.afinidad == 0.0 for x in r)


def test_sin_vector_la_busqueda_sigue_devolviendo_programas():
    """Que el proveedor de embeddings esté caído no puede dejar a un estudiante
    sin catálogo · el mismo criterio que rige el resto del producto."""
    filas = [_fila("A", "Salud y Medicina", 0.0)]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=None,
                  codigos_riasec=["I"], limite=10)

    assert len(r) == 1
    assert r[0].similitud == 0.0


def test_el_resultado_dice_por_que_salio():
    """Sin similitud y afinidad separadas, nadie puede depurar una mala
    recomendación ni explicarle a un asesor de dónde salió."""
    filas = [_fila("A", "Salud y Medicina", 0.42)]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4,
                  codigos_riasec=["I", "S"], limite=1)[0]

    assert r.similitud == 0.42
    assert r.afinidad > 0
    assert r.puntaje == pytest.approx(0.42 + bp.PESO_AFINIDAD * r.afinidad, abs=1e-3)


def test_se_piden_mas_candidatos_de_los_que_se_muestran():
    """Si se pidieran justo los que se muestran, reordenar por afinidad no
    cambiaría nada: ya vendrían recortados por similitud."""
    assert bp.CANDIDATOS > 20


# ---------------------------------------------------------------------------
# El perfil del estudiante
# ---------------------------------------------------------------------------


def test_un_perfil_a_medio_hacer_no_revienta_la_busqueda():
    """`ConsolidatedProfile` exige 200+ caracteres de narrativa y tres
    fortalezas. Reconstruirlo aquí haría que un perfil incompleto tumbe la
    búsqueda entera por validación, cuando sólo hacen falta cuatro campos."""
    class _Fila:
        profile_data = {"holland_codes": [{"code": "I"}], "interests": ["Diseño"]}

    class _Q:
        def filter(self, *a):
            return self

        def first(self):
            return _Fila()

    class _DB:
        def query(self, *a):
            return _Q()

    class _User:
        id = "u1"
        onboarding_answers = None

    p = bp.perfil_del_usuario(_DB(), _User())

    assert p.codigos_riasec == ["I"]
    assert p.intereses == ["Diseño"]
    assert p.hizo_el_test is True


def test_sin_perfil_guardado_se_puede_buscar_igual():
    class _Q:
        def filter(self, *a):
            return self

        def first(self):
            return None

    class _DB:
        def query(self, *a):
            return _Q()

    class _User:
        id = "u1"
        onboarding_answers = None

    p = bp.perfil_del_usuario(_DB(), _User())

    assert p.codigos_riasec == []
    assert p.hizo_el_test is False
