"""Las tres mini apps de "Herramientas" (2026-08-25).

JP en la reunión del 24-08 (13:48): *"ya salieron tres, hoja de vida,
postulación a trabajo, postulación a la universidad... armamos así como unas
mini apps"*.

Lo que protegen estos tests, en orden de importancia:

 1. **El disclaimer de los detectores de IA siempre está.** Lo pidió la clienta
    textualmente (13:14) y por eso no depende de que el modelo se acuerde: lo
    pone `normalizar()` pase lo que pase.
 2. **Nada inventado sobrevive.** Si el modelo cuela un salario, un porcentaje
    o un ranking, la garantía estructural lo convierte en un corchete Y en un
    pendiente visible. Se prueba forzando a un modelo simulado a desobedecer.
 3. **Lo que no cumple va aparte del mensaje**, nunca maquillado dentro.
 4. **España y Colombia son formatos de verdad**, con diferencias que se ven en
    el documento — y el Word dice lo mismo que el PDF.
 5. El camino completo sobre HTTP: 409 cuando no hay insumos, 200 cuando sí, y
    el consumo de IA registrado.

## Qué se mockea y por qué

**La frontera: `app.core.ai_client.get_client`**, o sea el SDK de Anthropic.
Nunca `sop_service.escribir` ni `job_pitch_service.redactar`, que son justo lo
que se prueba. Es la regla que este repo aprendió a golpes el 05-08 (once tests
en verde con la funcionalidad rota al 100%). Prueba de que se cumple: estos
tests recorren `normalizar()` de verdad, así que si el esquema del tool cambia,
fallan aquí.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import cv_variants, job_pitch_service, sop_service
from app.services import tools_guardrails as guard
from app.services.cv_docx_service import render_cv_docx
from app.services.cv_pdf_service import CVActivity, CVData, render_cv_html


# ---------------------------------------------------------------------------
# Dobles · la frontera del SDK
# ---------------------------------------------------------------------------


def _tool_response(tool_input: dict, tokens_in: int = 120, tokens_out: int = 400):
    """Imita lo que devuelve el SDK con tool use forzado."""
    bloque = MagicMock()
    bloque.type = "tool_use"
    bloque.input = tool_input
    resp = MagicMock()
    resp.content = [bloque]
    resp.usage = MagicMock(input_tokens=tokens_in, output_tokens=tokens_out)
    resp.stop_reason = "tool_use"
    return resp


def _cliente(tool_input: dict):
    cliente = MagicMock()
    cliente.with_options.return_value.messages.create.return_value = _tool_response(
        tool_input
    )
    return cliente


def _cv(**extra) -> CVData:
    datos = dict(
        student_name="Ana Perez",
        generated_on="25 de agosto de 2026",
        email="ana@example.com",
        english_level="B2",
        summary="Estudiante de once con interes en ingenieria.",
        strengths=["Liderazgo"],
        interests=["Ciencia"],
        test_highlights=[("Holland", "RIA", "Realista", "holland")],
        activities=[
            CVActivity(
                category_label="Deporte",
                name="Natacion",
                role="Capitana",
                achievements=["1er lugar regional 2024"],
            )
        ],
    )
    datos.update(extra)
    return CVData(**datos)


_SOP_OK = {
    "parrafos": [
        "El primer parrafo cuenta un hecho concreto de su trayectoria.",
        "El segundo habla de lo que hizo en natacion como capitana.",
        "Me interesa [completa aqui: el nombre de un curso del programa].",
        "Y esto es lo que quiero hacer despues de graduarme.",
    ],
    "puntos_usados": ["Capitana del equipo de natacion", "Holland: RIA"],
    "que_debes_completar": ["El nombre de un curso del programa"],
}


# ===========================================================================
# 1 · Statement of Purpose
# ===========================================================================


class TestStatementOfPurpose:
    def test_sin_universidad_no_se_gasta_una_llamada(self):
        """El límite se comprueba ANTES del modelo · si no, cada intento cuesta."""
        with patch("app.core.ai_client.get_client") as get_client:
            with pytest.raises(sop_service.SOPError):
                sop_service.escribir(
                    cv=_cv(), universidad="", programa="Ingenieria", session_id="s"
                )
        get_client.assert_not_called()

    def test_sin_nada_del_estudiante_no_se_escribe_el_ensayo(self):
        """Un ensayo sin insumos sería invención pura · preferimos no generarlo."""
        vacio = CVData(student_name="Ana", generated_on="hoy")

        with patch("app.core.ai_client.get_client") as get_client:
            with pytest.raises(sop_service.SOPError):
                sop_service.escribir(
                    cv=vacio,
                    universidad="Manchester",
                    programa="Ingenieria",
                    session_id="s",
                )
        get_client.assert_not_called()

    def test_recorre_el_camino_completo(self):
        cliente = _cliente(_SOP_OK)

        with patch("app.core.ai_client.get_client", return_value=cliente):
            sop, meta = sop_service.escribir(
                cv=_cv(),
                universidad="University of Manchester",
                programa="BSc Mechanical Engineering",
                pais="Reino Unido",
                motivacion="Quiero disenar protesis.",
                session_id="s1",
            )

        assert sop["universidad"] == "University of Manchester"
        assert len(sop["parrafos"]) == 4
        assert sop["texto"].startswith("El primer parrafo")
        assert meta["tokens_output"] == 400

    def test_el_perfil_real_llega_al_prompt(self):
        """Que 'ya tienes mi hoja de vida' sea cierto y no una promesa del copy.

        Si esto fallara, el ensayo se estaría escribiendo sobre nada — el error
        nº1 del CLAUDE.md (leer un dato que nadie escribe) en su peor versión.
        """
        cliente = _cliente(_SOP_OK)

        with patch("app.core.ai_client.get_client", return_value=cliente):
            sop_service.escribir(
                cv=_cv(),
                universidad="Manchester",
                programa="Ingenieria",
                session_id="s1",
            )

        enviado = cliente.with_options.return_value.messages.create.call_args.kwargs
        prompt = enviado["messages"][0]["content"]
        assert "Natacion" in prompt          # su actividad
        assert "1er lugar regional 2024" in prompt  # su logro (F-001)
        assert "Holland" in prompt           # su test
        assert "Manchester" in prompt        # a dónde se postula

    def test_el_disclaimer_de_los_detectores_siempre_esta(self):
        """Petición literal de la clienta (13:14) · no depende del modelo."""
        salida = sop_service.normalizar(
            {"parrafos": ["texto"]},
            universidad="Manchester",
            programa="Ingenieria",
            pais=None,
            idioma="es",
        )

        assert salida["disclaimer"] == sop_service.DISCLAIMER
        # Tiene que decir QUÉ hacer y POR QUÉ, no un "revísalo" a secas.
        assert "detecta texto generado por IA" in salida["disclaimer"]
        assert "Reescríbelo" in salida["disclaimer"]
        assert salida["como_usarlo"]

    def test_un_ranking_inventado_por_el_modelo_no_sobrevive(self):
        """La garantía es estructural: si el modelo desobedece el prompt e
        inventa una cifra, `redactar_cifras` la quita igual — y el hueco que
        deja aparece como pendiente, no se pierde dentro del párrafo."""
        salida = sop_service.normalizar(
            {
                "parrafos": [
                    "Su programa esta en el top 5% de Europa y cuesta $30.000 al ano."
                ]
            },
            universidad="Manchester",
            programa="Ingenieria",
            pais=None,
            idioma="es",
        )

        texto = salida["texto"]
        assert "5%" not in texto
        assert "$30.000" not in texto
        assert guard.MARCADOR_CIFRA in texto
        # El circuito cerrado: la cifra redactada sale como pendiente visible.
        assert any("completa" in p.lower() for p in salida["que_debes_completar"])

    def test_los_corchetes_del_texto_entran_a_la_lista_aunque_no_los_declare(self):
        """El texto manda sobre la memoria del modelo."""
        salida = sop_service.normalizar(
            {
                "parrafos": ["Quiero trabajar con [completa aqui: un profesor]."],
                "que_debes_completar": [],
            },
            universidad="Manchester",
            programa="Ingenieria",
            pais=None,
            idioma="es",
        )

        assert salida["que_debes_completar"] == ["completa aqui: un profesor"]

    def test_las_palabras_las_cuenta_python_no_el_modelo(self):
        """Los límites de palabras de una convocatoria son duros."""
        salida = sop_service.normalizar(
            {"parrafos": ["una dos tres", "cuatro cinco"]},
            universidad="U",
            programa="P",
            pais=None,
            idioma="es",
        )

        assert salida["palabras"] == 5

    def test_el_idioma_invalido_cae_a_espanol(self):
        assert sop_service.normalizar_idioma("klingon") == "es"
        assert sop_service.normalizar_idioma("EN") == "en"

    def test_si_el_modelo_falla_el_mensaje_es_para_el_estudiante(self):
        cliente = MagicMock()
        cliente.with_options.return_value.messages.create.side_effect = RuntimeError(
            "la API se cayó"
        )

        with patch("app.core.ai_client.get_client", return_value=cliente):
            with pytest.raises(sop_service.SOPError) as exc:
                sop_service.escribir(
                    cv=_cv(),
                    universidad="Manchester",
                    programa="Ingenieria",
                    session_id="s",
                )

        assert "la API se cayó" not in str(exc.value)

    def test_el_modulo_del_cliente_de_ia_existe_de_verdad(self):
        """El import vive dentro de la función y sólo se toca en la llamada
        real · mismo test que en `test_cv2_import_linkedin.py`."""
        from app.core.ai_client import call_claude_tool, load_prompt  # noqa: F401

        assert load_prompt("sop_universidad")
        assert load_prompt("job_pitch")


# ===========================================================================
# 2 · Copy para postularse a un trabajo
# ===========================================================================


_PITCH_OK = {
    "asunto": "Postulacion a Analista de Datos",
    "parrafos": [
        "Escribo para postularme a la vacante de Analista de Datos.",
        "En Acme trabaje con SQL durante dos anos.",
    ],
    "requisitos_detectados": ["SQL", "Ingles B2"],
    "puntos_usados": ["Analista en Acme"],
    "no_cumples": [{"que": "Ingles B2", "que_hacer": "Presenta un examen de nivel."}],
}

_VACANTE = (
    "Buscamos Analista de Datos con experiencia en SQL y Python. "
    "Requisitos: dos anos de experiencia, ingles B2, manejo de dashboards. "
    "Ofrecemos contrato a termino indefinido y trabajo hibrido en Medellin."
)


class TestPostulacionTrabajo:
    def test_una_vacante_muy_corta_no_gasta_llamada(self):
        with patch("app.core.ai_client.get_client") as get_client:
            with pytest.raises(job_pitch_service.JobPitchError):
                job_pitch_service.redactar(
                    vacante="hola", perfil="x", session_id="s"
                )
        get_client.assert_not_called()

    def test_recorre_el_camino_completo(self):
        cliente = _cliente(_PITCH_OK)

        with patch("app.core.ai_client.get_client", return_value=cliente):
            pitch, meta = job_pitch_service.redactar(
                vacante=_VACANTE,
                perfil="Analista en Acme",
                formato="correo",
                session_id="s",
            )

        assert pitch["formato"] == "correo"
        assert pitch["asunto"] == "Postulacion a Analista de Datos"
        assert pitch["requisitos_detectados"] == ["SQL", "Ingles B2"]
        assert meta["tokens_input"] == 120

    def test_lo_que_no_cumple_va_aparte_y_nunca_dentro_del_mensaje(self):
        """La misma garantía estructural que los `faltantes` del CV: separado
        del texto, para que no se maquille dentro."""
        salida = job_pitch_service.normalizar(
            _PITCH_OK, formato=job_pitch_service.obtener_formato("correo")
        )

        assert salida["no_cumples"][0]["que"] == "Ingles B2"
        assert "Ingles B2" not in salida["texto"]

    def test_un_salario_inventado_no_sobrevive(self):
        salida = job_pitch_service.normalizar(
            {"parrafos": ["Mi pretension salarial es de $9.000.000 mensuales."]},
            formato=job_pitch_service.obtener_formato("mensaje"),
        )

        assert "9.000.000" not in salida["texto"]
        assert salida["que_debes_completar"]

    def test_el_formato_mensaje_no_lleva_asunto(self):
        """No es cosmético: un mensaje de LinkedIn no tiene dónde ponerlo."""
        salida = job_pitch_service.normalizar(
            _PITCH_OK, formato=job_pitch_service.obtener_formato("mensaje")
        )

        assert salida["asunto"] is None
        assert salida["limite_caracteres"] == 700

    def test_un_formato_inventado_cae_al_por_defecto(self):
        assert job_pitch_service.obtener_formato("telepatia").clave == "mensaje"

    def test_el_disclaimer_siempre_esta(self):
        salida = job_pitch_service.normalizar(
            {"parrafos": ["hola"]},
            formato=job_pitch_service.obtener_formato("mensaje"),
        )

        assert salida["disclaimer"] == job_pitch_service.DISCLAIMER

    def test_reusa_el_perfil_de_linkedin_y_la_brecha_que_ya_existen(self):
        """No se reescribió el import de LinkedIn ni el análisis de brecha:
        se serializan con `career_gap_service.describir_perfil_actual`."""
        texto = job_pitch_service.describir_perfil(
            perfil_linkedin={
                "headline": "Analista de datos",
                "experience": [{"role": "Analista", "organization": "Acme"}],
            },
            current_role="Analista senior",
            gap_analysis={
                "resumen": "Buen encaje.",
                "fortalezas_alineadas": ["SQL"],
                "brechas": [{"area": "Python"}],
            },
            cv=_cv(),
        )

        assert "Analista senior" in texto
        assert "Acme" in texto
        assert "SQL" in texto
        assert "Natacion" in texto  # la hoja de vida también entra

    def test_las_brechas_no_entran_al_prompt(self):
        """Lo que le FALTA no es material para el texto con el que se presenta:
        si entrara, el modelo escribe 'estoy trabajando en mi Python' sin que
        nadie se lo haya pedido."""
        texto = job_pitch_service.describir_perfil(
            gap_analysis={
                "resumen": "Buen encaje.",
                "fortalezas_alineadas": ["SQL"],
                "brechas": [{"area": "Python", "descripcion": "No aparece."}],
            }
        )

        assert "SQL" in texto
        assert "Python" not in texto

    def test_sin_ningun_dato_lo_dice_explicitamente(self):
        """Mismo patrón que `cv_tailor_service`: decirlo evita que el modelo
        asuma que faltó pasarlo y se lo invente."""
        assert "no hay ningún dato" in job_pitch_service.describir_perfil().lower()

    def test_hay_con_que_postularse_acepta_linkedin_o_cv(self):
        vacio = CVData(student_name="Ana", generated_on="hoy")

        assert job_pitch_service.hay_con_que_postularse(perfil_linkedin={"headline": "x"})
        assert job_pitch_service.hay_con_que_postularse(cv=_cv())
        assert not job_pitch_service.hay_con_que_postularse(cv=vacio)


# ===========================================================================
# 3 · Hoja de vida por país
# ===========================================================================


class TestHojaDeVidaPorPais:
    def test_colombia_es_un_alias_del_estandar_que_ya_existia(self):
        """La clienta pidió "la que se usa en Colombia" · esa convención ya
        estaba implementada como `latam`, así que se le puso nombre en vez de
        duplicar la entrada campo por campo."""
        assert cv_variants.obtener_estandar("colombia").clave == "latam"
        assert "Colombia" in cv_variants.obtener_estandar("colombia").nombre
        # Y el alias NO ensucia el catálogo que ve la pantalla.
        claves = {e["clave"] for e in cv_variants.catalogo()["estandares"]}
        assert "colombia" not in claves

    def test_espana_existe_con_su_propia_politica(self):
        est = cv_variants.obtener_estandar("espana")

        assert est.clave == "espana"
        assert cv_variants.obtener_estandar("españa").clave == "espana"
        assert est.aviso_legal  # la cláusula RGPD

    def test_espana_imprime_la_clausula_de_proteccion_de_datos(self):
        """Es costumbre allá desde el RGPD · en Colombia no se usa."""
        html_es = render_cv_html(_cv(), estandar="espana")
        html_co = render_cv_html(_cv(), estandar="colombia")

        # Se busca la cláusula, no la sigla: "RGPD" también aparece en el
        # comentario del CSS y el test pasaría sin que se imprima nada.
        assert "Autorizo el tratamiento" in html_es
        assert "Autorizo el tratamiento" not in html_co

    def test_espana_saca_los_idiomas_a_su_propia_seccion(self):
        html = render_cv_html(_cv(), estandar="espana")

        assert "<h2>Idiomas</h2>" in html
        assert "MCER" in html
        # Y deja de repetirlos en el encabezado: el mismo dato dos veces en dos
        # páginas se lee como descuido.
        assert "Inglés: <b>B2</b>" not in html

    def test_colombia_deja_el_idioma_en_el_encabezado(self):
        html = render_cv_html(_cv(), estandar="colombia")

        assert "<h2>Idiomas</h2>" not in html
        assert "Inglés: <b>B2</b>" in html

    def test_espana_manda_los_tests_al_final(self):
        """No son parte de la convención española · salen, pero no abren."""
        html = render_cv_html(_cv(), estandar="espana")

        assert html.index(">Actividades extracurriculares<") < html.index(
            ">Resultados de tests<"
        )

    def test_sin_nivel_de_ingles_la_seccion_no_se_pinta_vacia(self):
        """No se inventa el nivel de ningún idioma que no hayamos medido."""
        html = render_cv_html(_cv(english_level=None), estandar="espana")

        assert "<h2>Idiomas</h2>" not in html

    def test_el_word_dice_lo_mismo_que_el_pdf(self):
        """Si divergieran, el estudiante se baja dos documentos distintos
        creyendo que son el mismo (el bug P0-8, en otra capa)."""
        from docx import Document
        import io as _io

        blob = render_cv_docx(_cv(), estandar="espana")
        doc = Document(_io.BytesIO(blob))
        texto = "\n".join(p.text for p in doc.paragraphs)

        # Los títulos del Word van en mayúsculas (`_titulo`).
        assert "IDIOMAS" in texto
        assert "MCER" in texto
        assert "Autorizo el tratamiento" in texto
        # Y el encabezado tampoco repite el idioma · igual que en el PDF.
        assert "Inglés: B2" not in texto

    def test_lo_que_ya_estaba_impreso_no_cambia(self):
        """`latam` sigue siendo el por defecto y sale exactamente igual que
        antes de que existieran España y la sección de idiomas."""
        cv = _cv()

        assert render_cv_html(cv) == render_cv_html(cv, estandar="latam")
        assert "<h2>Idiomas</h2>" not in render_cv_html(cv)
        assert cv_variants.ESTANDAR_POR_DEFECTO == "latam"

    def test_europass_ya_cumple_lo_que_su_nota_prometia(self):
        """Su `nota` decía desde el primer día que el nivel de idioma es una
        sección esperada · la sección no existía. Ahora sí."""
        est = cv_variants.ESTANDARES["europass"]

        assert "idioma" in est.nota.lower()
        assert "<h2>Idiomas</h2>" in render_cv_html(_cv(), estandar="europass")

    def test_toda_seccion_declarada_sabe_pintarse_en_los_dos_renderizadores(self):
        """El paso 2 del "cómo se agrega otro país": si una sección se declara
        en un estándar y falta en un renderizador, desaparece EN SILENCIO."""
        from app.services.cv_docx_service import _SECCIONES as DOCX
        from app.services.cv_pdf_service import _SECCIONES as PDF

        for est in cv_variants.ESTANDARES.values():
            for clave in est.orden_secciones:
                assert clave in PDF, f"{est.clave} · {clave} no está en el PDF"
                assert clave in DOCX, f"{est.clave} · {clave} no está en el Word"
                assert clave in cv_variants.SECCIONES_VALIDAS

    def test_un_estandar_inventado_sigue_sin_dejar_a_nadie_sin_cv(self):
        assert cv_variants.obtener_estandar("atlantida").clave == "latam"
        assert cv_variants.canonico("atlantida") is None
        assert cv_variants.canonico("colombia") == "latam"


# ===========================================================================
# 4 · Los endpoints, sobre HTTP real
# ===========================================================================


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


def _estudiante(SessionLocal, email="ana@example.com", con_actividad=True, answers=None):
    from app.api.v1.auth import get_password_hash
    from app.db.models import (
        ExtracurricularActivity,
        OnboardingStatus,
        User,
        UserRole,
    )

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Ana Perez",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
            onboarding_answers=answers or {},
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        if con_actividad:
            # Los "logros del estudiante" que pidió la clienta ya existen desde
            # F-001 · esto comprueba que la herramienta los usa, no otra tabla.
            db.add(
                ExtracurricularActivity(
                    user_id=u.id,
                    category="sport",
                    name="Natacion",
                    role="Capitana",
                    achievements=["1er lugar regional 2024"],
                )
            )
            db.commit()
        return u.id
    finally:
        db.close()


def _auth(client, email="ana@example.com"):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


BASE = "/api/v1/me/tools"


class TestEndpoints:
    def test_el_indice_lista_las_tres_mini_apps(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)

        r = client.get(BASE, headers=_auth(client))

        assert r.status_code == 200, r.text
        claves = [h["clave"] for h in r.json()["herramientas"]]
        assert claves == [
            "statement_of_purpose",
            "postulacion_trabajo",
            "hoja_de_vida_por_pais",
        ]

    def test_el_indice_ofrece_espana_como_opcion_de_hoja_de_vida(self, app_with_db):
        """El pedido de la clienta, visible desde la sección Herramientas."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)

        r = client.get(BASE, headers=_auth(client))

        cv_tool = r.json()["herramientas"][2]
        nombres = {o["nombre"] for o in cv_tool["opciones"]}
        assert "España" in nombres
        assert any("Colombia" in n for n in nombres)

    def test_el_indice_avisa_cuando_falta_algo(self, app_with_db):
        """Lo que la pantalla dice que falta es lo mismo que el endpoint exige:
        un botón habilitado que devuelve 409 es el bug clásico de aquí."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, con_actividad=False)
        client = TestClient(app)
        auth = _auth(client)

        indice = client.get(BASE, headers=auth).json()["herramientas"][0]
        assert indice["disponible"] is False
        assert indice["que_falta"]

        r = client.post(
            f"{BASE}/statement-of-purpose",
            headers=auth,
            json={"universidad": "Manchester", "programa": "Ingenieria"},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "sop_sin_insumos"

    def test_el_sop_de_punta_a_punta_y_deja_el_consumo_registrado(self, app_with_db):
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        client = TestClient(app)
        cliente = _cliente(_SOP_OK)

        with patch("app.core.ai_client.get_client", return_value=cliente):
            r = client.post(
                f"{BASE}/statement-of-purpose",
                headers=_auth(client),
                json={
                    "universidad": "University of Manchester",
                    "programa": "BSc Mechanical Engineering",
                    "pais": "Reino Unido",
                    "idioma": "en",
                },
            )

        assert r.status_code == 200, r.text
        datos = r.json()
        assert datos["idioma"] == "en"
        assert datos["disclaimer"] == sop_service.DISCLAIMER
        assert datos["que_debes_completar"]

        # M-001 · el consumo queda auditado.
        from app.db.models import AIUsageLog

        db = SessionLocal()
        try:
            filas = db.query(AIUsageLog).filter(AIUsageLog.user_id == user_id).all()
            assert [f.feature for f in filas] == ["sop_universidad"]
        finally:
            db.close()

    def test_la_postulacion_de_punta_a_punta(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(
            SessionLocal,
            answers={
                "career_linkedin_profile": {
                    "headline": "Analista de datos",
                    "experience": [{"role": "Analista", "organization": "Acme"}],
                },
                "career_current_role": "Analista",
            },
        )
        client = TestClient(app)
        cliente = _cliente(_PITCH_OK)

        with patch("app.core.ai_client.get_client", return_value=cliente):
            r = client.post(
                f"{BASE}/job-application",
                headers=_auth(client),
                json={"vacante": _VACANTE, "formato": "correo"},
            )

        assert r.status_code == 200, r.text
        datos = r.json()
        assert datos["asunto"]
        assert datos["no_cumples"][0]["que"] == "Ingles B2"

        # El perfil de LinkedIn que ya estaba guardado llegó al prompt.
        prompt = cliente.with_options.return_value.messages.create.call_args.kwargs[
            "messages"
        ][0]["content"]
        assert "Acme" in prompt

    def test_una_vacante_corta_se_rechaza_sin_llamar_al_modelo(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        cliente = _cliente(_PITCH_OK)

        with patch("app.core.ai_client.get_client", return_value=cliente):
            r = client.post(
                f"{BASE}/job-application",
                headers=_auth(client),
                json={"vacante": "hola"},
            )

        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "job_vacante_too_short"
        cliente.with_options.return_value.messages.create.assert_not_called()

    def test_estas_herramientas_son_solo_del_estudiante(self, app_with_db):
        """Trabajan sobre datos personales de un menor · un asesor no escribe
        aquí (Ley 1581/2012)."""
        app, SessionLocal = app_with_db
        from app.api.v1.auth import get_password_hash
        from app.db.models import OnboardingStatus, User, UserRole

        db = SessionLocal()
        try:
            db.add(
                User(
                    email="asesor@example.com",
                    hashed_password=get_password_hash("testpass123"),
                    name="Asesor",
                    role=UserRole.GH_ADVISOR,
                    onboarding_status=OnboardingStatus.NOT_STARTED,
                )
            )
            db.commit()
        finally:
            db.close()

        client = TestClient(app)
        auth = _auth(client, "asesor@example.com")

        assert client.get(BASE, headers=auth).status_code == 403
        assert (
            client.post(
                f"{BASE}/statement-of-purpose",
                headers=auth,
                json={"universidad": "Manchester", "programa": "Ingenieria"},
            ).status_code
            == 403
        )

    def test_la_foto_del_estudiante_no_se_baja_para_escribir_un_texto(
        self, app_with_db
    ):
        """El CV va a un prompt, no a un PDF · la foto no pinta nada ahí.

        Bajarla de storage y pasarla a base64 en cada request es trabajo tirado,
        y se trata de la foto de un menor: mejor que ni se mueva.
        """
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)

        with patch(
            "app.services.cv_photo_service.obtener_data_uri", return_value=None
        ) as foto:
            r = client.get(BASE, headers=_auth(client))

        assert r.status_code == 200
        foto.assert_not_called()

    def test_sin_sesion_no_se_entra(self, app_with_db):
        app, _ = app_with_db
        client = TestClient(app)

        assert client.get(BASE).status_code in (401, 403)
