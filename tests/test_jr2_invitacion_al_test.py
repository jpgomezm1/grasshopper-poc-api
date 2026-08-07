"""JR-2 · Llevar al test temprano en el journey.

Verónica, reunión del 21-07: *"estamos cayendo en un error: el test se lo estamos
tirando por allá lejísimos… el test verdaderamente va a ser el que más nos va a
generar información"*.

Todo va detrás del feature flag `journey_test_invitation`, **apagado por defecto**,
porque la documentación de Tomás marca JR-2 como decisión de producto de la clienta,
no de implementación. De ahí el test más importante de este archivo:
`test_con_el_flag_apagado_la_secuencia_es_identica`. Si ese falla, se rompió el
journey de gente real.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.state_machine import JOURNEY_STEPS, get_next_step, get_step
from app.schemas.session import ViewType


# La secuencia del journey ANTES de JR-2, escrita a mano a propósito. Derivarla
# de JOURNEY_STEPS haría el test tautológico: insertar un paso lo actualizaría
# solo y nunca avisaría de la regresión.
SECUENCIA_HISTORICA = [
    "welcome",
    "whyHere",
    "empathy",
    "lifeStage",
    "timeHorizon",
    "clarityLevel",
    "interestType",
    "weeklyActivities",
    "dontWant",
    "declaredAspirations",
    "partialSummary1",
    "budgetBand",
    "languageLevel",
    "geoPreference",
    "synthesis",
    "routes",
    "nextStep",
]

FLAG_OFF = {"test_invitation_enabled": False, "has_tests": False, "has_english_test": False}
FLAG_ON_SIN_TESTS = {"test_invitation_enabled": True, "has_tests": False, "has_english_test": False}
FLAG_ON_CON_TESTS = {"test_invitation_enabled": True, "has_tests": True, "has_english_test": False}
FLAG_ON_CON_INGLES = {"test_invitation_enabled": True, "has_tests": True, "has_english_test": True}


def _recorrer(contexto=None, answers=None, onboarding=None) -> list[str]:
    """Camina el journey de principio a fin y devuelve los pasos visitados."""
    actual = "welcome"
    visitados = [actual]
    while True:
        siguiente = get_next_step(actual, answers, onboarding, contexto)
        if not siguiente:
            break
        assert siguiente not in visitados, f"ciclo en {siguiente}"
        visitados.append(siguiente)
        actual = siguiente
    return visitados


# ---------------------------------------------------------------- flag apagado

def test_con_el_flag_apagado_la_secuencia_es_identica():
    """EL test de este archivo · producción no puede cambiar."""
    assert _recorrer(FLAG_OFF) == SECUENCIA_HISTORICA
    assert len(_recorrer(FLAG_OFF)) == 17


def test_sin_contexto_ninguno_tampoco_aparece_la_invitacion():
    """Un call-site que olvide pasar contexto no puede filtrar el paso.

    Al quitar el atajo de `get_next_step` (antes salía sin evaluar `skip_if`
    cuando no había respuestas), este es el caso que sostiene que quitarlo fue
    seguro Y que el paso sigue apagado.
    """
    assert _recorrer(None) == SECUENCIA_HISTORICA
    assert get_next_step("clarityLevel") == "interestType"


# --------------------------------------------------------------- flag prendido

def test_con_el_flag_prendido_y_sin_tests_la_invitacion_va_despues_de_clarity():
    assert get_next_step("clarityLevel", {}, {}, FLAG_ON_SIN_TESTS) == "testInvitation"
    recorrido = _recorrer(FLAG_ON_SIN_TESTS)
    assert recorrido.index("testInvitation") == recorrido.index("clarityLevel") + 1
    assert len(recorrido) == 18


def test_a_quien_ya_hizo_un_test_no_se_le_invita():
    assert get_next_step("clarityLevel", {}, {}, FLAG_ON_CON_TESTS) == "interestType"
    assert "testInvitation" not in _recorrer(FLAG_ON_CON_TESTS)


def test_responder_la_invitacion_avanza_al_journey_normal():
    """Las dos salidas continúan igual · irse al test es cosa del front."""
    assert get_next_step("testInvitation", {}, {}, FLAG_ON_SIN_TESTS) == "interestType"


def test_la_invitacion_no_se_repregunta():
    """Con la respuesta guardada, el paso ya no vuelve a salir."""
    respondido = {"testInvitation": "seguir"}
    assert get_next_step("clarityLevel", respondido, {}, FLAG_ON_SIN_TESTS) == "interestType"


def test_interest_type_se_mantiene_aunque_haya_tests():
    """Holland mide R·I·A·S·E·C; este paso pregunta por MODALIDAD (aprender algo
    práctico · mejorar un idioma · vivir en otro país). No son el mismo eje, así
    que tener tests no lo hace redundante."""
    assert "interestType" in _recorrer(FLAG_ON_CON_INGLES)


# ------------------------------------------------------- el paso del idioma

def test_el_idioma_se_salta_solo_con_examen_de_ingles():
    """Un examen medido reemplaza una percepción · pero sólo si existe."""
    assert "languageLevel" not in _recorrer(FLAG_ON_CON_INGLES)
    assert "languageLevel" in _recorrer(FLAG_ON_CON_TESTS)
    assert "languageLevel" in _recorrer(FLAG_ON_SIN_TESTS)


def test_el_examen_de_ingles_no_salta_el_idioma_con_el_flag_apagado():
    """El flag manda sobre todo lo demás."""
    ctx = {"test_invitation_enabled": False, "has_tests": True, "has_english_test": True}
    assert _recorrer(ctx) == SECUENCIA_HISTORICA


def test_el_paso_del_idioma_conserva_su_texto_y_su_destino():
    """Saltarlo no es borrarlo: sigue vivo para quien no presentó el examen."""
    paso = get_step("languageLevel")
    assert paso is not None
    assert paso.next_step == "geoPreference"
    assert paso.save_to == "languageLevel"


# --------------------------------------------------------- forma del paso nuevo

def test_la_invitacion_tiene_su_propio_view_type_y_dos_salidas():
    """El front no puede depender de comparar el TEXTO de la opción: esa copy es
    de la clienta y la puede cambiar cuando quiera."""
    paso = get_step("testInvitation")
    assert paso is not None
    assert paso.view_type == ViewType.TEST_INVITATION
    assert paso.options is not None and len(paso.options) == 2
    assert paso.save_to == "testInvitation"
    assert paso.next_step == "interestType"
    assert paso.skip_if is not None


def test_el_journey_tiene_18_pasos_definidos():
    assert len(JOURNEY_STEPS) == 18
    assert [s.id for s in JOURNEY_STEPS].count("testInvitation") == 1


def test_una_condicion_rota_no_deja_al_usuario_atascado():
    paso = get_step("testInvitation")
    original = paso.skip_if
    paso.skip_if = lambda ctx: 1 / 0  # noqa: E731
    try:
        # Ante la duda se MUESTRA el paso · nunca se rompe el journey.
        assert get_next_step("clarityLevel", {}, {}, FLAG_OFF) == "testInvitation"
    finally:
        paso.skip_if = original


# ----------------------------------------------- contexto_de_navegacion (DB)

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    Maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sesion = Maker()
    try:
        yield sesion
    finally:
        sesion.close()


def _usuario(db, **kwargs):
    from app.db.models import User, UserRole

    u = User(
        email=kwargs.pop("email", "estudiante@test.com"),
        hashed_password="x",
        name="Estudiante",
        role=kwargs.pop("role", UserRole.STUDENT),
        **kwargs,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _sesion(db, user=None):
    from app.db.models import Session as DBSession

    s = DBSession(user_id=user.id if user else None, answers={})
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _prender_flag(db, enabled=True):
    from app.db.models import FeatureFlag
    from app.services import feature_flags_service as ff
    from app.services.journey_service import FLAG_TEST_INVITATION

    db.add(
        FeatureFlag(
            key=FLAG_TEST_INVITATION,
            name="Invitación al test en el journey",
            enabled=enabled,
        )
    )
    db.commit()
    ff.invalidate_cache()


@pytest.fixture(autouse=True)
def _sin_cache_de_flags():
    """El caché de flags es global al proceso y dura 60 s · sin esto, el estado
    de un test se filtra al siguiente y el de "flag apagado" pasaría por
    casualidad."""
    from app.services import feature_flags_service as ff

    ff.invalidate_cache()
    yield
    ff.invalidate_cache()


def test_sesion_anonima_no_activa_nada(db):
    from app.services.journey_service import contexto_de_navegacion

    ctx = contexto_de_navegacion(db, _sesion(db))
    assert ctx == {
        "test_invitation_enabled": False,
        "has_tests": False,
        "has_english_test": False,
    }


def test_sin_la_fila_del_flag_todo_queda_apagado(db):
    """`is_feature_enabled` devuelve False cuando el flag no existe · esto fija
    que no hay que crear nada para que producción siga igual."""
    from app.services.journey_service import contexto_de_navegacion

    usuario = _usuario(db, english_test_completed=True, english_cefr_level="B2")
    ctx = contexto_de_navegacion(db, _sesion(db, usuario))
    assert ctx["test_invitation_enabled"] is False
    # Aunque el usuario SÍ tenga examen, con el flag apagado no se reporta:
    # nadie debe poder saltarse un paso por un dato que no se consultó.
    assert ctx["has_english_test"] is False


def test_con_el_flag_prendido_se_reporta_el_examen_de_ingles(db, monkeypatch):
    from app.services import journey_service as js

    monkeypatch.setattr(js, "FLAG_TEST_INVITATION", "journey_test_invitation")
    _prender_flag(db)
    usuario = _usuario(db, english_test_completed=True, english_cefr_level="B2")

    from app.services import recommendation_service as rs

    monkeypatch.setattr(rs, "user_has_tests", lambda db, user: True)

    ctx = js.contexto_de_navegacion(db, _sesion(db, usuario))
    assert ctx == {
        "test_invitation_enabled": True,
        "has_tests": True,
        "has_english_test": True,
    }


def test_el_panel_muestra_el_nivel_medido_cuando_se_salto_el_paso(db, monkeypatch):
    """El panel cuenta 6 campos. Saltar el paso del idioma a secas dejaría 5/6
    para siempre — perfil incompleto justo por haber hecho MÁS."""
    from app.services.journey_service import get_side_panel_data

    usuario = _usuario(db, english_test_completed=True, english_cefr_level="B2")
    sesion = _sesion(db, usuario)

    panel = get_side_panel_data(db, sesion)
    assert panel.profile_preview.languageLevel == "B2 (medido)"
    # …y NO se sembró una respuesta que la persona nunca dio.
    assert "languageLevel" not in (sesion.answers or {})


def test_la_api_emite_el_paso_completo_y_serializable(db, monkeypatch):
    """De punta a punta · lo que los tests de la máquina de estados NO cubren.

    `ViewType.TEST_INVITATION` tiene que existir también en el schema Pydantic
    de la respuesta. Si sólo estuviera en `state_machine`, la API respondería
    500 al serializar y ningún test de arriba se enteraría.
    """
    from app.services import journey_service as js
    from app.services import recommendation_service as rs

    _prender_flag(db)
    monkeypatch.setattr(rs, "user_has_tests", lambda db, user: False)

    usuario = _usuario(db)
    sesion = _sesion(db, usuario)
    sesion.current_step = "testInvitation"
    db.commit()

    respuesta = js.build_journey_response(db, sesion)
    payload = respuesta.model_dump(mode="json")

    assert payload["view_type"] == "TEST_INVITATION"
    assert payload["step_id"] == "testInvitation"
    assert len(payload["options"]) == 2
    assert payload["progress"]["percentage"] <= 100


def test_la_respuesta_del_journey_le_gana_al_nivel_medido(db):
    """Si contestó el paso, manda lo que contestó · el medido es un respaldo."""
    from app.services.journey_service import get_side_panel_data

    usuario = _usuario(db, english_test_completed=True, english_cefr_level="B2")
    sesion = _sesion(db, usuario)
    sesion.answers = {"languageLevel": "Intermedio"}
    db.commit()

    panel = get_side_panel_data(db, sesion)
    assert panel.profile_preview.languageLevel == "Intermedio"
