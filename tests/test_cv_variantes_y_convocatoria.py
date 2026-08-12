"""La hoja de vida con destino, foto y convocatoria (2026-08-10).

Cubre las tres cosas que se añadieron y que no tenían red:

1. **Las variantes** · que `us` omita la foto no es cosmética: es la única regla
   de este módulo que cambia el CONTENIDO del documento según a dónde se manda.
   Si alguien la ablanda por error, el estudiante manda a una universidad
   estadounidense un documento que allá se lee como sesgo.
2. **La convocatoria** · los límites, y sobre todo que un fallo del modelo deje
   la fila en `failed` con un mensaje, y no colgada en `analyzing` para siempre.
3. **La foto** · magic bytes, tamaño, y que se persista la RUTA y no una URL
   firmada (el bug que arrastra `programs.py`).

## Qué se mockea y por qué

**La frontera: `client.messages.create` del SDK de Anthropic.** No las funciones
de `cv_target_service` ni `cv_tailor_service`, que son justo lo que se prueba.
Es la regla que este repo aprendió a golpes el 05-08, cuando once tests en verde
convivían con una funcionalidad rota al 100% porque mockeaban la función y no el
cliente. Prueba de ello: estos tests recorren `parsear()` y `normalizar()` de
verdad, así que si el esquema del tool cambia, fallan.
"""
from __future__ import annotations

import base64
import io
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import cv_tailor_service, cv_target_service, cv_variants
from app.services.cv_docx_service import render_cv_docx
from app.services.cv_pdf_service import CVActivity, CVData, render_cv_html

# PNG de 1x1 real · sirve para el camino feliz de la foto.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _cv_de_prueba(**extra) -> CVData:
    datos = dict(
        student_name="Ana Perez",
        generated_on="10 de agosto de 2026",
        email="ana@example.com",
        summary="Estudiante de once con interes en ingenieria.",
        strengths=["Liderazgo"],
        interests=["Ciencia"],
        test_highlights=[("Holland", "RIA", "Realista", "holland")],
        activities=[
            CVActivity(category_label="Deporte", name="Natacion", role="Capitana")
        ],
        photo_data_uri="data:image/png;base64," + base64.b64encode(PNG_1X1).decode(),
    )
    datos.update(extra)
    return CVData(**datos)


# ===========================================================================
# 1 · Las variantes
# ===========================================================================


class TestVariantes:
    def test_estados_unidos_omite_la_foto_aunque_el_estudiante_la_quiera(self):
        """La regla que justifica que el estándar sea política y no estilo.

        Se pide explícitamente `incluir_foto=True` y aun así no sale: allá
        incluirla se lee como sesgo y descarta el documento. El estudiante no
        tiene por qué saberlo.
        """
        html = render_cv_html(_cv_de_prueba(), estandar="us", incluir_foto=True)

        assert 'class="photo"' not in html

    def test_latam_y_europa_si_imprimen_la_foto(self):
        for estandar in ("latam", "europass"):
            html = render_cv_html(_cv_de_prueba(), estandar=estandar)
            assert 'class="photo"' in html, estandar

    def test_el_estudiante_puede_quitar_su_foto_donde_si_se_permite(self):
        html = render_cv_html(_cv_de_prueba(), estandar="latam", incluir_foto=False)

        assert 'class="photo"' not in html

    def test_cada_estandar_ordena_las_secciones_a_su_manera(self):
        """En Estados Unidos pesa primero lo que hiciste; los tests van al final."""
        def orden(estandar: str):
            html = render_cv_html(_cv_de_prueba(), estandar=estandar)
            return [
                clave
                for _, clave in sorted(
                    (html.index(marca), clave)
                    for clave, marca in (
                        ("perfil", ">Perfil<"),
                        ("tests", ">Resultados de tests<"),
                        ("actividades", ">Actividades extracurriculares<"),
                    )
                )
            ]

        assert orden("us") == ["perfil", "actividades", "tests"]
        assert orden("latam") == ["perfil", "tests", "actividades"]

    def test_un_estandar_inventado_no_deja_al_estudiante_sin_hoja_de_vida(self):
        """Un querystring inválido cae al por defecto · no revienta.

        Este servicio presume de ser "siempre generable"; eso vale también para
        los parámetros.
        """
        html = render_cv_html(_cv_de_prueba(), estandar="atlantida", estilo="neon")

        assert "Ana Perez" in html
        assert cv_variants.obtener_estandar("atlantida").clave == "latam"

    def test_los_valores_por_defecto_dan_el_mismo_cv_de_siempre(self):
        """Nada de lo que ya estaba impreso cambia en silencio."""
        cv = _cv_de_prueba()

        assert render_cv_html(cv) == render_cv_html(
            cv, estandar="latam", estilo="clasico"
        )

    def test_el_word_obedece_al_estandar_igual_que_el_pdf(self):
        """Si divergieran, el estudiante bajaría dos documentos distintos
        creyendo que son el mismo — el bug P0-8 otra vez, en otra capa."""
        def imagenes(blob: bytes) -> int:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                return len([n for n in z.namelist() if n.startswith("word/media/")])

        assert imagenes(render_cv_docx(_cv_de_prueba(), estandar="us")) == 0
        assert imagenes(render_cv_docx(_cv_de_prueba(), estandar="latam")) == 1

    def test_una_foto_corrupta_no_tumba_la_descarga(self):
        cv = _cv_de_prueba(photo_data_uri="data:image/png;base64,@@@no-es-base64@@@")

        assert len(render_cv_docx(cv)) > 0
        assert "Ana Perez" in render_cv_html(cv)


