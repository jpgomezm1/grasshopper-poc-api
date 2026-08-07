"""§1 · Que las rutas miren los tests.

Verónica, sobre la pantalla de Rutas (21-07): *"este tampoco he podido que me
saque cosas, siempre me saca lo mismo"* · *"¿por qué todavía no sale nada?"*. Y
su tesis: *"el test verdaderamente va a ser el que más nos va a generar
información"*.

El test que más importa de este archivo es `test_el_hash_cambia_cuando_llega_un_test`:
sin él, todo lo demás funciona y **nadie se entera**, porque quien viera sus rutas
y después hiciera un test seguiría viendo las de antes, cacheadas sin mirar
ninguno. Es el defecto de "campo que nadie lee" en otra forma.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import ai_client
from app.services import ai_service, journey_service
from app.services import test_interpretation_service as tis


# ---------------------------------------------------------------------------
# DB en memoria · nunca contra la real
# ---------------------------------------------------------------------------


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _estudiante(db, *, cefr=None):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    u = User(
        email="rutas@grasshopper.dev",
        hashed_password=get_password_hash("x"),
        name="Ana",
        role=UserRole.STUDENT,
        onboarding_status=OnboardingStatus.NOT_STARTED,
        english_cefr_level=cefr,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _resultado(db, user, test_id="holland", scores=None, self_assessment=None):
    """Las claves son las REALES del motor (`_HOLLAND`: R·I·A·S·E·C).

    La primera versión de este fixture usaba `artistic`/`social` escritos a
    mano. El test pasaba igual y el bloque salía con las siglas crudas — que es
    justo lo que A1 vino a arreglar. Es el mismo defecto que documentó la
    auditoría del 29-07: fixtures que fijan formas de datos que producción
    nunca genera.
    """
    from app.db.models import VocationalTestResult

    r = VocationalTestResult(
        user_id=user.id,
        test_id=test_id,
        answers={},
        scores=scores or {"A": 88, "S": 72, "R": 20},
        self_assessment=self_assessment,
    )
    db.add(r)
    db.commit()
    return r


# ---------------------------------------------------------------------------
# 1 · El bloque de tests
# ---------------------------------------------------------------------------


def test_sin_tests_lo_dice_explicitamente(db):
    """Un hueco mudo en el prompt invita al modelo a inventarse el perfil."""
    user = _estudiante(db)

    bloque = tis.format_tests_for_prompt(db, user.id)

    assert bloque == tis.SIN_TESTS
    assert bloque.strip(), "nunca puede quedar vacío"


def test_sin_usuario_no_consulta_la_base(db):
    """El journey puede ser anónimo · no hay tests que buscar."""
    assert tis.format_tests_for_prompt(db, None) == tis.SIN_TESTS


def test_el_bloque_usa_nombres_legibles_no_siglas(db):
    """Reusa `format_scores_block` · pasarle JSON crudo desharía el arreglo A1.

    A1 fue el reclamo #1 de la clienta: *"le salen como unas siglas y ya"*. Si
    las rutas reciben `{"A": 88}` en vez de la dimensión con su nombre, ese
    arreglo se pierde justo en el entregable que ella llama hoja de ruta.
    """
    user = _estudiante(db)
    _resultado(db, user)

    bloque = tis.format_tests_for_prompt(db, user.id)

    assert "Artístico" in bloque, "la sigla no se tradujo · se perdió A1"
    assert "88" in bloque
    # El orden importa: la dimensión más alta primero.
    assert bloque.index("Artístico") < bloque.index("Realista")


def test_el_bloque_incluye_el_autoanalisis(db):
    """A6 · lo que ELLA cree, para poder contrastarlo con lo que el test mide."""
    user = _estudiante(db)
    _resultado(db, user, self_assessment={"careers": ["Diseño", "Arquitectura"]})

    bloque = tis.format_tests_for_prompt(db, user.id)

    assert "Diseño" in bloque
    assert "1." in bloque, "el orden importa · 1 = la que más"


def test_el_bloque_incluye_el_ingles_medido(db):
    user = _estudiante(db, cefr="B2")
    _resultado(db, user)

    assert "B2" in tis.format_tests_for_prompt(db, user.id)


def test_el_ingles_solo_no_cuenta_como_perfil(db):
    """Sin tests de orientación, un nivel de inglés NO es un perfil.

    Bug real que encontró este test: la primera versión devolvía sólo el bloque
    de inglés, así que el prompt creía que ya había perfil psicométrico y
    dejaba de pedir tests — justo la información que falta. El nivel se
    conserva (es útil), pero el "todavía no hay tests" manda.
    """
    user = _estudiante(db, cefr="B2")

    bloque = tis.format_tests_for_prompt(db, user.id)

    assert tis.SIN_TESTS in bloque, "el prompt tiene que seguir sabiendo que faltan tests"
    assert "B2" in bloque, "el nivel de inglés no se pierde"


# ---------------------------------------------------------------------------
# 2 · LA CACHÉ · lo que hace que el resto sirva
# ---------------------------------------------------------------------------


def test_el_hash_cambia_cuando_llega_un_test():
    """Sin esto, hacer un test no refresca las rutas y nadie se entera."""
    respuestas = {"lifeStage": "Terminando el colegio"}

    sin = journey_service._ai_inputs_hash(respuestas, {}, tis.SIN_TESTS)
    con = journey_service._ai_inputs_hash(respuestas, {}, "### Holland\n- Artístico: 88")

    assert sin != con


def test_el_hash_es_estable_con_los_mismos_tests():
    """Si cambiara en cada request, se regeneraría (y se pagaría) siempre."""
    bloque = "### Holland\n- Artístico: 88"

    a = journey_service._ai_inputs_hash({"x": 1}, {}, bloque)
    b = journey_service._ai_inputs_hash({"x": 1}, {}, bloque)

    assert a == b


# ---------------------------------------------------------------------------
# 3 · generate_routes
# ---------------------------------------------------------------------------


class _FakeMessages:
    def __init__(self, outcome):
        self._outcome = outcome
        self.kwargs = None

    def create(self, **kwargs):
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
    cliente = _FakeClient(outcome)
    monkeypatch.setattr(ai_client, "get_client", lambda: cliente)
    return cliente


def _respuesta(texto):
    return SimpleNamespace(
        content=[SimpleNamespace(text=texto)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


_JSON_OK = """{"routes": [
  {"key": "R1", "name": "Ruta Diseño", "why": "porque sí",
   "what_it_looks_like": "así", "next_step": "haz esto",
   "evidence": ["tu perfil marca alto en lo artístico"]}
]}"""


def test_los_tests_llegan_al_prompt(monkeypatch):
    """El camino incómodo: no basta con que la función acepte el parámetro."""
    cliente = _patch_sdk(monkeypatch, _respuesta(_JSON_OK))

    ai_service.generate_routes(
        {}, "s1", tests_block="### Holland\n- Artístico: 88 · le gusta crear"
    )

    prompt = cliente.messages.kwargs["messages"][0]["content"]
    assert "Artístico: 88" in prompt, "el bloque de tests no llegó al prompt"


def test_sin_bloque_el_prompt_dice_que_no_hay_tests(monkeypatch):
    cliente = _patch_sdk(monkeypatch, _respuesta(_JSON_OK))

    ai_service.generate_routes({}, "s1")

    assert ai_service.SIN_TESTS_EN_RUTAS in cliente.messages.kwargs["messages"][0]["content"]


def test_la_evidencia_se_parsea(monkeypatch):
    _patch_sdk(monkeypatch, _respuesta(_JSON_OK))

    salida = ai_service.generate_routes({}, "s1", tests_block="x")

    assert salida.routes[0].evidence == ["tu perfil marca alto en lo artístico"]
    assert salida.routes[0].is_generic is False


def test_una_ruta_sin_evidencia_no_revienta(monkeypatch):
    """El modelo puede omitir el campo · eso no puede tumbar la pantalla."""
    sin_evidencia = """{"routes": [{"key": "R1", "name": "n", "why": "w",
      "what_it_looks_like": "l", "next_step": "s"}]}"""
    _patch_sdk(monkeypatch, _respuesta(sin_evidencia))

    salida = ai_service.generate_routes({}, "s1", tests_block="x")

    assert salida.routes[0].evidence == []


def test_el_fallback_se_marca_como_generico(monkeypatch):
    """Se presentaban idénticas a las personalizadas · el estudiante no podía saberlo."""
    _patch_sdk(monkeypatch, RuntimeError("la IA se cayó"))

    salida = ai_service.generate_routes({}, "s1", tests_block="x")

    assert salida.routes, "el fallback sigue entregando algo"
    assert all(r.is_generic for r in salida.routes)


def test_las_dos_constantes_de_sin_tests_coinciden():
    """Están duplicadas para evitar un ciclo de imports · que no se separen."""
    assert ai_service.SIN_TESTS_EN_RUTAS == tis.SIN_TESTS
