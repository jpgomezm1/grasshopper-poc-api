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

    assert "NOT (pi.nivel = ANY(:fuera))" in sql
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
    assert sql == "pi.activo = true"


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


def _db_que_devuelve(filas, sin_vector=()):
    """Doble de la sesión · `buscar()` hace hasta DOS consultas, no una.

    La primera trae lo que tiene embedding, ordenado por parecido. La segunda
    —sólo si la primera no llenó el cupo— trae lo que **no** tiene embedding,
    para que un programa recién extraído no desaparezca del catálogo mientras
    espera su vector. Devolver `filas` en las dos llamadas duplicaría todo, que
    no es lo que hace la base.

    Se distingue por el SQL y no por el número de llamada porque con vector hay
    un `SET LOCAL ivfflat.probes` antes de la consulta real: contar llamadas deja
    el doble desfasado en cuanto alguien añada otro `execute`.
    """
    class _Res:
        def __init__(self, datos):
            self._datos = datos

        def mappings(self):
            datos = self._datos

            class _M:
                def all(_self):
                    return datos
            return _M()

    class _DB:
        def execute(self, sentencia, *a, **k):
            sql = str(sentencia)
            if "SET LOCAL" in sql:
                return _Res([])
            if "embedding IS NULL" in sql:
                return _Res(list(sin_vector))
            return _Res(filas)

    return _DB()


def _fila(nombre, area, sim, program_id=None, oferta_slug=None,
          confianza="publicado"):
    return _FilaFalsa(
        id="11111111-1111-1111-1111-111111111111", nombre=nombre,
        institucion="X", pais="Canadá", ciudad=None, nivel="bachelor",
        area=area, duracion=None, codigo_oficial=None, url_fuente=None,
        # El programa sabe de qué ficha del catálogo cuelga · es lo que conecta
        # los dos catálogos. `None` es un caso real: 708 programas son de
        # instituciones sin ficha y siguen siendo visibles.
        program_id=program_id, oferta_slug=oferta_slug, oferta_nombre=None,
        confianza=confianza,
        sim=sim,
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


# ---------------------------------------------------------------------------
# La relación con el catálogo autorizado · 2026-08-08
# ---------------------------------------------------------------------------
# Antes de esto había dos catálogos hablando de lo mismo sin saberse
# relacionados: el estudiante veía "Murdoch University" en las ofertas y
# "Bachelor of Veterinary Science · Murdoch University" en la búsqueda, sin nada
# que le dijera que son la misma institución.


def test_se_pueden_pedir_los_programas_de_UNA_ficha():
    """Es lo que usa la página de una institución para mostrar su oferta real."""
    sql, params = bp._where(bp.Filtros(program_id="abc-123"))

    assert "pi.program_id = CAST(:program_id AS uuid)" in sql
    assert params["program_id"] == "abc-123"


def test_el_program_id_se_castea_a_uuid():
    """La columna es UUID y el parámetro llega como texto. Sin el casteo,
    Postgres responde `operator does not exist: uuid = text`; y como la
    excepción se captura, el filtro fallaría en silencio devolviendo el catálogo
    entero en vez de los programas de esa institución. Ya pasó una vez."""
    sql, _ = bp._where(bp.Filtros(program_id="abc-123"))

    assert "CAST(:program_id AS uuid)" in sql


def test_las_condiciones_van_con_alias_de_tabla():
    """La consulta une `programas_investigados` con `programs`, y **las dos
    tienen una columna `area`**. Sin prefijo, Postgres responde "column
    reference is ambiguous" y la búsqueda entera revienta."""
    sql, _ = bp._where(bp.Filtros(areas=["Artes"], paises=["Canadá"]))

    assert "pi.area = ANY(:areas)" in sql
    assert "pi.pais = ANY(:paises)" in sql


def test_un_programa_sin_ficha_sigue_apareciendo():
    """708 programas son de instituciones que no tienen ficha en el catálogo del
    cliente (redes que se descompusieron en sus miembros). Un JOIN normal los
    habría borrado del catálogo sin que nada lo dijera."""
    filas = [_fila("Programa huérfano", "Artes", 0.5, program_id=None)]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4, limite=5)

    assert len(r) == 1
    assert r[0].program_id is None
    assert r[0].oferta_slug is None


