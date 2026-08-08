"""A8 · Nivel académico según la etapa + prioridad comercial del catálogo.

Dos pedidos de Verónica en la reunión del 21-07:

  1. *"la IA debería ir a la institución a buscar qué foundations, pregrados y
     maestrías tiene que le puedan servir a esa persona según su perfil"* — con
     su ejemplo textual: **pregrado si está en último año de colegio**.
  2. *"¿tengo cómo ponerle estrellas para que determine qué sale primero?"*

Lo que más protegen estos tests, en orden:

  1. **Que no se esconda oferta de más.** `Program.type` está ADIVINADO por
     texto (`build_programs_from_catalog._derive_type`, con `curso_corto` como
     último recurso). Filtrar de más sobre un dato adivinado le quita opciones
     reales a un estudiante. Por eso sólo se descarta lo que exige un título que
     todavía no puede tener, y hay varios tests que fijan qué NO se descarta.
  2. **Que sin etapa conocida el comportamiento sea el de siempre.** Es el caso
     de cualquier persona que no completó el onboarding.
  3. Que "sin priorizar" no se comporte como "prioridad baja".
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import academic_level as al


# ---------------------------------------------------------------------------
# academic_level · función pura, sin DB
# ---------------------------------------------------------------------------

class TestNivelPorEtapa:
    def test_el_ejemplo_textual_de_la_clienta(self):
        """*"pregrado si está en último año de colegio"*."""
        assert al.evaluar("pregrado", "high_school") == al.PREFERIDO

    @pytest.mark.parametrize("nivel", ["maestria", "mba", "doctorado", "especializacion", "posgrado"])
    @pytest.mark.parametrize("etapa", ["high_school_early", "high_school"])
    def test_sin_bachillerato_no_hay_posgrado(self, nivel, etapa):
        """No es preferencia: es requisito de admisión."""
        assert al.evaluar(nivel, etapa) == al.IMPOSIBLE

    def test_en_la_universidad_la_maestria_pasa_y_el_doctorado_no(self):
        """Planear la maestría mientras se termina el pregrado es media
        conversación de esta agencia, así que no se descarta — pero tampoco se
        premia: el siguiente paso más probable sigue siendo terminar. Un
        doctorado sin título, ese sí es imposible."""
        assert al.evaluar("maestria", "university") == al.NEUTRO
        assert al.evaluar("doctorado", "university") == al.IMPOSIBLE

    @pytest.mark.parametrize("etapa", ["working", "recent_grad", "career_change"])
    @pytest.mark.parametrize("nivel", ["maestria", "doctorado", "mba", "pregrado"])
    def test_con_titulo_en_la_mano_nada_es_imposible(self, etapa, nivel):
        assert al.evaluar(nivel, etapa) != al.IMPOSIBLE

    def test_al_colegial_no_se_le_esconde_el_pregrado_ni_el_idioma(self):
        """El descarte más peligroso sería este · planear la carrera desde el
        colegio es exactamente el caso normal de la agencia."""
        for nivel in ("pregrado", "bachelor", "vacacional", "intercambio", "curso_corto"):
            assert al.evaluar(nivel, "high_school") != al.IMPOSIBLE

    def test_entiende_los_dos_vocabularios(self):
        """Códigos del onboarding y textos de opción del journey · la misma
        persona puede traer uno u otro según por dónde entró."""
        assert al.evaluar("mba", "Terminando el colegio") == al.IMPOSIBLE
        assert al.evaluar("mba", "high_school") == al.IMPOSIBLE
        assert al.evaluar("pregrado", "En la universidad") == al.PREFERIDO
        # Y no depende de mayúsculas ni de espacios sueltos.
        assert al.evaluar("mba", "  TERMINANDO EL COLEGIO ") == al.IMPOSIBLE

    def test_sin_etapa_no_se_descarta_nada(self):
        for etapa in (None, "", "algo_que_nadie_mapeo"):
            assert al.evaluar("doctorado", etapa) == al.NEUTRO

    def test_en_transicion_no_descarta_nada(self):
        """Es justo la persona de la que NO sabemos si tiene título."""
        assert al.evaluar("doctorado", "En transición / no seguro") == al.NEUTRO

    def test_sin_tipo_de_programa_no_se_descarta_nada(self):
        """El catálogo demo estático no trae `type`."""
        assert al.evaluar(None, "high_school") == al.NEUTRO
        assert al.evaluar("", "high_school") == al.NEUTRO

    def test_los_niveles_fuera_de_alcance_alimentan_el_prompt(self):
        fuera = al.niveles_fuera_de_alcance("high_school")
        assert "maestria" in fuera and "doctorado" in fuera
        assert "pregrado" not in fuera
        assert al.niveles_fuera_de_alcance("working") == set()
        assert al.niveles_fuera_de_alcance(None) == set()

    def test_la_etapa_legible_distingue_los_dos_momentos_del_colegio(self):
        """R6-ON-1b · ella lo pidió dos veces ("Susana de 11 grados"): un
        estudiante de 9° no puede decirle a la IA que se está graduando."""
        temprano = al.etapa_legible("high_school_early")
        ultimo = al.etapa_legible("high_school")
        assert temprano != ultimo
        assert al.etapa_legible("En transición / no seguro") is None


# ---------------------------------------------------------------------------
# filter_catalog · el filtro real
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    from app.db.models import Base
    from app.services.catalog_service import invalidate_catalog_cache

    Base.metadata.create_all(bind=engine)
    invalidate_catalog_cache()
    db = Maker()
    try:
        yield db
    finally:
        db.close()
        invalidate_catalog_cache()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _user(**kw):
    from app.db.models import User

    defaults = dict(
        budget_band=None, budget_max_usd=None,
        preferred_countries=[], english_cefr_level=None,
        onboarding_answers={},
    )
    defaults.update(kw)
    return User(**defaults)


def _profile():
    from app.schemas.consolidated_profile import ConsolidatedProfile

    return ConsolidatedProfile(
        summary_narrative="Perfil de prueba para A8. " * 10,
        strengths=["Análisis", "Curiosidad", "Persistencia"],
        # Tokens que no matchean nada del catálogo, para aislar el efecto del
        # nivel y de la prioridad del scoring por intereses.
        interests=["Zetaxia", "Yumbral", "Wolframio"],
        holland_codes=[],
    )


def _oferta(oid, program_type, priority=None):
    """Oferta en el shape que produce catalog_service · neutra en todo lo
    demás para aislar el efecto del nivel y de la prioridad."""
    return {
        "id": oid, "slug": oid, "name": f"Opción {oid}",
        "shortDescription": "", "category": "carrera_completa", "tags": [],
        "programType": program_type,
        "priority": priority,
        "countries": ["España"],
        "duration": {"min": 1, "max": 2, "type": "meses"},
        "cost": {"min": 1000, "max": 1000, "currency": "USD"},
        "budgetTier": "medio",
        "eligibility": {"languageRequirement": "ninguno"},
        "scholarshipsForLatam": None, "active": True,
    }


def _ids(slim):
    return [s["program_id"] for s in slim]


class TestFiltroDeNivel:
    def test_al_colegial_no_le_llega_una_maestria(self):
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("MAE", "maestria"), _oferta("PRE", "pregrado")]
        slim = filter_catalog(
            _user(), _profile(), catalog=catalogo, life_stage="high_school"
        )
        assert _ids(slim) == ["PRE"]

    def test_al_que_trabaja_le_llegan_las_dos(self):
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("MAE", "maestria"), _oferta("PRE", "pregrado")]
        slim = filter_catalog(
            _user(), _profile(), catalog=catalogo, life_stage="working"
        )
        assert set(_ids(slim)) == {"MAE", "PRE"}

    def test_sin_etapa_el_catalogo_sale_completo(self):
        """El comportamiento de HOY para quien no completó el onboarding.
        Si esto falla, se le está escondiendo oferta a gente por un dato que
        nunca dio."""
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("MAE", "maestria"), _oferta("DOC", "doctorado"),
                    _oferta("PRE", "pregrado")]
        slim = filter_catalog(_user(), _profile(), catalog=catalogo)
        assert set(_ids(slim)) == {"MAE", "DOC", "PRE"}

    def test_el_catalogo_demo_sin_programType_no_se_filtra(self):
        """El fallback estático no trae nivel · no puede quedar vacío."""
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("A", None), _oferta("B", None)]
        slim = filter_catalog(
            _user(), _profile(), catalog=catalogo, life_stage="high_school"
        )
        assert set(_ids(slim)) == {"A", "B"}

    def test_el_fallback_de_catalogo_vacio_no_reintroduce_lo_imposible(self):
        """Encontrado por mutation testing · era un agujero real.

        `filter_catalog` termina con "si no quedó nada, devuelve el catálogo":
        un respaldo pensado para relajar presupuesto e idioma. Estaba iterando
        sobre TODO el catálogo, así que a un estudiante de 11° cuyo filtro
        quedara vacío le volvían a entrar las maestrías por la puerta de atrás.

        Un nivel imposible no es una preferencia que se pueda relajar.
        """
        from app.services.recommendation_service import filter_catalog

        # Catálogo donde TODO es imposible para un colegial → el filtro queda
        # vacío y el fallback se dispara.
        catalogo = [_oferta("MAE", "maestria"), _oferta("DOC", "doctorado")]
        slim = filter_catalog(
            _user(), _profile(), catalog=catalogo, life_stage="high_school"
        )
        assert slim == [], f"el fallback recuperó lo imposible: {_ids(slim)}"

    def test_el_fallback_sigue_funcionando_para_lo_que_si_puede_cursar(self):
        """El respaldo no se rompió: lo que sí es cursable vuelve a entrar
        cuando el presupuesto o el idioma dejaron la lista vacía."""
        from app.services.recommendation_service import filter_catalog

        # CEFR bajo + requisito alto → el hard-filter de idioma vacía la lista.
        catalogo = [_oferta("PRE", "pregrado")]
        catalogo[0]["eligibility"] = {"languageRequirement": "avanzado"}
        slim = filter_catalog(
            _user(english_cefr_level="A1"), _profile(),
            catalog=catalogo, life_stage="high_school",
        )
        assert _ids(slim) == ["PRE"]

    def test_el_nivel_que_corresponde_queda_por_delante(self):
        """Ponderar, no sólo filtrar: entre dos que la persona SÍ puede cursar,
        el que le corresponde a su etapa va primero."""
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("CUR", "curso_corto"), _oferta("PRE", "pregrado")]
        slim = filter_catalog(
            _user(), _profile(), catalog=catalogo, life_stage="high_school"
        )
        assert _ids(slim)[0] == "PRE"

    def test_el_nivel_viaja_hasta_el_bloque_del_prompt(self):
        """Regla del repo: un campo que nadie lee es un campo muerto."""
        from app.services.recommendation_service import (
            filter_catalog, _format_catalog_block,
        )

        slim = filter_catalog(
            _user(), _profile(), catalog=[_oferta("PRE", "pregrado")],
            life_stage="working",
        )
        assert slim[0]["program_type"] == "pregrado"
        assert "nivel=pregrado" in _format_catalog_block(slim)

    def test_sin_nivel_la_clave_se_omite_en_vez_de_escribir_un_guion(self):
        from app.services.recommendation_service import (
            filter_catalog, _format_catalog_block,
        )

        slim = filter_catalog(_user(), _profile(), catalog=[_oferta("X", None)])
        assert "nivel=" not in _format_catalog_block(slim)


class TestEtapaEnElPrompt:
    def test_la_etapa_y_lo_que_no_puede_cursar_llegan_al_modelo(self):
        from app.services.recommendation_service import _format_constraints_block

        bloque = _format_constraints_block(_user(), "high_school")
        assert "último año" in bloque
        assert "maestria" in bloque and "doctorado" in bloque

    def test_sin_etapa_el_bloque_no_menciona_niveles(self):
        from app.services.recommendation_service import _format_constraints_block

        bloque = _format_constraints_block(_user(), None)
        assert "Etapa académica" not in bloque
        assert "TODAVÍA no puede cursar" not in bloque

    def test_a_quien_puede_todo_no_se_le_lista_nada_prohibido(self):
        from app.services.recommendation_service import _format_constraints_block

        bloque = _format_constraints_block(_user(), "working")
        assert "Etapa académica" in bloque
        assert "TODAVÍA no puede cursar" not in bloque


class TestEtapaDeVida:
    def test_prefiere_el_onboarding(self, db_session):
        from app.services.recommendation_service import etapa_de_vida

        user = _user(onboarding_answers={"life_stage": "high_school"})
        user.email = "a@test.com"
        user.hashed_password = "x"
        user.name = "A"
        db_session.add(user)
        db_session.commit()

        assert etapa_de_vida(db_session, user) == "high_school"

    def test_cae_al_journey_cuando_el_onboarding_no_lo_tiene(self, db_session):
        """El onboarding siembra el journey, pero NO al revés: quien entró
        directo al journey no tiene nada en `User`."""
        from app.db.models import Session as DBSession
        from app.services.recommendation_service import etapa_de_vida

        user = _user(onboarding_answers={})
        user.email = "b@test.com"
        user.hashed_password = "x"
        user.name = "B"
        db_session.add(user)
        db_session.commit()
        db_session.add(
            DBSession(user_id=user.id, answers={"lifeStage": "Ya trabajando"})
        )
        db_session.commit()

        assert etapa_de_vida(db_session, user) == "Ya trabajando"

    def test_sin_ninguna_de_las_dos_devuelve_none(self, db_session):
        from app.services.recommendation_service import etapa_de_vida

        user = _user(onboarding_answers={})
        user.email = "c@test.com"
        user.hashed_password = "x"
        user.name = "C"
        db_session.add(user)
        db_session.commit()

        assert etapa_de_vida(db_session, user) is None

    def test_una_etapa_que_no_reconocemos_no_bloquea_el_journey(self, db_session):
        """`recent_grad` sí se mapea; un valor futuro sin mapear cae al journey
        y, si tampoco está, a None — nunca a un descarte."""
        from app.services.recommendation_service import etapa_de_vida

        user = _user(onboarding_answers={"life_stage": "algo_nuevo_2027"})
        user.email = "d@test.com"
        user.hashed_password = "x"
        user.name = "D"
        db_session.add(user)
        db_session.commit()

        assert al.evaluar("doctorado", etapa_de_vida(db_session, user)) == al.NEUTRO


# ---------------------------------------------------------------------------
# Prioridad comercial
# ---------------------------------------------------------------------------

class TestPrioridad:
    def test_la_priorizada_va_primero(self):
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("BAJA", "pregrado", priority=1),
                    _oferta("ALTA", "pregrado", priority=10)]
        slim = filter_catalog(_user(), _profile(), catalog=catalogo)
        assert _ids(slim)[0] == "ALTA"

    def test_sin_priorizar_no_es_prioridad_baja(self):
        """Hoy las 2.511 filas están en NULL. Si NULL pesara como 0, priorizar
        una sola institución mandaría al fondo a todo el catálogo real."""
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("SIN", "pregrado", priority=None),
                    _oferta("UNO", "pregrado", priority=1)]
        slim = filter_catalog(_user(), _profile(), catalog=catalogo)
        # La de prioridad 1 suma 0.09; la sin priorizar no suma ni resta. El
        # orden entre ellas es lo de menos: lo que se fija es que estar sin
        # priorizar NO descarta ni hunde.
        assert set(_ids(slim)) == {"SIN", "UNO"}

    def test_la_prioridad_no_le_gana_al_nivel_imposible(self):
        """Ninguna prioridad comercial justifica ofrecerle un doctorado a
        alguien que está en el colegio."""
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("DOC", "doctorado", priority=10),
                    _oferta("PRE", "pregrado", priority=None)]
        slim = filter_catalog(
            _user(), _profile(), catalog=catalogo, life_stage="high_school"
        )
        assert _ids(slim) == ["PRE"]

    def test_un_valor_fuera_de_rango_se_ignora(self):
        """El PATCH valida 1-10, pero un import viejo o un script podrían meter
        cualquier cosa · no puede desbalancear el scoring."""
        from app.services.recommendation_service import filter_catalog

        catalogo = [_oferta("LOCA", "pregrado", priority=999),
                    _oferta("SANA", "pregrado", priority=10)]
        slim = filter_catalog(_user(), _profile(), catalog=catalogo)
        assert _ids(slim)[0] == "SANA"

    def test_el_orden_del_catalogo_pone_primero_lo_priorizado(self, db_session):
        """*"¿tengo cómo ponerle estrellas para que determine qué sale
        primero?"* · el orden de /ofertas, que es donde ella lo vería.

        Se usa `orden_del_catalogo()` —la misma función que llama el endpoint—
        y no un ORDER BY escrito aquí: un test que arma su propia consulta
        pasa aunque el endpoint ordene distinto, que es no probar nada.
        """
        from app.api.v1.ofertas import orden_del_catalogo
        from app.db.models import Program

        for nombre, prio in [("Zeta", None), ("Alfa", None), ("Beta", 9), ("Delta", 3)]:
            db_session.add(Program(
                program_id=nombre.lower(), name=nombre, slug=nombre.lower(),
                country="CO", institution=nombre, type="pregrado",
                priority=prio, active=True,
            ))
        db_session.commit()

        orden = [
            p.name for p in
            db_session.query(Program).order_by(*orden_del_catalogo()).all()
        ]
        # Priorizadas primero (9 antes que 3), y el resto alfabético como antes.
        assert orden == ["Beta", "Delta", "Alfa", "Zeta"]

    def test_sin_priorizar_no_se_ordena_como_si_fuera_lo_mejor(self):
        """En Postgres, `ORDER BY x DESC` pone los NULL PRIMERO — sin
        `nullslast`, las 2.511 filas sin priorizar se irían al tope y la
        prioridad no ordenaría nada.

        Compilado contra el dialecto de PRODUCCIÓN a propósito: SQLite (donde
        corren los tests) ordena los NULL al revés y el test de arriba pasaría
        igual sin `nullslast`. Este es el único que ve el bug real.
        """
        from sqlalchemy.dialects import postgresql
        from app.api.v1.ofertas import orden_del_catalogo
        from app.db.models import Program

        sql = str(
            Program.__table__.select()
            .order_by(*orden_del_catalogo())
            .compile(dialect=postgresql.dialect())
        )
        assert "NULLS LAST" in sql.upper()

    def test_la_prioridad_viaja_de_la_columna_al_catalogo(self, db_session):
        from app.db.models import Program
        from app.services.catalog_service import get_catalog_for_recommender

        db_session.add_all([
            Program(program_id="p1", name="Con", slug="p1", country="CO",
                    institution="Con", type="pregrado", priority=7, active=True),
            Program(program_id="p2", name="Sin", slug="p2", country="CO",
                    institution="Sin", type="pregrado", priority=None, active=True),
        ])
        db_session.commit()

        catalogo = {c["program_id"]: c for c in
                    get_catalog_for_recommender(db_session, use_cache=False)}
        assert catalogo["p1"]["priority"] == 7
        assert catalogo["p2"]["priority"] is None
        # …y el nivel también, que es lo que necesita el filtro.
        assert catalogo["p1"]["programType"] == "pregrado"

    def test_el_estudiante_no_ve_la_prioridad_comercial(self, db_session):
        """Es un juicio interno de la agencia · no tiene por qué llegarle al
        alumno en el payload de /ofertas."""
        from app.db.models import Program
        from app.api.v1.ofertas import _program_to_oferta

        p = Program(program_id="p1", name="X", slug="p1", country="CO",
                    institution="X", type="pregrado", priority=9, active=True)
        db_session.add(p)
        db_session.commit()

        oferta = _program_to_oferta(p)
        serializado = str(oferta)
        assert "priority" not in serializado and "prioridad" not in serializado


class TestSchemaPrioridad:
    def test_el_panel_puede_escribirla_entre_1_y_10(self):
        from app.schemas.program import ProgramUpdate

        assert ProgramUpdate(priority=1).priority == 1
        assert ProgramUpdate(priority=10).priority == 10

    @pytest.mark.parametrize("valor", [0, 11, -3])
    def test_rechaza_lo_que_esta_fuera_de_rango(self, valor):
        import pydantic
        from app.schemas.program import ProgramUpdate

        with pytest.raises(pydantic.ValidationError):
            ProgramUpdate(priority=valor)

    def test_no_mandarla_no_la_borra(self):
        """`exclude_unset` en el PATCH · editar el nombre no puede despriorizar
        una institución sin querer."""
        from app.schemas.program import ProgramUpdate

        payload = ProgramUpdate(name="Nuevo nombre")
        assert "priority" not in payload.model_dump(exclude_unset=True)
