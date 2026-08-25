"""La ruta del adulto profesional · auditoría de trayectoria + análisis de brecha.

Lo que protegen estos tests, en orden de importancia:

 1. **No se inventan cifras de salario ni de demanda de mercado.** Fue pedido
    explícitamente ("ya hubo un reclamo del cliente por contenido inventado por
    nosotros") y la garantía es ESTRUCTURAL, no depende de que el modelo
    obedezca el prompt — así que se prueba forzando a un modelo simulado a
    devolver justo eso, y comprobando que no sobrevive.
 2. **El disclaimer de honestidad siempre está**, lo ponga el modelo o no.
 3. Que el análisis funcione de punta a punta sobre HTTP real: guardar
    LinkedIn, guardar la auditoría, pedir el análisis, y que sobreviva a un
    GET posterior — no sólo que el endpoint responda 200.
 4. Que esto quede fuera del alcance de quien es claramente colegio.
 5. El camino incómodo: se mockea la FRONTERA (`app.core.ai_client.get_client`),
    nunca la función que se está probando — mismo patrón que
    `test_cv2_import_linkedin.py`, que documenta por qué importa.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import career_gap_service as cgs


# ---------------------------------------------------------------------------
# Servicio · sin HTTP · mockeando la frontera del SDK
# ---------------------------------------------------------------------------


def _tool_response(tool_input: dict, tokens_in: int = 100, tokens_out: int = 60):
    """Imita lo que devuelve el SDK de Anthropic con tool use forzado."""
    bloque = MagicMock()
    bloque.type = "tool_use"
    bloque.input = tool_input
    resp = MagicMock()
    resp.content = [bloque]
    resp.usage = MagicMock(input_tokens=tokens_in, output_tokens=tokens_out)
    resp.stop_reason = "tool_use"
    return resp


def test_target_role_vacio_no_llama_al_modelo():
    with patch("app.core.ai_client.get_client") as get_client:
        with pytest.raises(cgs.CareerGapError):
            cgs.analizar(perfil_linkedin={}, target_role="  ", session_id="s1")
    get_client.assert_not_called()


def test_analizar_recorre_el_camino_completo():
    tool_input = {
        "resumen": "Tienes bases sólidas pero te falta experiencia específica.",
        "fortalezas_alineadas": ["Experiencia con SQL", "Comunicación"],
        "brechas": [
            {"area": "Python", "descripcion": "No aparece en tu experiencia.", "impacto": "alto"}
        ],
        "plan_upskilling": [
            {
                "brecha": "Python",
                "como_cerrarla": "Un curso introductorio y un proyecto propio.",
                "tipo": "curso",
                "prioridad": "alta",
            }
        ],
    }
    cliente = MagicMock()
    cliente.with_options.return_value.messages.create.return_value = _tool_response(tool_input)

    with patch("app.core.ai_client.get_client", return_value=cliente):
        analisis, meta = cgs.analizar(
            perfil_linkedin={
                "headline": "Analista de datos",
                "strengths": ["SQL"],
                "experience": [{"role": "Analista", "organization": "Acme"}],
            },
            target_role="Data Analyst remoto",
            current_role="Analista",
            job_satisfaction_score=3,
            job_satisfaction_text="Me gustaría más flexibilidad.",
            session_id="s2",
        )

    assert analisis["resumen"].startswith("Tienes bases sólidas")
    assert analisis["brechas"][0]["area"] == "Python"
    assert analisis["plan_upskilling"][0]["tipo"] == "curso"
    assert meta["tokens_input"] == 100
    assert meta["tokens_output"] == 60


def test_el_modulo_del_cliente_de_ia_existe_de_verdad():
    """Mismo test que ya existe en `test_cv2_import_linkedin.py` — el import
    del cliente vive dentro de la función y sólo se toca en la llamada real."""
    from app.core.ai_client import get_client  # noqa: F401


# ---------------------------------------------------------------------------
# La garantía anti-invención · el corazón de la tarea
# ---------------------------------------------------------------------------


def test_el_disclaimer_siempre_esta_lo_diga_o_no_el_modelo():
    salida = cgs.normalizar({"resumen": "ok", "brechas": [], "plan_upskilling": []})
    assert salida["disclaimer"] == cgs.DISCLAIMER
    assert "salario" in salida["disclaimer"].lower()
    assert "demanda" in salida["disclaimer"].lower()


def test_una_cifra_de_salario_inventada_por_el_modelo_no_sobrevive():
    """Si el modelo desobedece el prompt e inventa un salario, la garantía
    estructural de `_redactar_cifras` la quita de todas formas — no depende
    de que el modelo se porte bien."""
    salida = cgs.normalizar(
        {
            "resumen": "Con este perfil podrías ganar $8.500.000 al mes.",
            "brechas": [
                {
                    "area": "Inglés",
                    "descripcion": "Los puestos similares pagan USD 3000.",
                    "impacto": "alto",
                }
            ],
            "plan_upskilling": [
                {"brecha": "Inglés", "como_cerrarla": "Practica 40% más seguido."}
            ],
        }
    )
    texto_completo = (
        salida["resumen"]
        + salida["brechas"][0]["descripcion"]
        + salida["plan_upskilling"][0]["como_cerrarla"]
    )
    assert "$8.500.000" not in texto_completo
    assert "8.500.000" not in texto_completo
    assert "USD 3000" not in texto_completo
    assert "40%" not in texto_completo
    assert "[cifra no disponible]" in salida["resumen"]


def test_no_inventa_demanda_de_mercado_con_porcentaje():
    salida = cgs._redactar_cifras("Este rol crecerá 25% en los próximos años.")
    assert "25%" not in salida
    assert "[dato no disponible]" in salida


def test_cifras_legitimas_de_otro_tipo_no_se_tocan():
    """El scrub es específico a plata y porcentajes, no a cualquier número."""
    salida = cgs._redactar_cifras("Tienes 5 años de experiencia en el área.")
    assert salida == "Tienes 5 años de experiencia en el área."


# ---------------------------------------------------------------------------
# Normalizado · nunca confiar en lo que devuelve el modelo
# ---------------------------------------------------------------------------


def test_brechas_sin_area_se_descartan():
    salida = cgs.normalizar(
        {"brechas": [{"descripcion": "sin area"}, {"area": "SQL"}], "plan_upskilling": []}
    )
    assert len(salida["brechas"]) == 1
    assert salida["brechas"][0]["area"] == "SQL"


def test_impacto_invalido_se_limpia_a_none():
    salida = cgs.normalizar(
        {"brechas": [{"area": "SQL", "impacto": "catastrófico"}], "plan_upskilling": []}
    )
    assert salida["brechas"][0]["impacto"] is None


def test_se_acota_a_seis_items():
    salida = cgs.normalizar(
        {
            "brechas": [{"area": f"brecha {i}"} for i in range(20)],
            "plan_upskilling": [
                {"brecha": f"b{i}", "como_cerrarla": f"paso {i}"} for i in range(20)
            ],
        }
    )
    assert len(salida["brechas"]) <= 6
    assert len(salida["plan_upskilling"]) <= 6


def test_describir_perfil_dice_explicitamente_cuando_no_hay_experiencia():
    """Mismo patrón que `cv_tailor_service`: decirlo explícito evita que el
    modelo asuma que faltó pasarla y se la invente."""
    texto = cgs.describir_perfil_actual({})
    assert "ninguna registrada" in texto.lower()


def test_describir_perfil_incluye_satisfaccion_y_cargo():
    texto = cgs.describir_perfil_actual(
        {"headline": "Analista"},
        current_role="Analista de datos",
        job_satisfaction_score=2,
        job_satisfaction_text="Poco reto técnico.",
    )
    assert "Analista de datos" in texto
    assert "2" in texto
    assert "Poco reto técnico" in texto


# ---------------------------------------------------------------------------
# Endpoints · sobre HTTP real
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


def _student(SessionLocal, email, onboarding_answers=None):
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
            onboarding_answers=onboarding_answers or {},
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


BASE = "/api/v1/me/career-gap"


def _linkedin_ai_response():
    """Lo que devuelve `linkedin_import_service.importar_desde_texto` mockeado
    en la frontera del SDK (mismo patrón que `test_cv2_import_linkedin.py`)."""
    bloque = MagicMock()
    bloque.text = (
        '{"headline": "Analista de datos", "summary": "5 años en analítica.",'
        ' "strengths": ["SQL", "Python"], "interests": ["Datos"],'
        ' "experience": [{"role": "Analista", "organization": "Acme",'
        ' "period": "2021-2024"}], "education": []}'
    )
    resp = MagicMock()
    resp.content = [bloque]
    resp.usage = MagicMock(input_tokens=90, output_tokens=70)
    return resp


def test_perfil_de_colegio_no_puede_usar_esta_ruta(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "colegio@grasshopper.dev",
        onboarding_answers={"life_stage": "high_school"},
    )
    with TestClient(app) as client:
        h = _headers(client, "colegio@grasshopper.dev")
        r = client.get(BASE, headers=h)
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "career_gap_not_for_school"


def test_perfil_desconocido_si_puede_usarla(app_with_db):
    """Postura conservadora: sin `life_stage` todavía, no se bloquea."""
    app, SessionLocal = app_with_db
    _student(SessionLocal, "desconocido@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "desconocido@grasshopper.dev")
        r = client.get(BASE, headers=h)
        assert r.status_code == 200, r.text


def test_perfil_profesional_puede_usarla(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "profesional@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "profesional@grasshopper.dev")
        r = client.get(BASE, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["ready_for_analysis"] is False


def test_guardar_audit_a_medias_y_volver_despues(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "audit@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "audit@grasshopper.dev")
        client.put(f"{BASE}/audit", headers=h, json={"current_role": "Analista"})
        r = client.put(
            f"{BASE}/audit", headers=h,
            json={"job_satisfaction_score": 2, "target_role": "Data Analyst remoto"},
        )
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        # El segundo PUT no borró lo del primero
        assert cuerpo["current_role"] == "Analista"
        assert cuerpo["job_satisfaction_score"] == 2
        assert cuerpo["target_role"] == "Data Analyst remoto"
        assert cuerpo["answered"] is True


def test_score_fuera_de_rango_se_rechaza(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "score@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "score@grasshopper.dev")
        r = client.put(f"{BASE}/audit", headers=h, json={"job_satisfaction_score": 7})
        assert r.status_code == 422


def test_guardar_linkedin_persiste_y_estructura(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "linkedin@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    cliente = MagicMock()
    cliente.with_options.return_value.messages.create.return_value = (
        _linkedin_ai_response()
    )
    with TestClient(app) as client:
        h = _headers(client, "linkedin@grasshopper.dev")
        with patch("app.core.ai_client.get_client", return_value=cliente):
            r = client.put(
                f"{BASE}/linkedin", headers=h,
                json={"profile_text": "Analista de datos con 5 años de experiencia. " * 3},
            )
        assert r.status_code == 200, r.text
        assert r.json()["proposal"]["headline"] == "Analista de datos"

        # Sobrevive a un GET posterior
        r2 = client.get(BASE, headers=h)
        assert r2.json()["linkedin_profile"]["headline"] == "Analista de datos"
        assert r2.json()["audit"]["has_linkedin_profile"] is True


def test_texto_de_linkedin_demasiado_corto_no_llama_al_modelo(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "corto@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "corto@grasshopper.dev")
        with patch("app.core.ai_client.get_client") as get_client:
            r = client.put(f"{BASE}/linkedin", headers=h, json={"profile_text": "hola"})
        get_client.assert_not_called()
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "linkedin_import_failed"


def test_analizar_sin_datos_da_409_con_lo_que_falta(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "incompleto@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "incompleto@grasshopper.dev")
        r = client.post(f"{BASE}/analyze", headers=h)
        assert r.status_code == 409
        cuerpo = r.json()["detail"]
        assert cuerpo["code"] == "career_gap_incomplete"
        assert "linkedin_profile" in cuerpo["missing"]
        assert "target_role" in cuerpo["missing"]


def test_flujo_completo_de_punta_a_punta(app_with_db):
    """El camino real: LinkedIn + auditoría + análisis, y que sobreviva a un
    GET posterior — el test que de verdad importa en este archivo."""
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "completo@grasshopper.dev",
        onboarding_answers={"life_stage": "career_change"},
    )
    cliente_linkedin = MagicMock()
    cliente_linkedin.with_options.return_value.messages.create.return_value = (
        _linkedin_ai_response()
    )

    with TestClient(app) as client:
        h = _headers(client, "completo@grasshopper.dev")

        with patch("app.core.ai_client.get_client", return_value=cliente_linkedin):
            r = client.put(
                f"{BASE}/linkedin", headers=h,
                json={"profile_text": "Analista de datos con 5 años de experiencia. " * 3},
            )
        assert r.status_code == 200, r.text

        client.put(
            f"{BASE}/audit", headers=h,
            json={
                "current_role": "Analista",
                "job_satisfaction_score": 2,
                "job_satisfaction_text": "Quiero más reto técnico.",
                "target_role": "Data Analyst remoto en una fintech",
            },
        )

        assert client.get(BASE, headers=h).json()["ready_for_analysis"] is True

        tool_input = {
            "resumen": "Vas por buen camino, con dos brechas claras.",
            "fortalezas_alineadas": ["Experiencia analizando datos"],
            "brechas": [
                {"area": "Python", "descripcion": "No aparece en tu perfil.", "impacto": "alto"}
            ],
            "plan_upskilling": [
                {
                    "brecha": "Python",
                    "como_cerrarla": "Un curso base y un proyecto propio.",
                    "tipo": "curso",
                    "prioridad": "alta",
                }
            ],
        }
        cliente_analisis = MagicMock()
        cliente_analisis.with_options.return_value.messages.create.return_value = _tool_response(tool_input)
        with patch("app.core.ai_client.get_client", return_value=cliente_analisis):
            r = client.post(f"{BASE}/analyze", headers=h)
        assert r.status_code == 200, r.text
        analisis = r.json()["analysis"]
        assert analisis["resumen"] == tool_input["resumen"]
        assert analisis["disclaimer"]

        # Sobrevive a un GET posterior
        r2 = client.get(BASE, headers=h)
        assert r2.json()["analysis"]["resumen"] == tool_input["resumen"]
        assert r2.json()["analysis_generated_at"]


# ---------------------------------------------------------------------------
# GET /me/professional/gap-analysis · GET /me/professional/upskilling-plan
#
# El contrato que ya consume `journey-compass/src/lib/professionalApi.ts` —
# construido por otro agente en paralelo sin backend detrás. Estos endpoints
# son de sólo lectura sobre el MISMO análisis que arriba (no llaman IA, no
# agregan lógica) así que se prueban por HTTP real, sin mockear nada más que
# lo que ya mockea el flujo de punta a punta.
# ---------------------------------------------------------------------------

PROFESSIONAL_BASE = "/api/v1/me/professional"


def _analisis_guardado() -> dict:
    return {
        "resumen": "Vas por buen camino, con dos brechas claras.",
        "fortalezas_alineadas": ["Experiencia analizando datos"],
        "brechas": [
            {"area": "Python", "descripcion": "No aparece en tu perfil.", "impacto": "alto"}
        ],
        "plan_upskilling": [
            {
                "brecha": "Python",
                "como_cerrarla": "Un curso base y un proyecto propio.",
                "tipo": "curso",
                "prioridad": "alta",
            }
        ],
        "disclaimer": cgs.DISCLAIMER,
    }


def test_gap_analysis_view_404_sin_analisis_todavia(app_with_db):
    """El frontend trata el 404 como 'todavía no hay datos', no como error
    (`useProfessionalResource` en `ProfessionalHomePanel.tsx`) — por eso el
    código NO puede ser un 200 con listas vacías."""
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "sin-analisis@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "sin-analisis@grasshopper.dev")
        r = client.get(f"{PROFESSIONAL_BASE}/gap-analysis", headers=h)
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "career_gap_not_analyzed"

        r2 = client.get(f"{PROFESSIONAL_BASE}/upskilling-plan", headers=h)
        assert r2.status_code == 404


def test_gap_analysis_view_bloqueada_para_colegio(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "colegio-panel@grasshopper.dev",
        onboarding_answers={"life_stage": "high_school"},
    )
    with TestClient(app) as client:
        h = _headers(client, "colegio-panel@grasshopper.dev")
        r = client.get(f"{PROFESSIONAL_BASE}/gap-analysis", headers=h)
        assert r.status_code == 403


def test_gap_analysis_view_refleja_lo_ya_calculado(app_with_db):
    """No llama IA ni recalcula: lee lo que dejó `POST /me/career-gap/analyze`
    y lo traduce al shape que declara `GapAnalysis` en `types/upskilling.ts`
    del frontend — `resumen`→`summary`, `brechas`→`gaps`, tal cual, SIN
    inventar `current_level`/`target_level` (esa parte de la propuesta
    original del frontend no sobrevivió: no hay dato real de qué nivel tiene
    cada habilidad, sólo un `impacto`)."""
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "con-analisis@grasshopper.dev",
        onboarding_answers={
            "life_stage": "working",
            "career_current_role": "Analista",
            "career_target_role": "Data Analyst remoto",
            "career_gap_analysis": _analisis_guardado(),
            "career_gap_analysis_generated_at": "2026-08-24T10:00:00+00:00",
        },
    )
    with TestClient(app) as client:
        h = _headers(client, "con-analisis@grasshopper.dev")
        r = client.get(f"{PROFESSIONAL_BASE}/gap-analysis", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["current_role"] == "Analista"
        assert body["target_role"] == "Data Analyst remoto"
        assert body["summary"] == "Vas por buen camino, con dos brechas claras."
        assert body["gaps"] == [
            {"area": "Python", "descripcion": "No aparece en tu perfil.", "impacto": "alto"}
        ]
        assert "current_level" not in body["gaps"][0]
        assert body["disclaimer"] == cgs.DISCLAIMER
        assert body["generated_at"] == "2026-08-24T10:00:00+00:00"


def test_upskilling_plan_view_refleja_lo_ya_calculado(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "con-plan@grasshopper.dev",
        onboarding_answers={
            "life_stage": "working",
            "career_gap_analysis": _analisis_guardado(),
            "career_gap_analysis_generated_at": "2026-08-24T10:00:00+00:00",
        },
    )
    with TestClient(app) as client:
        h = _headers(client, "con-plan@grasshopper.dev")
        r = client.get(f"{PROFESSIONAL_BASE}/upskilling-plan", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["headline"] == "Vas por buen camino, con dos brechas claras."
        assert body["steps"] == [
            {
                "brecha": "Python",
                "como_cerrarla": "Un curso base y un proyecto propio.",
                "tipo": "curso",
                "prioridad": "alta",
            }
        ]


def test_upskilling_plan_view_404_si_el_analisis_no_trae_plan(app_with_db):
    """Defensivo: un análisis viejo o incompleto sin `plan_upskilling` se lee
    igual que 'no hay nada' — nunca se muestra un plan vacío como si fuera
    real."""
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "analisis-sin-plan@grasshopper.dev",
        onboarding_answers={
            "life_stage": "working",
            "career_gap_analysis": {"resumen": "x", "brechas": [], "plan_upskilling": []},
        },
    )
    with TestClient(app) as client:
        h = _headers(client, "analisis-sin-plan@grasshopper.dev")
        r = client.get(f"{PROFESSIONAL_BASE}/upskilling-plan", headers=h)
        assert r.status_code == 404


def test_panel_profesional_de_punta_a_punta_via_analyze(app_with_db):
    """El camino real completo: analizar y LUEGO leer por las rutas del
    panel — no sólo sembrar el dato directo en la base, como los tests de
    arriba (que prueban la traducción de forma aislada)."""
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "e2e-panel@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        h = _headers(client, "e2e-panel@grasshopper.dev")
        client.put(
            f"{BASE}/audit", headers=h,
            json={"target_role": "Data Analyst remoto en una fintech"},
        )
        # `analyze` exige perfil de LinkedIn · lo sembramos directo en la
        # respuesta guardada (ya probado en `test_flujo_completo_de_punta_a_punta`
        # que `PUT .../linkedin` lo persiste igual).
        db = SessionLocal()
        try:
            from app.db.models import User
            u = db.query(User).filter(User.email == "e2e-panel@grasshopper.dev").first()
            u.onboarding_answers = {
                **u.onboarding_answers,
                "career_linkedin_profile": {"headline": "Analista"},
            }
            db.commit()
        finally:
            db.close()

        tool_input = {
            "resumen": "Resumen del análisis real.",
            "fortalezas_alineadas": [],
            "brechas": [{"area": "SQL avanzado", "impacto": "medio"}],
            "plan_upskilling": [
                {"brecha": "SQL avanzado", "como_cerrarla": "Certificación.", "tipo": "certificacion"}
            ],
        }
        cliente = MagicMock()
        cliente.with_options.return_value.messages.create.return_value = _tool_response(tool_input)
        with patch("app.core.ai_client.get_client", return_value=cliente):
            r = client.post(f"{BASE}/analyze", headers=h)
        assert r.status_code == 200, r.text

        gap = client.get(f"{PROFESSIONAL_BASE}/gap-analysis", headers=h)
        assert gap.status_code == 200, gap.text
        assert gap.json()["summary"] == "Resumen del análisis real."

        plan = client.get(f"{PROFESSIONAL_BASE}/upskilling-plan", headers=h)
        assert plan.status_code == 200, plan.text
        assert plan.json()["steps"][0]["brecha"] == "SQL avanzado"


def test_cada_quien_ve_solo_lo_suyo(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "ana.cg@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    _student(
        SessionLocal, "beto.cg@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        ha = _headers(client, "ana.cg@grasshopper.dev")
        client.put(f"{BASE}/audit", headers=ha, json={"target_role": "CTO"})

        hb = _headers(client, "beto.cg@grasshopper.dev")
        assert client.get(BASE, headers=hb).json()["audit"]["target_role"] is None


def test_sin_sesion_no_se_puede_leer_ni_escribir(app_with_db):
    app, SessionLocal = app_with_db
    _student(
        SessionLocal, "priv.cg@grasshopper.dev",
        onboarding_answers={"life_stage": "working"},
    )
    with TestClient(app) as client:
        assert client.get(BASE).status_code in (401, 403)
        assert client.put(f"{BASE}/audit", json={"target_role": "x"}).status_code in (401, 403)
        assert client.post(f"{BASE}/analyze").status_code in (401, 403)


def test_el_registro_de_consumo_de_ia_acepta_los_argumentos_que_le_pasamos():
    """Mismo test-fijador que ya existe para CV-2 · evita el bug real de
    `record_ai_usage` tragándose un `TypeError` por `provider` faltante."""
    import inspect

    from app.services.ai_usage_service import record_ai_usage

    firma = inspect.signature(record_ai_usage)
    obligatorios = {
        nombre
        for nombre, p in firma.parameters.items()
        if p.default is inspect.Parameter.empty and nombre != "db"
    }
    pasados = {
        "provider", "user_id", "feature", "model",
        "tokens_input", "tokens_output", "latency_ms",
    }
    faltantes = obligatorios - pasados
    assert not faltantes, f"los endpoints no pasan argumentos obligatorios: {faltantes}"