def test_un_programa_enlazado_trae_como_llegar_a_su_institucion():
    """Con el id solo, el front sabría que hay una ficha pero no podría llegar a
    ella: la ruta del detalle es por slug."""
    filas = [_fila("Bachelor of X", "Ciencias", 0.5,
                   program_id="p-1", oferta_slug="murdoch-university")]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4, limite=5)[0]

    assert r.program_id == "p-1"
    assert r.oferta_slug == "murdoch-university"


def test_la_confianza_NO_entra_en_el_puntaje():
    """Se muestra, no se pondera · y la diferencia es deliberada.

    Bajar lo `indicativo` enterraría el 31% del catálogo por una corazonada, y
    hoy no hay forma de medir si eso mejora o empeora la recomendación (para eso
    está `scripts/evaluar_recomendaciones.py`, que todavía no tiene casos). Este
    test es el que se da cuenta si alguien la mete al ranking sin medirlo.
    """
    filas = [
        _fila("Flojo pero muy parecido", "Artes", 0.90, confianza="indicativo"),
        _fila("Verificable y menos parecido", "Artes", 0.80,
              confianza="verificable"),
    ]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4, limite=5)

    assert r[0].nombre == "Flojo pero muy parecido"
    assert r[0].confianza == "indicativo"


def test_la_confianza_llega_al_resultado():
    """Si no viaja, el estudiante no puede distinguir una fila confirmable de
    una reconstruida desde el slug de una URL."""
    filas = [_fila("X", "Artes", 0.5, confianza="verificable")]
    r = bp.buscar(_db_que_devuelve(filas), vector_perfil=[0.1] * 4, limite=1)[0]

    assert r.confianza == "verificable"


# ---------------------------------------------------------------------------
# Los programas sin embedding no desaparecen
# ---------------------------------------------------------------------------


def test_un_programa_sin_vector_sigue_apareciendo_para_quien_tiene_perfil():
    """El bug que este caso protege es de los que no se ven mirando la pantalla.

    La rama semántica exigía `pi.embedding IS NOT NULL`. Medido sobre el
    catálogo real de septiembre 2026 —33.907 programas activos y 5.086
    embebidos— eso significaba que **un estudiante que hizo el test veía el 14%
    del catálogo y uno que no hizo nada veía el 100%**. En Nueva Zelanda, con
    757 programas y 6 embebidos, el estudiante con perfil veía 6.

    Entre más señal daba la persona, más pequeño se le volvía el catálogo, y
    nada en la respuesta lo decía: `orden_semantico` seguía siendo `True`,
    porque el orden semántico sí funcionaba — sobre casi nada.
    """
    con_vector = [_fila("Tiene vector", "Salud y Medicina", 0.70)]
    sin_vector = [_fila("Recien extraido, sin vector", "Salud y Medicina", 0.0)]

    r = bp.buscar(_db_que_devuelve(con_vector, sin_vector=sin_vector),
                  vector_perfil=[0.1] * 4, codigos_riasec=[], limite=10)

    nombres = [x.nombre for x in r]
    assert "Recien extraido, sin vector" in nombres, (
        "un programa sin embedding no puede desaparecer del catálogo"
    )
    # Y va DETRÁS: lo que sí se pudo ordenar por parecido manda.
    assert nombres.index("Tiene vector") < nombres.index("Recien extraido, sin vector")


def test_lo_que_no_tiene_vector_no_se_pide_cuando_ya_hay_de_sobra():
    """El relleno es para cuando falta cupo, no un segundo viaje gratis.

    Si la consulta semántica ya trajo los candidatos que se pedían, ir a buscar
    los que no tienen vector sería una consulta de más en cada búsqueda.
    """
    llenos = [_fila(f"P{i}", "Artes", 0.5) for i in range(bp.CANDIDATOS)]
    sin_vector = [_fila("NO deberia pedirse", "Artes", 0.0)]

    r = bp.buscar(_db_que_devuelve(llenos, sin_vector=sin_vector),
                  vector_perfil=[0.1] * 4, codigos_riasec=[], limite=5)

    assert "NO deberia pedirse" not in [x.nombre for x in r]


def test_sin_vector_de_perfil_no_hay_segunda_consulta():
    """Sin vector, la primera consulta ya trae todo el conjunto elegible: no hay
    nada que rellenar y pedirlo duplicaría filas."""
    filas = [_fila("A", "Artes", 0.0)]
    sin_vector = [_fila("A", "Artes", 0.0)]

    r = bp.buscar(_db_que_devuelve(filas, sin_vector=sin_vector),
                  vector_perfil=None, codigos_riasec=[], limite=10)

    assert len(r) == 1


