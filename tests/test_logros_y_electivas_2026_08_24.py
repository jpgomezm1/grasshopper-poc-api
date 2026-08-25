"""Reunión clienta 2026-08-24 · logros conectados a la IA/dossier/snapshot +
recomendación de materias electivas.

Dos frentes:

1. Los logros (`ExtracurricularActivity`, F-001, ya existentes) NO llegaban al
   pipeline de IA del journey (`ai_service.format_onboarding_context`, distinto
   del perfil consolidado que ya los leía desde JR-7), ni al dossier del
   asesor, ni al snapshot exportable del estudiante. Aquí se prueba que ahora
   sí — mockeando la FRONTERA (`call_claude_with_meta`), nunca la función bajo
   prueba, y sobre HTTP real donde el defecto importaba (dossier/snapshot).

2. Recomendación de materias electivas (minuto 27:00 de la reunión):
   determinista, sin IA — no hay superficie para que se invente una materia.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ACTIVITIES = [
    {
        "category": "sport",
        "name": "Capitana del equipo de vóleibol",
        "role": "capitana",
        "hours_per_week": 6,
        "en_curso": True,
        "description": "Lidera entrenamientos y estrategia de juego.",
        "achievements": ["1er lugar regional 2024"],
    }
]


# ---------------------------------------------------------------------------
# 1a · `format_onboarding_context` cita los logros (unit, sin BD)
# ---------------------------------------------------------------------------


def test_format_onboarding_context_incluye_actividades():
    from app.services.ai_service import format_onboarding_context

    txt = format_onboarding_context(None, ACTIVITIES)
    assert "Capitana del equipo de vóleibol" in txt
    assert "capitana" in txt
    assert "1er lugar regional 2024" in txt
    assert "deportivo" in txt  # label de category=sport


def test_format_onboarding_context_tolera_todo_vacio():
    from app.services.ai_service import format_onboarding_context

    assert format_onboarding_context(None, None) == "(sin datos del onboarding)"
    assert format_onboarding_context({}, []) == "(sin datos del onboarding)"


def test_format_onboarding_context_sanea_llaves_en_actividad():
    """Una descripción con `{`/`}` no debe reventar el `str.format` del prompt."""
    from app.services.ai_service import format_onboarding_context

    txt = format_onboarding_context(None, [{"name": "Club de {robótica}"}])
    assert "{" not in txt and "}" not in txt


# ---------------------------------------------------------------------------
# 1b · los 3 pasos IA del journey reciben `activities` y lo meten en el prompt
# (mismo patrón que `test_adaptive_session_context_r4.py`: mockear la frontera)
# ---------------------------------------------------------------------------


def _capture_prompt(monkeypatch):
    captured = {}

    def _fake_call(prompt, **kwargs):
        captured["prompt"] = prompt
        return None, {}  # sin respuesta → cae al fallback, no importa aquí

    from app.services import ai_service

    monkeypatch.setattr(ai_service, "call_claude_with_meta", _fake_call)
    return captured


def test_reflection_recibe_actividades(monkeypatch):
    from app.services import ai_service

    captured = _capture_prompt(monkeypatch)
    ai_service.generate_empathy_reflection(
        "quiero claridad", "sess-1", activities=ACTIVITIES
    )
    assert "Capitana del equipo de vóleibol" in captured["prompt"]


def test_synthesis_recibe_actividades(monkeypatch):
    from app.services import ai_service

    captured = _capture_prompt(monkeypatch)
    ai_service.generate_synthesis(
        {"lifeStage": "En la universidad"}, "sess-1", activities=ACTIVITIES
    )
    assert "Capitana del equipo de vóleibol" in captured["prompt"]


def test_routes_recibe_actividades(monkeypatch):
    from app.services import ai_service

    captured = _capture_prompt(monkeypatch)
    ai_service.generate_routes(
        {"lifeStage": "En la universidad"}, "sess-1", activities=ACTIVITIES
    )
    assert "Capitana del equipo de vóleibol" in captured["prompt"]


def test_sin_actividades_no_rompe_nada(monkeypatch):
    from app.services import ai_service

    captured = _capture_prompt(monkeypatch)
    out = ai_service.generate_empathy_reflection("hola", "sess-1")
    assert out.text
    assert "(sin datos del onboarding)" in captured["prompt"]


# ---------------------------------------------------------------------------
# 1c · journey_service: wiring + caché
# ---------------------------------------------------------------------------


def test_owner_activities_none_si_sesion_anonima():
    from app.services.journey_service import _owner_activities

    session = SimpleNamespace(user_id=None)
    assert _owner_activities(MagicMock(), session) is None


def test_hash_cambia_si_hay_un_logro_nuevo():
    """Sin esto, un estudiante que registra un logro seguiría viendo la misma
    reflexión/síntesis/rutas cacheadas — el mismo defecto de caché obsoleta
    que R5 ya corrigió para tests y onboarding."""
    from app.services.journey_service import _ai_inputs_hash

    sin_logros = _ai_inputs_hash({"a": 1}, {"o": 1}, activities=None)
    con_logros = _ai_inputs_hash({"a": 1}, {"o": 1}, activities=ACTIVITIES)
    assert sin_logros != con_logros


def test_hash_estable_para_las_mismas_actividades():
    from app.services.journey_service import _ai_inputs_hash

    h1 = _ai_inputs_hash({"a": 1}, {"o": 1}, activities=ACTIVITIES)
    h2 = _ai_inputs_hash({"a": 1}, {"o": 1}, activities=list(ACTIVITIES))
    assert h1 == h2


# ---------------------------------------------------------------------------
# 2 · Fixture HTTP real (SQLite en memoria) · mismo patrón que
#     `test_a9_study_preferences.py` (`app_with_db`)
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_db(monkeypatch):
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setenv("BITRIX_WEBHOOK_URL", "")
    from app.db import database as dbmod
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.db.models import Base
    Base.metadata.create_all(bind=engine)

    from app.main import app
    app.dependency_overrides[dbmod.get_db] = _override_get_db

    from app.core.rate_limiter import limiter as gh_limiter
    gh_limiter.reset()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _student(SessionLocal, email, **extra):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Estudiante",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
            **extra,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _headers(client, email):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# 2a · el dossier del asesor muestra los logros (el "camino incómodo")
# ---------------------------------------------------------------------------


def test_los_logros_llegan_al_dossier_del_asesor(app_with_db):
    """El dossier leía notas y demographics pero nunca `ExtracurricularActivity`.
    Este es el sitio donde el defecto se vería: la pestaña de logros del
    asesor, en blanco, aunque el estudiante ya hubiera registrado uno."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "logros.dossier@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "logros.dossier@grasshopper.dev")
        r = client.post(
            "/api/v1/me/activities",
            headers=h,
            json={
                "category": "sport",
                "name": "Capitana del equipo de vóleibol",
                "role": "capitana",
                "hours_per_week": 6,
                "achievements": ["1er lugar regional 2024"],
            },
        )
        assert r.status_code == 201, r.text

    from app.services import dossier_service
    from app.db.models import User

    db = SessionLocal()
    try:
        student = db.query(User).filter(User.id == uid).first()
        dossier = dossier_service.build_dossier(db, student)
        assert len(dossier.activities) == 1
        assert dossier.activities[0].name == "Capitana del equipo de vóleibol"
        assert dossier.activities[0].category == "sport"
        assert dossier.activities[0].achievements == ["1er lugar regional 2024"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2b · el snapshot exportable del estudiante también los incluye
# ---------------------------------------------------------------------------


def test_los_logros_llegan_al_snapshot(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "logros.snapshot@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "logros.snapshot@grasshopper.dev")

        r = client.post(
            "/api/v1/me/activities",
            headers=h,
            json={"category": "arts", "name": "Coro del colegio"},
        )
        assert r.status_code == 201, r.text

        sid = client.post("/api/v1/sessions", headers=h).json()["session_id"]

        snap = client.post(f"/api/v1/snapshots/{sid}", headers=h)
        assert snap.status_code == 200, snap.text
        actividades = snap.json()["profile"]["activities"]
        assert len(actividades) == 1
        assert actividades[0]["name"] == "Coro del colegio"
        assert actividades[0]["category"] == "arts"


# ---------------------------------------------------------------------------
# 3 · Recomendación de materias electivas · `electives_service.py`
# ---------------------------------------------------------------------------


class _StubDB:
    """Doble mínimo para `recommend_electives`: sólo necesita `.query(School)`."""

    def __init__(self, school=None):
        self._school = school

    def query(self, *_args, **_kwargs):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = self._school
        return chain


def _user_para_electivas(study_area=None, grade=None, school_id=None):
    return SimpleNamespace(
        onboarding_answers={"study_area": study_area} if study_area else {},
        grade=grade,
        school_id=school_id,
    )


def test_sin_area_de_estudio_no_recomienda_nada():
    from app.services.electives_service import recommend_electives

    out = recommend_electives(_StubDB(), _user_para_electivas())
    assert out["recomendaciones"] == []
    assert "área de estudio" in out["mensaje"]
    assert out["disclaimer"]  # siempre presente, sea cual sea el caso


def test_area_undecided_se_trata_como_ausencia_de_dato():
    """'Todavía no lo sé' es una respuesta legítima · no inventa nada."""
    from app.services.electives_service import recommend_electives

    out = recommend_electives(_StubDB(), _user_para_electivas(study_area="undecided"))
    assert out["recomendaciones"] == []
    assert out["tiene_datos_colegio"] is False


def test_area_conocida_sin_datos_del_colegio_es_general_y_lo_dice():
    from app.services.electives_service import recommend_electives

    out = recommend_electives(
        _StubDB(school=None), _user_para_electivas(study_area="engineering")
    )
    assert out["tiene_datos_colegio"] is False
    assert len(out["recomendaciones"]) > 0
    # No promete: ninguna recomendación puede afirmar True/False sin datos.
    assert all(r["ofrecida_por_colegio"] is None for r in out["recomendaciones"])
    assert "general" in out["mensaje"]


def test_area_conocida_con_colegio_cruza_las_materias_que_ofrece():
    """El ejemplo textual de la clienta: ingeniería + colegio con matemáticas
    avanzadas y cálculo → esas dos salen marcadas como disponibles."""
    from app.services.electives_service import recommend_electives

    school = SimpleNamespace(
        subjects_offered=["Matemáticas avanzadas", "Cálculo diferencial", "Arte"]
    )
    out = recommend_electives(
        _StubDB(school=school),
        _user_para_electivas(study_area="engineering", school_id=uuid.uuid4()),
    )
    assert out["tiene_datos_colegio"] is True
    por_materia = {r["subject"]: r["ofrecida_por_colegio"] for r in out["recomendaciones"]}
    assert por_materia["Matemáticas avanzadas"] is True
    assert por_materia["Cálculo"] is True  # coincide por substring con "Cálculo diferencial"
    # Física/Química no están en lo que ofrece el colegio de este ejemplo.
    assert por_materia["Física"] is False


def test_colegio_con_lista_vacia_no_es_lo_mismo_que_sin_datos():
    """`subjects_offered=[]` (colegio cargó y no tiene ninguna) es distinto de
    `None` (todavía no se cargó) — sólo `None` cae a "general"."""
    from app.services.electives_service import recommend_electives

    school = SimpleNamespace(subjects_offered=[])
    out = recommend_electives(
        _StubDB(school=school),
        _user_para_electivas(study_area="engineering", school_id=uuid.uuid4()),
    )
    assert out["tiene_datos_colegio"] is True
    assert all(r["ofrecida_por_colegio"] is False for r in out["recomendaciones"])


@pytest.mark.parametrize("grade,esperado", [(10, True), (11, True), (9, False), (12, False), (None, False)])
def test_especialmente_util_solo_en_10_y_11(grade, esperado):
    """La clienta: 'útil sobre todo en grado 10 y 11, cuando todavía se pueden
    elegir'. No bloquea otros grados, sólo informa."""
    from app.services.electives_service import recommend_electives

    out = recommend_electives(
        _StubDB(), _user_para_electivas(study_area="health", grade=grade)
    )
    assert out["especialmente_util_ahora"] is esperado


def test_disclaimer_es_fijo_no_depende_del_modelo():
    """Garantía estructural, no una instrucción de prompt: no hay IA en este
    módulo, así que no hay forma de que el disclaimer se le olvide a nadie."""
    from app.services.electives_service import recommend_electives, DISCLAIMER

    out = recommend_electives(
        _StubDB(), _user_para_electivas(study_area="engineering")
    )
    assert out["disclaimer"] == DISCLAIMER
    assert "no es una lista oficial" in DISCLAIMER


# ---------------------------------------------------------------------------
# 3b · el endpoint /me/electives, sobre HTTP real
# ---------------------------------------------------------------------------


def test_endpoint_electivas_feliz(app_with_db):
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "electivas.ok@grasshopper.dev")

    db = SessionLocal()
    try:
        from app.db.models import User

        u = db.query(User).filter(User.id == uid).first()
        u.onboarding_answers = {"study_area": "engineering"}
        u.grade = 10
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        h = _headers(client, "electivas.ok@grasshopper.dev")
        r = client.get("/api/v1/me/electives", headers=h)
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["study_area"] == "engineering"
        assert cuerpo["grade"] == 10
        assert cuerpo["especialmente_util_ahora"] is True
        assert len(cuerpo["recomendaciones"]) > 0
        assert cuerpo["disclaimer"]


def test_endpoint_electivas_cruza_contra_el_colegio(app_with_db):
    """El ejemplo de la clienta de punta a punta: colegio con materias
    cargadas + estudiante de 10° con área declarada."""
    app, SessionLocal = app_with_db

    db = SessionLocal()
    try:
        from app.db.models import School

        school = School(
            name="Colegio Ejemplo",
            slug="colegio-ejemplo-electivas",
            subjects_offered=["Matemáticas avanzadas", "Cálculo", "Geometría avanzada"],
        )
        db.add(school)
        db.commit()
        db.refresh(school)
        school_id = school.id
    finally:
        db.close()

    uid = _student(
        SessionLocal, "electivas.colegio@grasshopper.dev", school_id=school_id, grade=10
    )
    db = SessionLocal()
    try:
        from app.db.models import User

        u = db.query(User).filter(User.id == uid).first()
        u.onboarding_answers = {"study_area": "engineering"}
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        h = _headers(client, "electivas.colegio@grasshopper.dev")
        cuerpo = client.get("/api/v1/me/electives", headers=h).json()
        assert cuerpo["tiene_datos_colegio"] is True
        por_materia = {
            r["subject"]: r["ofrecida_por_colegio"] for r in cuerpo["recomendaciones"]
        }
        assert por_materia["Matemáticas avanzadas"] is True
        assert por_materia["Cálculo"] is True


def test_endpoint_electivas_solo_estudiantes(app_with_db):
    from app.db.models import User, UserRole
    from app.api.v1.auth import get_password_hash

    app, SessionLocal = app_with_db
    db = SessionLocal()
    try:
        advisor = User(
            email="advisor.electivas@grasshopper.dev",
            hashed_password=get_password_hash("testpass123"),
            name="Advisor",
            role=UserRole.GH_ADVISOR,
        )
        db.add(advisor)
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        h = _headers(client, "advisor.electivas@grasshopper.dev")
        r = client.get("/api/v1/me/electives", headers=h)
        assert r.status_code == 403


def test_endpoint_electivas_requiere_login(app_with_db):
    app, _SessionLocal = app_with_db
    with TestClient(app) as client:
        assert client.get("/api/v1/me/electives").status_code in (401, 403)