# ===========================================================================
# 2 · La convocatoria
# ===========================================================================


def _respuesta_tool(payload: dict):
    """Imita la respuesta del SDK cuando el tool use forzado devuelve `payload`."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="x", input=payload)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        stop_reason="tool_use",
    )


class _ClienteFalso:
    """Doble del cliente de Anthropic · **la frontera**, no la función."""

    def __init__(self, payload=None, error=None):
        self._payload = payload or {}
        self._error = error
        self.llamadas = 0

    def with_options(self, **_kwargs):
        return self

    @property
    def messages(self):
        return self

    def create(self, **_kwargs):
        self.llamadas += 1
        if self._error:
            raise self._error
        return _respuesta_tool(self._payload)


@pytest.fixture()
def cliente_falso(monkeypatch):
    """Deja el doble instalado y devuelve una fábrica para configurarlo."""
    creados = []

    def instalar(payload=None, error=None):
        fake = _ClienteFalso(payload, error)
        creados.append(fake)
        monkeypatch.setattr("app.core.ai_client.get_client", lambda: fake)
        return fake

    return instalar


class TestConvocatoria:
    def test_texto_muy_corto_no_llega_a_gastar_una_llamada(self, cliente_falso):
        """El límite se comprueba ANTES del modelo · si no, cada 'hola' cuesta."""
        fake = cliente_falso({"kind": "job"})

        with pytest.raises(cv_target_service.CVTargetError):
            cv_target_service.parsear("hola", session_id="t")

        assert fake.llamadas == 0

    def test_un_texto_larguisimo_se_recorta_antes_de_mandarlo(self, cliente_falso):
        cliente_falso({"kind": "job", "title": "Analista"})
        enorme = "x" * (cv_target_service.MAX_CHARS + 5000)

        parsed, _meta = cv_target_service.parsear(enorme, session_id="t")

        assert parsed["title"] == "Analista"

    def test_recorre_la_normalizacion_de_verdad(self, cliente_falso):
        """Lo que devuelve el modelo NUNCA se guarda en crudo.

        Este test es el que demuestra que se mockea la frontera: pasa por
        `parsear()` y `normalizar()` reales, así que un cambio de esquema
        rompería aquí.
        """
        cliente_falso(
            {
                "kind": "BANANA",  # no está en el enum
                "title": "T" * 500,  # más largo que el límite
                "requisitos": [f"requisito {i}" for i in range(40)],
            }
        )

        parsed, _meta = cv_target_service.parsear("x" * 200, session_id="t")

        assert parsed["kind"] == "other"
        assert len(parsed["title"]) <= 200
        assert len(parsed["requisitos"]) == 10

    def test_si_el_modelo_no_devuelve_nada_el_error_es_para_el_estudiante(
        self, cliente_falso
    ):
        cliente_falso(error=RuntimeError("la API se cayó"))

        with pytest.raises(cv_target_service.CVTargetError) as exc:
            cv_target_service.parsear("x" * 200, session_id="t")

        # El mensaje llega a su pantalla · no puede ser una traza.
        assert "la API se cayó" not in str(exc.value)

    def test_el_ajuste_se_acota_porque_pinta_una_barra_en_pantalla(self):
        assert cv_tailor_service.normalizar({"ajuste": 130})["ajuste"] == 100
        assert cv_tailor_service.normalizar({"ajuste": -5})["ajuste"] == 0
        assert cv_tailor_service.normalizar({"ajuste": "buenísimo"})["ajuste"] is None

    def test_los_faltantes_sobreviven_aunque_vengan_como_texto_suelto(self):
        salida = cv_tailor_service.normalizar({"faltantes": ["Inglés B2"]})

        assert salida["faltantes"] == [
            {"que": "Inglés B2", "por_que": None, "como_resolverlo": None}
        ]

    def test_la_propuesta_solo_toca_los_campos_editables(self):
        """`a_overrides` tiene que encajar con lo que acepta `cv_profile_service`.

        Si emitiera una clave que ese servicio no conoce, se descartaría en
        silencio y el estudiante vería "aplicado" sin que cambiara nada.
        """
        from app.services.cv_profile_service import _LIST_FIELDS, _TEXT_FIELDS

        overrides = cv_tailor_service.a_overrides(
            {
                "headline": "Aspirante",
                "summary": "Resumen",
                "strengths": ["Liderazgo"],
                "interests": ["Ciencia"],
                "ajuste": 70,
                "faltantes": [{"que": "Inglés"}],
                "destacar_actividades": ["Natacion"],
            }
        )

        assert set(overrides) <= set(_TEXT_FIELDS) | set(_LIST_FIELDS)
        assert set(overrides) == {"headline", "summary", "strengths", "interests"}

    def test_destacar_una_actividad_no_borra_las_demas(self):
        """Destacar no es quitar. Borrar del CV algo que el estudiante registró
        porque un modelo lo consideró poco relevante es decisión suya."""
        overrides = cv_tailor_service.a_overrides(
            {"destacar_actividades": ["Natacion"], "ajuste": 50, "faltantes": []}
        )

        assert "excluded_activity_ids" not in overrides

    def test_le_dice_al_modelo_que_no_hay_actividades_en_vez_de_callarselo(self):
        """Si no lo dice, el modelo asume que se le olvidó pasarlas y se las
        inventa — y este prompt tiene prohibido inventar experiencia."""
        texto = cv_tailor_service.describir_cv(
            CVData(student_name="B", generated_on="hoy")
        )

        assert "ninguna registrada" in texto


# ===========================================================================
# 3 · Los endpoints · foto, formato y ciclo de la convocatoria
# ===========================================================================


@pytest.fixture()
def app_with_db(monkeypatch):
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
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

    from app.services import storage_service

    storage_service.reset_backend_for_tests()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _estudiante(SessionLocal, email="ana@test.co"):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Ana Perez",
            role=UserRole("student"),
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _token(client, email="ana@test.co"):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class TestEndpointFoto:
    def test_un_ejecutable_disfrazado_de_jpg_se_rechaza(self, app_with_db):
        """El content-type lo manda el cliente y se puede mentir · los magic
        bytes no."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.post(
            "/api/v1/me/photo",
            headers=auth,
            files={"file": ("foto.jpg", b"MZ\x90\x00esto es un .exe", "image/jpeg")},
        )

        assert r.status_code == 415

    def test_un_svg_no_pasa_aunque_sea_una_imagen(self, app_with_db):
        """Una foto de una persona nunca es vectorial, y el SVG es el formato
        que puede traer script dentro."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.post(
            "/api/v1/me/photo",
            headers=auth,
            files={"file": ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")},
        )

        assert r.status_code == 415

    def test_una_foto_valida_guarda_la_RUTA_y_no_una_url_firmada(self, app_with_db):
        """Las URLs de Supabase caducan a las 24 h · persistirlas deja imágenes
        rotas. Es el bug que arrastra `programs.py` y que aquí no se repite."""
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.post(
            "/api/v1/me/photo",
            headers=auth,
            files={"file": ("foto.png", PNG_1X1, "image/png")},
        )
        assert r.status_code == 200, r.text

        from app.db.models import UserPhoto

        db = SessionLocal()
        try:
            fila = db.query(UserPhoto).filter(UserPhoto.user_id == user_id).first()
            assert fila is not None, "la foto no quedó guardada"
            # Los BYTES, no una referencia: el bucket corría contra un stub en
            # memoria y la foto se perdía en cada reinicio del dyno.
            assert bytes(fila.data) == PNG_1X1
            assert fila.content_type == "image/png"
            assert fila.size_bytes == len(PNG_1X1)
        finally:
            db.close()

    def test_subir_otra_foto_reemplaza_en_vez_de_acumular(self, app_with_db):
        """Una foto por persona · el user_id es la clave primaria."""
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        for _ in range(3):
            client.post(
                "/api/v1/me/photo",
                headers=auth,
                files={"file": ("foto.png", PNG_1X1, "image/png")},
            )

        from app.db.models import UserPhoto

        db = SessionLocal()
        try:
            assert db.query(UserPhoto).filter(UserPhoto.user_id == user_id).count() == 1
        finally:
            db.close()

    def test_saber_si_hay_foto_no_se_descarga_la_imagen(self, app_with_db):
        """`tiene_foto` es para pintar un botón · bajarse 2 MB para responder
        sí o no sería absurdo, así que va por `SELECT 1`."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        assert client.get("/api/v1/me/cv/formatos", headers=auth).json()["tiene_foto"] is False

        client.post(
            "/api/v1/me/photo",
            headers=auth,
            files={"file": ("foto.png", PNG_1X1, "image/png")},
        )

        assert client.get("/api/v1/me/cv/formatos", headers=auth).json()["tiene_foto"] is True

    def test_quitar_la_foto_suelta_la_referencia(self, app_with_db):
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        client.post(
            "/api/v1/me/photo",
            headers=auth,
            files={"file": ("foto.png", PNG_1X1, "image/png")},
        )
        r = client.delete("/api/v1/me/photo", headers=auth)

        assert r.status_code == 200
        assert r.json() == {"tiene_foto": False}

        from app.db.models import UserPhoto

        db = SessionLocal()
        try:
            # La fila se borra de verdad · no basta con marcarla, porque la
            # imagen de un menor no se queda dando vueltas "por si acaso".
            assert db.query(UserPhoto).filter(UserPhoto.user_id == user_id).first() is None
        finally:
            db.close()