# ---------------------------------------------------------------------------
# Paginación · y lo que la pantalla puede prometer
# ---------------------------------------------------------------------------


def test_el_paginador_no_ofrece_paginas_vacias():
    """`total` y `total_paginas` responden preguntas distintas.

    En modo relevancia el orden sólo existe dentro de `VENTANA_RANKING`: más
    allá no hay nada ordenado que paginar. Calcular las páginas desde `total`
    daría un paginador con páginas que no devuelven nada — medido con un filtro
    real: 1.335 resultados, ventana de 500, 267 páginas ofrecidas y 167 vacías.

    `total` sigue siendo el número honesto y se reporta aparte: es lo que le
    dice al estudiante que afinar los filtros sirve para algo.
    """
    ventana = [_fila(f"P{i}", "Artes", 1.0 - i / 1000) for i in range(bp.VENTANA_RANKING)]

    class _DBGrande:
        def execute(self, sentencia, *a, **k):
            sql = str(sentencia)
            if "count(*)" in sql:
                class _R:
                    def scalar(_s):
                        return 1335
                return _R()
            return _db_que_devuelve(ventana).execute(sentencia, *a, **k)

    r = bp.buscar_pagina(_DBGrande(), vector_perfil=[0.1] * 4,
                         codigos_riasec=[], filtros=bp.Filtros(),
                         pagina=1, por_pagina=5)

    assert r["total"] == 1335, "el total real no se recorta"
    assert r["ranking_hasta"] == bp.VENTANA_RANKING
    assert r["total_paginas"] == bp.VENTANA_RANKING // 5, (
        "sólo se ofrecen las páginas que caben en la ventana ordenada"
    )


def test_sin_vector_se_pagina_el_conjunto_entero():
    """Sin orden semántico no hay ventana que respetar: el `ORDER BY` es estable
    y `LIMIT/OFFSET` alcanza todas las filas."""
    filas = [_fila(f"P{i}", "Artes", 0.0) for i in range(5)]

    class _DB:
        def execute(self, sentencia, *a, **k):
            if "count(*)" in str(sentencia):
                class _R:
                    def scalar(_s):
                        return 1335
                return _R()
            return _db_que_devuelve(filas).execute(sentencia, *a, **k)

    r = bp.buscar_pagina(_DB(), vector_perfil=None, codigos_riasec=[],
                         filtros=bp.Filtros(), pagina=1, por_pagina=5)

    assert r["ranking_hasta"] is None, "sin ranking, la pregunta no aplica"
    assert r["total_paginas"] == 267
    assert r["orden_semantico"] is False


def test_solo_vendible_cruza_el_nivel_del_programa_con_lo_autorizado():
    """No basta con que la ficha autorice algo: tiene que autorizar ESTE nivel.

    Los dos catálogos hablan vocabularios distintos —la ficha dice `pregrado`,
    el programa dice `bachelor`— y el puente vive en el importador. Si aquí se
    comprobara sólo que la ficha tiene alguna autorización, una universidad
    autorizada únicamente en idiomas mostraría sus doctorados.
    """
    sql, _ = bp._where(bp.Filtros(solo_vendible=True))

    assert "institutions_catalog" in sql
    assert "sin_oferta_vendible IS NULL" in sql
    # El CASE traduce el nivel del programa a las autorizaciones que lo cubren.
    assert "CASE pi.nivel" in sql
    assert "WHEN 'bachelor' THEN ARRAY['pregrado']" in sql
    # El literal es JSON dentro de SQL: `'"todos"'::jsonb`.
    assert '\'"todos"\'' in sql, "una ficha con 'todos' autoriza cualquier nivel"


def test_una_ficha_sin_niveles_declarados_no_autoriza_nada():
    """`niveles_autorizados` vacío es un dato que falta, no un permiso.

    Es el mismo criterio que el cargador: el Excel no dijo qué se puede vender
    ahí, y prometerle a una familia un trámite que la agencia no tiene es peor
    que mostrar de menos.
    """
    sql, _ = bp._where(bp.Filtros(solo_vendible=True))
    assert "ic.niveles_autorizados IS NOT NULL" in sql