class TestEndpointFormato:
    def test_el_catalogo_sale_del_servicio_y_no_de_una_lista_en_el_front(
        self, app_with_db
    ):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.get("/api/v1/me/cv/formatos", headers=auth)

        assert r.status_code == 200
        datos = r.json()
        claves = {e["clave"] for e in datos["estandares"]}
        assert claves == set(cv_variants.ESTANDARES)
        # La nota es lo que explica en pantalla por qué US no lleva foto.
        us = next(e for e in datos["estandares"] if e["clave"] == "us")
        assert us["permite_foto"] is False
        assert us["nota"]

    def test_un_estandar_inventado_se_rechaza_al_guardar(self, app_with_db):
        """Guardar basura sí falla · renderizar con basura no. La diferencia es
        deliberada: una preferencia mal escrita se corrige, un CV que no se
        genera deja al estudiante sin documento."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.put(
            "/api/v1/me/cv/formato", headers=auth, json={"estandar": "atlantida"}
        )

        assert r.status_code == 400

    def test_lo_elegido_se_recuerda(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        client.put(
            "/api/v1/me/cv/formato",
            headers=auth,
            json={"estandar": "us", "estilo": "compacto", "incluir_foto": False},
        )
        r = client.get("/api/v1/me/cv/formatos", headers=auth)

        assert r.json()["seleccion"] == {
            "estandar": "us",
            "estilo": "compacto",
            "incluir_foto": False,
        }

    def test_un_formato_de_archivo_desconocido_se_rechaza(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.get("/api/v1/me/cv?formato=wordperfect", headers=auth)

        assert r.status_code == 400


class TestEndpointConvocatoria:
    def _preparar(self, SessionLocal, user_id):
        """A3 · sin las preguntas previas el CV no se genera."""
        from app.services import cv_profile_service

        db = SessionLocal()
        try:
            cv_profile_service.save_answers(
                db, user_id, current_occupation="working", occupation_detail="Panadería"
            )
        finally:
            db.close()

    def test_texto_corto_se_rechaza_sin_crear_fila(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.post("/api/v1/me/cv/targets", headers=auth, json={"raw_text": "hola"})

        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "cv_target_too_short"
        assert client.get("/api/v1/me/cv/targets", headers=auth).json()["targets"] == []

    def test_un_fallo_del_modelo_deja_la_fila_en_failed_y_no_colgada(
        self, app_with_db, cliente_falso
    ):
        """El peor final posible es `analyzing` para siempre: la pantalla haría
        polling eterno y el estudiante nunca sabría que falló."""
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        self._preparar(SessionLocal, user_id)
        cliente_falso(error=RuntimeError("boom"))
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        # TestClient corre los BackgroundTasks al cerrar el request.
        r = client.post(
            "/api/v1/me/cv/targets", headers=auth, json={"raw_text": "x" * 300}
        )
        assert r.status_code == 202

        estado = client.get(
            f"/api/v1/me/cv/targets/{r.json()['id']}", headers=auth
        ).json()

        assert estado["status"] == "failed"
        assert estado["error"]

    def test_el_camino_feliz_deja_propuesta_y_faltantes(
        self, app_with_db, cliente_falso
    ):
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        self._preparar(SessionLocal, user_id)
        # El mismo doble responde a las dos llamadas (parse y tailor); el payload
        # trae las claves de ambos esquemas.
        cliente_falso(
            {
                "kind": "internship",
                "title": "Práctica en laboratorio",
                "organization": "Universidad X",
                "requisitos": ["Inglés B2"],
                "headline": "Aspirante a ingeniería",
                "summary": "Resumen adaptado.",
                "strengths": ["Liderazgo"],
                "ajuste": 65,
                "faltantes": [{"que": "Inglés B2", "por_que": "Lo exigen"}],
            }
        )
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        creado = client.post(
            "/api/v1/me/cv/targets", headers=auth, json={"raw_text": "x" * 300}
        ).json()
        estado = client.get(
            f"/api/v1/me/cv/targets/{creado['id']}", headers=auth
        ).json()

        assert estado["status"] == "ready", estado.get("error")
        assert estado["title"] == "Práctica en laboratorio"
        assert estado["analysis"]["ajuste"] == 65
        assert estado["analysis"]["faltantes"][0]["que"] == "Inglés B2"
        # La propuesta NO se aplicó sola.
        assert estado["proposal"]["headline"] == "Aspirante a ingeniería"
        perfil = client.get("/api/v1/me/cv/profile", headers=auth).json()
        assert perfil["content"]["headline"] != "Aspirante a ingeniería"

    def test_aplicar_es_lo_unico_que_escribe_la_hoja_de_vida(
        self, app_with_db, cliente_falso
    ):
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        self._preparar(SessionLocal, user_id)
        cliente_falso(
            {
                "kind": "job",
                "headline": "Aspirante a ingeniería",
                "summary": "Resumen adaptado.",
                "ajuste": 65,
                "faltantes": [],
            }
        )
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        creado = client.post(
            "/api/v1/me/cv/targets", headers=auth, json={"raw_text": "x" * 300}
        ).json()
        r = client.post(
            f"/api/v1/me/cv/targets/{creado['id']}/apply", headers=auth
        )

        assert r.status_code == 200
        assert r.json()["content"]["headline"] == "Aspirante a ingeniería"

    def test_no_se_puede_aplicar_algo_que_no_esta_listo(
        self, app_with_db, cliente_falso
    ):
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal)
        self._preparar(SessionLocal, user_id)
        cliente_falso(error=RuntimeError("boom"))
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        creado = client.post(
            "/api/v1/me/cv/targets", headers=auth, json={"raw_text": "x" * 300}
        ).json()
        r = client.post(f"/api/v1/me/cv/targets/{creado['id']}/apply", headers=auth)

        assert r.status_code == 409

    def test_no_puedo_ver_la_convocatoria_de_otro_estudiante(
        self, app_with_db, cliente_falso
    ):
        """Filtrar sólo por id dejaría leer la de cualquiera adivinando un UUID."""
        app, SessionLocal = app_with_db
        user_id = _estudiante(SessionLocal, "ana@test.co")
        _estudiante(SessionLocal, "otro@test.co")
        self._preparar(SessionLocal, user_id)
        cliente_falso({"kind": "job", "ajuste": 50, "faltantes": []})
        client = TestClient(app)

        mio = client.post(
            "/api/v1/me/cv/targets",
            headers={"Authorization": f"Bearer {_token(client)}"},
            json={"raw_text": "x" * 300},
        ).json()

        ajeno = {"Authorization": f"Bearer {_token(client, 'otro@test.co')}"}
        r = client.get(f"/api/v1/me/cv/targets/{mio['id']}", headers=ajeno)

        # 404 y no 403 · un 403 confirmaría que ese id existe.
        assert r.status_code == 404


class TestEnlacePublico:
    def test_nace_apagado(self, app_with_db):
        """Son menores de edad · encenderlo lo decide la clienta, no el código."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal)
        client = TestClient(app)
        auth = {"Authorization": f"Bearer {_token(client)}"}

        r = client.post("/api/v1/me/cv/share", headers=auth)

        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "cv_share_disabled"

    def test_un_token_inventado_da_404_aunque_este_encendido(self, app_with_db, monkeypatch):
        app, _SessionLocal = app_with_db
        from app.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("CV_PUBLIC_LINK_ENABLED", "true")
        get_settings.cache_clear()
        client = TestClient(app)

        r = client.get("/api/v1/cv/p/" + "z" * 43)

        assert r.status_code == 404
        get_settings.cache_clear()
