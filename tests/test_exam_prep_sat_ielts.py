"""Práctica para SAT e IELTS · reunión con la clienta del 2026-08-24.

Textual, minuto 40:22: *"yo lo que necesito es pasar el test, no que nadie me
certifique... es solamente para hacer el test"*.

Lo que estos tests protegen son tres cosas que se rompen en silencio y las tres
cuestan caro:

1. **El encuadre legal.** Esto es material de práctica propio; no es el examen,
   no certifica y no predice puntajes. Si mañana alguien "mejora" el copy y
   escribe que esto acredita algo, o publica la duración del examen como si
   fuera dato nuestro, el producto empieza a afirmar cosas que no puede
   sostener — y en este proyecto ya hubo un reclamo de la clienta por contenido
   inventado por nosotros. Por eso hay tests de copy, de avisos y de datos duros.

2. **La conexión con el diagnóstico de inglés que YA existe.** El test más
   importante del archivo es
   `test_hacer_el_diagnostico_de_ames_cambia_el_nivel_de_la_practica`: recorre
   el camino real (HTTP → examen de AMES → práctica) en vez de llamar al
   servicio con un CEFR inventado. Sin él, la conexión podría estar rota al
   100% y todo lo demás seguiría en verde — que es literalmente el defecto que
   documenta el CLAUDE.md del repo.

3. **Que la clave no salga del servidor.** Un ejercicio servido con su
   `correct` adentro convierte la práctica en un juego de leer el JSON.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import exam_prep as banco
from app.data.english_test_questions import ENGLISH_TEST_QUESTIONS
from app.data.exam_prep import (
    EXAMEN_IELTS,
    EXAMEN_SAT,
    NIVEL_AVANZADO,
    NIVEL_FUNDAMENTOS,
    NIVEL_INTERMEDIO,
    NIVELES,
)
from app.data.onboarding_hechos import (
    RUTA_GRADO_11,
    RUTA_GRADO_12,
    RUTA_POR_GRADO,
)
from app.services import exam_prep_service as servicio


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _usuario(**overrides):
    """Un estudiante de mentira con lo mínimo que lee el servicio."""
    base = dict(
        id="00000000-0000-0000-0000-000000000001",
        grade=None,
        onboarding_answers={},
        english_cefr_level=None,
        english_test_completed=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _todo_el_copy_visible() -> str:
    """Cada string que un estudiante puede llegar a leer de este módulo."""
    trozos = [
        banco.AVISO_NO_OFICIAL,
        banco.REMISION_AL_EXAMINADOR,
        banco.NOTA_DE_RESULTADO,
        *banco.MARCAS.values(),
    ]
    for examen in banco.EXAMENES:
        trozos += [
            examen["name"],
            examen["shortName"],
            examen["description"],
            examen["academicBasis"],
            examen["audiencia"],
            *examen["formato"],
        ]
        for nc in examen["no_cubierto"]:
            trozos += [nc["que"], nc["porque"]]
    for h in banco.HABILIDADES:
        trozos += [h["name"], h["description"]]
    for i in banco.EXAM_PREP_ITEMS:
        trozos += [i["question"], i["explanation"], *i["options"]]
    return "\n".join(trozos)


# ---------------------------------------------------------------------------
# 1 · El banco
# ---------------------------------------------------------------------------

class TestBanco:
    def test_cada_ejercicio_tiene_su_explicacion_de_verdad(self):
        """El valor pedagógico está en el porqué · una explicación de tres
        palabras es lo mismo que no tenerla."""
        for item in banco.EXAM_PREP_ITEMS:
            assert len(item["explanation"].strip()) >= 80, item["id"]

    def test_la_respuesta_correcta_siempre_esta_entre_las_opciones(self):
        for item in banco.EXAM_PREP_ITEMS:
            assert item["correct"] in item["options"], item["id"]
            assert len(set(item["options"])) == len(item["options"]), item["id"]

    def test_no_hay_ids_repetidos(self):
        ids = [i["id"] for i in banco.EXAM_PREP_ITEMS]
        assert len(set(ids)) == len(ids)

    def test_cada_habilidad_tiene_ejercicios_en_los_tres_niveles(self):
        """Si una habilidad no tuviera el nivel de un estudiante, la sesión le
        saldría siempre del nivel vecino y el arranque desde el diagnóstico de
        inglés no se notaría."""
        for examen in banco.EXAMENES:
            for h in banco.habilidades_de(examen["id"]):
                assert h["levels"] == list(NIVELES), h["id"]
                assert h["itemCount"] >= 6, h["id"]

    def test_los_dos_examenes_declaran_su_conteo_real(self):
        for examen in banco.EXAMENES:
            reales = len(banco.items(exam_id=examen["id"]))
            assert examen["questionCount"] == reales

    def test_el_ejercicio_publico_no_lleva_la_clave_ni_la_explicacion(self):
        """Si la respuesta viaja al front antes de responder, esto deja de ser
        práctica."""
        for item in banco.EXAM_PREP_ITEMS:
            publico = banco.item_publico(item)
            assert "correct" not in publico, item["id"]
            assert "explanation" not in publico, item["id"]
            assert item["correct"] in publico["options"]

    def test_el_texto_de_lectura_viaja_con_el_ejercicio(self):
        """Un ejercicio de comprensión sin su texto es incontestable · el mismo
        contrato que `english_test_questions.get_questions_for_client`."""
        con_texto = [i for i in banco.EXAM_PREP_ITEMS if i["passage_id"]]
        assert con_texto, "el banco debería tener ejercicios sobre textos"
        for item in con_texto:
            publico = banco.item_publico(item)
            assert publico["passage"] == banco.texto(item["passage_id"])
            assert len(publico["passage"]) > 200

    def test_la_ficha_sigue_el_contrato_de_los_tests_vocacionales(self):
        """Se reusa el shape de `vocational_tests` para que el front pinte la
        tarjeta sin trabajo extra."""
        obligatorios = (
            "id", "slug", "name", "shortName", "description", "academicBasis",
            "estimatedMinutes", "questionCount", "icon",
        )
        for examen in banco.EXAMENES:
            for clave in obligatorios:
                assert clave in examen, (examen["id"], clave)

    def test_los_ejercicios_siguen_el_shape_de_opcion_multiple_que_ya_existe(self):
        """Mismo contrato que el test de inglés (`question` + `options` como
        lista de strings): el front ya tiene ese renderizador."""
        for item in banco.EXAM_PREP_ITEMS:
            publico = banco.item_publico(item)
            assert publico["type"] == "multiple_choice"
            assert isinstance(publico["question"], str) and publico["question"]
            assert all(isinstance(o, str) for o in publico["options"])
            assert publico["level"] in NIVELES


# ---------------------------------------------------------------------------
# 2 · La línea que no se cruza · copy y datos duros
# ---------------------------------------------------------------------------

# Palabras que sólo pueden aparecer NEGADAS. "Esto no certifica" es correcto;
# "esto certifica" es una afirmación que no podemos sostener.
_SOLO_NEGADAS = ("certific", "acredit", "avalad", "predice", "garantiz")

# Frases que no pueden aparecer de ninguna forma.
_PROHIBIDAS = (
    "examen oficial",
    "puntaje oficial",
    "material oficial",
    "en alianza con",
    "preparación certificada",
)


def _negada(texto: str, posicion: int) -> bool:
    """¿Hay una negación en los 60 caracteres anteriores?"""
    ventana = texto[max(0, posicion - 60):posicion].lower()
    return " no " in ventana or ventana.startswith("no ") or " ni " in ventana


class TestNoAfirmaLoQueNoPuede:
    def test_certificar_acreditar_y_predecir_solo_aparecen_negados(self):
        copy = _todo_el_copy_visible()
        for palabra in _SOLO_NEGADAS:
            for match in re.finditer(palabra, copy, flags=re.IGNORECASE):
                assert _negada(copy, match.start()), (
                    f"“{palabra}” aparece sin negación cerca de: "
                    f"…{copy[max(0, match.start() - 90):match.start() + 40]}…"
                )

    def test_no_hay_frases_que_sugieran_afiliacion_ni_oficialidad(self):
        copy = _todo_el_copy_visible().lower()
        for frase in _PROHIBIDAS:
            assert frase not in copy, frase

    def test_el_aviso_dice_las_cuatro_cosas(self):
        aviso = banco.AVISO_NO_OFICIAL.lower()
        assert "práctica" in aviso
        assert "no es el examen" in aviso
        assert "no certifica" in aviso
        assert "no predice" in aviso

    def test_cada_examen_declara_de_quien_es_la_marca_y_que_no_estamos_afiliados(self):
        for exam_id, texto in banco.MARCAS.items():
            assert exam_id in [e["id"] for e in banco.EXAMENES]
            assert "no está afiliado" in texto

    def test_el_formato_no_publica_datos_duros_del_examen(self):
        """Duración, número de preguntas, escala y costo los define el
        examinador y cambian. Aquí se describe la FORMA, sin cifras."""
        for examen in banco.EXAMENES:
            for linea in examen["formato"]:
                assert not re.search(r"\d", linea), (examen["id"], linea)

    def test_no_aparece_ninguna_escala_de_puntaje(self):
        copy = _todo_el_copy_visible()
        for escala in ("1600", "2400", "800 puntos", "banda 9", "9.0"):
            assert escala not in copy, escala

    def test_la_ficha_remite_al_examinador_por_los_datos_que_no_son_nuestros(self):
        assert "oficial" in banco.REMISION_AL_EXAMINADOR
        assert "cambian" in banco.REMISION_AL_EXAMINADOR

    def test_el_ielts_declara_que_no_cubre_listening_ni_speaking(self):
        ielts = banco.get_examen(EXAMEN_IELTS)
        declarado = " ".join(nc["que"].lower() for nc in ielts["no_cubierto"])
        assert "listening" in declarado
        assert "speaking" in declarado

    def test_no_se_le_pone_puntaje_automatico_a_un_ensayo(self):
        """La práctica de escritura es de decisiones (opción múltiple) a
        propósito: calificar un texto con IA sería inventarle una nota."""
        escritura = banco.items(skill_id="ielts_escritura")
        assert escritura
        assert all(i["type"] == "multiple_choice" for i in escritura)


# ---------------------------------------------------------------------------
# 3 · A quién se le ofrece · las 5 rutas que ya existen
# ---------------------------------------------------------------------------

class TestAQuienSeLeOfrece:
    def test_los_grados_del_sat_salen_de_la_tabla_de_rutas_de_la_malla(self):
        """No es una tupla propia: si la malla cambiara, esto la sigue."""
        assert servicio.GRADOS_SAT == (11, 12)
        assert {RUTA_POR_GRADO[str(g)] for g in servicio.GRADOS_SAT} == {
            RUTA_GRADO_11,
            RUTA_GRADO_12,
        }

    @pytest.mark.parametrize("grado", [11, 12])
    def test_sat_se_recomienda_en_11_y_12(self, grado):
        u = _usuario(grade=grado, onboarding_answers={"life_stage": "high_school_late"})
        r = servicio.recomendacion(None, u, EXAMEN_SAT)
        assert r["recommended"] is True
        assert r["reasonCode"] == "grade"

    @pytest.mark.parametrize("grado", [9, 10])
    def test_sat_no_se_recomienda_antes_pero_tampoco_se_bloquea(self, grado):
        """"MEMORIA SÍ, LLAVE NO": se deja de recomendar, no se cierra."""
        u = _usuario(grade=grado, onboarding_answers={"life_stage": "high_school_early"})
        r = servicio.recomendacion(None, u, EXAMEN_SAT)
        assert r["recommended"] is False
        assert r["reasonCode"] == "grade_too_early"
        # Y la práctica sigue armándose para él.
        assert servicio.sesion(None, u, EXAMEN_SAT, limite=3)["items"]

    def test_sat_no_se_recomienda_en_la_ruta_del_adulto(self):
        """Reencuadre de la clienta (24-08): esto es orientación vocacional
        general. A quien busca un curso corto de tres meses no se le empuja un
        examen de admisión a pregrado."""
        u = _usuario(onboarding_answers={"life_stage": "working"})
        r = servicio.recomendacion(None, u, EXAMEN_SAT)
        assert r["recommended"] is False
        assert r["reasonCode"] == "professional_track"

    def test_sin_grado_no_se_adivina(self):
        u = _usuario()
        assert servicio.recomendacion(None, u, EXAMEN_SAT)["reasonCode"] == "grade_unknown"

    def test_el_grado_se_lee_tambien_del_espejo_en_json(self):
        """Se reusa `vocational_bank_selector.grado_del_estudiante`, que sabe
        leer la columna, el JSON y el grado escrito con palabras."""
        u = _usuario(onboarding_answers={"life_stage": "high_school_late", "grade": "once"})
        assert servicio.recomendacion(None, u, EXAMEN_SAT)["recommended"] is True

    @pytest.mark.parametrize("interes", ["intl_yes", "intl_maybe"])
    def test_ielts_se_recomienda_a_quien_declaro_interes_internacional(self, interes):
        u = _usuario(onboarding_answers={"international_interest": interes})
        r = servicio.recomendacion(None, u, EXAMEN_IELTS)
        assert r["recommended"] is True
        assert r["reasonCode"] == "international_interest"

    def test_ielts_se_recomienda_por_nivel_de_ingles_aunque_no_haya_dicho_nada(self):
        u = _usuario(english_cefr_level="B1", english_test_completed=True)
        r = servicio.recomendacion(None, u, EXAMEN_IELTS)
        assert r["recommended"] is True
        assert r["reasonCode"] == "english_level"

    def test_el_no_explicito_al_exterior_manda_sobre_el_nivel_de_ingles(self):
        """Mismo criterio que `onboarding_hechos.aplica()`, que deja de
        preguntarle por el pasaporte a quien dijo intl_no."""
        u = _usuario(
            onboarding_answers={"international_interest": "intl_no"},
            english_cefr_level="A2",
            english_test_completed=True,
        )
        r = servicio.recomendacion(None, u, EXAMEN_IELTS)
        assert r["recommended"] is False
        assert r["reasonCode"] == "not_international"

    def test_con_ingles_alto_y_sin_interes_declarado_no_se_insiste(self):
        u = _usuario(english_cefr_level="B2", english_test_completed=True)
        r = servicio.recomendacion(None, u, EXAMEN_IELTS)
        assert r["recommended"] is False
        assert r["reasonCode"] == "not_yet"

    def test_examen_desconocido_revienta_explicito(self):
        with pytest.raises(ValueError):
            servicio.recomendacion(None, _usuario(), "toefl")


# ---------------------------------------------------------------------------
# 4 · El nivel de arranque · sin duplicar el diagnóstico de inglés
# ---------------------------------------------------------------------------

class TestNivelDeArranque:
    @pytest.mark.parametrize(
        "cefr,esperado",
        [
            ("A2", NIVEL_FUNDAMENTOS),
            ("B1", NIVEL_INTERMEDIO),
            ("B2", NIVEL_AVANZADO),
        ],
    )
    def test_la_practica_de_lengua_arranca_en_el_nivel_que_ya_midio_ames(
        self, cefr, esperado
    ):
        u = _usuario(english_cefr_level=cefr, english_test_completed=True)
        sesion = servicio.sesion(None, u, EXAMEN_IELTS, skill_id="ielts_gramatica", limite=2)
        assert all(i["level"] == esperado for i in sesion["items"])

    def test_sin_diagnostico_no_se_inventa_un_nivel(self):
        u = _usuario()
        sesion = servicio.sesion(None, u, EXAMEN_IELTS, skill_id="ielts_gramatica", limite=6)
        niveles = {i["level"] for i in sesion["items"]}
        assert len(niveles) > 1, "sin diagnóstico la sesión debe mezclar niveles"
        assert sesion["englishDiagnostic"]["practiceLevel"] is None
        assert "diagnóstico" in sesion["levels"][0]["why"]

    def test_el_nivel_de_matematicas_no_se_deriva_del_ingles(self):
        """No hay diagnóstico de matemáticas en el repo. Graduar álgebra con el
        CEFR sería inventarse una relación que nadie midió."""
        u = _usuario(english_cefr_level="A2", english_test_completed=True)
        sesion = servicio.sesion(None, u, EXAMEN_SAT, skill_id="sat_algebra", limite=6)
        decision = sesion["levels"][0]
        assert decision["skill"] == "sat_algebra"
        assert decision["level"] is None
        assert len({i["level"] for i in sesion["items"]}) > 1

    def test_la_misma_sesion_para_el_mismo_perfil(self):
        """Determinista a propósito: sin `random`, dos estudiantes iguales ven
        lo mismo y los tests no dependen de la suerte."""
        u = _usuario(english_cefr_level="B1", english_test_completed=True)
        a = servicio.sesion(None, u, EXAMEN_SAT, limite=8)
        b = servicio.sesion(None, u, EXAMEN_SAT, limite=8)
        assert [i["id"] for i in a["items"]] == [i["id"] for i in b["items"]]

    def test_la_segunda_ronda_no_repite_ejercicios(self):
        u = _usuario(english_cefr_level="B1", english_test_completed=True)
        r1 = {i["id"] for i in servicio.sesion(None, u, EXAMEN_SAT, limite=6)["items"]}
        r2 = {
            i["id"]
            for i in servicio.sesion(None, u, EXAMEN_SAT, limite=6, ronda=2)["items"]
        }
        assert r1 and r2
        assert not (r1 & r2)

    def test_una_sesion_del_examen_completo_mezcla_habilidades(self):
        u = _usuario(english_cefr_level="B1", english_test_completed=True)
        sesion = servicio.sesion(None, u, EXAMEN_SAT, limite=6)
        assert len({i["skill"] for i in sesion["items"]}) >= 4

    def test_el_limite_esta_acotado(self):
        u = _usuario()
        sesion = servicio.sesion(None, u, EXAMEN_SAT, limite=999)
        assert len(sesion["items"]) <= servicio.MAX_EJERCICIOS_POR_SESION

    def test_habilidad_inexistente_revienta_explicito(self):
        with pytest.raises(ValueError):
            servicio.sesion(None, _usuario(), EXAMEN_SAT, skill_id="sat_latin")


# ---------------------------------------------------------------------------
# 5 · Corregir · la explicación es el producto
# ---------------------------------------------------------------------------

class TestCorreccion:
    def test_la_explicacion_llega_tambien_cuando_se_acierta(self):
        """Acertar por descarte sin saber por qué es justo lo que esta práctica
        intenta evitar."""
        item = banco.items(skill_id="sat_algebra")[0]
        salida = servicio.evaluar(EXAMEN_SAT, {item["id"]: item["correct"]})
        resultado = salida["results"][0]
        assert resultado["isCorrect"] is True
        assert resultado["explanation"] == item["explanation"]

    def test_marca_el_error_y_dice_cual_era(self):
        item = banco.items(skill_id="sat_algebra")[0]
        mala = next(o for o in item["options"] if o != item["correct"])
        salida = servicio.evaluar(EXAMEN_SAT, {item["id"]: mala})
        resultado = salida["results"][0]
        assert resultado["isCorrect"] is False
        assert resultado["correctAnswer"] == item["correct"]
        assert resultado["yourAnswer"] == mala

    def test_resume_por_habilidad(self):
        items = banco.items(exam_id=EXAMEN_SAT, skill_id="sat_datos")[:2]
        respuestas = {items[0]["id"]: items[0]["correct"], items[1]["id"]: "nada"}
        salida = servicio.evaluar(EXAMEN_SAT, respuestas)
        assert salida["bySkill"]["sat_datos"] == {
            "correct": 1,
            "answered": 2,
            "percentage": 50,
        }
        assert salida["answered"] == 2
        assert salida["correct"] == 1
        assert salida["percentage"] == 50

    def test_los_ids_que_no_son_de_este_examen_se_reportan_no_se_tragan(self):
        """Un id mal mandado por el front no puede desaparecer en silencio: un
        contador en cero no dice dónde está el error."""
        del_ielts = banco.items(exam_id=EXAMEN_IELTS)[0]["id"]
        salida = servicio.evaluar(EXAMEN_SAT, {del_ielts: "x", "inventado": "y"})
        assert sorted(salida["ignored"]) == sorted([del_ielts, "inventado"])
        assert salida["answered"] == 0

    def test_sin_respuestas_no_revienta_ni_divide_por_cero(self):
        salida = servicio.evaluar(EXAMEN_SAT, {})
        assert salida["answered"] == 0
        assert salida["percentage"] == 0

    def test_el_resultado_dice_que_no_es_un_puntaje_del_examen(self):
        item = banco.items(exam_id=EXAMEN_SAT)[0]
        salida = servicio.evaluar(EXAMEN_SAT, {item["id"]: item["correct"]})
        assert "no es un puntaje del examen" in salida["note"].lower()
        assert salida["disclaimer"] == banco.AVISO_NO_OFICIAL


# ---------------------------------------------------------------------------
# 6 · Sobre HTTP real · el camino que recorre el estudiante
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


def _estudiante(SessionLocal, email, **campos):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Estudiante",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
            **campos,
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


BASE = "/api/v1/exam-prep"


class TestSobreHTTP:
    def test_el_router_esta_montado_y_lista_los_dos_examenes(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.lista@grasshopper.dev", grade=11)
        with TestClient(app) as client:
            h = _headers(client, "prep.lista@grasshopper.dev")
            r = client.get(BASE, headers=h)
            assert r.status_code == 200, r.text
            ids = [e["id"] for e in r.json()["exams"]]
            assert ids == [EXAMEN_SAT, EXAMEN_IELTS]

    def test_sin_token_no_se_ve_nada(self, app_with_db):
        app, _ = app_with_db
        with TestClient(app) as client:
            assert client.get(BASE).status_code in (401, 403)

    def test_el_aviso_viaja_en_los_cuatro_endpoints(self, app_with_db):
        """La clienta pidió que el encuadre esté en pantalla, no en letra chica.
        Si la pantalla de práctica —la que se mira veinte minutos— sale sin
        aviso, el encuadre se perdió."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.aviso@grasshopper.dev", grade=11)
        with TestClient(app) as client:
            h = _headers(client, "prep.aviso@grasshopper.dev")
            respuestas = [
                client.get(BASE, headers=h),
                client.get(f"{BASE}/{EXAMEN_SAT}", headers=h),
                client.get(f"{BASE}/{EXAMEN_SAT}/practice?limit=3", headers=h),
                client.post(
                    f"{BASE}/{EXAMEN_SAT}/practice/check",
                    json={"answers": {}},
                    headers=h,
                ),
            ]
            for r in respuestas:
                assert r.status_code == 200, r.text
                assert r.json().get("disclaimer") == banco.AVISO_NO_OFICIAL

    def test_la_practica_no_devuelve_la_clave(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.clave@grasshopper.dev", grade=11)
        with TestClient(app) as client:
            h = _headers(client, "prep.clave@grasshopper.dev")
            r = client.get(f"{BASE}/{EXAMEN_SAT}/practice?limit=5", headers=h)
            assert r.status_code == 200, r.text
            crudo = r.text
            for item in r.json()["items"]:
                assert "correct" not in item
                assert "explanation" not in item
            assert '"correct"' not in crudo

    def test_corregir_devuelve_la_explicacion(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.check@grasshopper.dev", grade=11)
        with TestClient(app) as client:
            h = _headers(client, "prep.check@grasshopper.dev")
            practica = client.get(
                f"{BASE}/{EXAMEN_SAT}/practice?skill=sat_algebra&limit=2", headers=h
            ).json()
            primer = practica["items"][0]
            correcta = banco.get_item(primer["id"])["correct"]

            r = client.post(
                f"{BASE}/{EXAMEN_SAT}/practice/check",
                json={"answers": {primer["id"]: correcta}},
                headers=h,
            )
            assert r.status_code == 200, r.text
            cuerpo = r.json()
            assert cuerpo["correct"] == 1
            assert cuerpo["results"][0]["explanation"]

    def test_examen_y_habilidad_inexistentes_dan_404(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.404@grasshopper.dev", grade=11)
        with TestClient(app) as client:
            h = _headers(client, "prep.404@grasshopper.dev")
            assert client.get(f"{BASE}/toefl", headers=h).status_code == 404
            assert (
                client.get(f"{BASE}/{EXAMEN_SAT}/practice?skill=latin", headers=h)
                .status_code
                == 404
            )

    def test_el_detalle_dice_lo_que_no_cubre(self, app_with_db):
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.detalle@grasshopper.dev", grade=11)
        with TestClient(app) as client:
            h = _headers(client, "prep.detalle@grasshopper.dev")
            r = client.get(f"{BASE}/{EXAMEN_IELTS}", headers=h)
            assert r.status_code == 200, r.text
            cuerpo = r.json()
            assert cuerpo["no_cubierto"]
            assert cuerpo["examinerNotice"] == banco.REMISION_AL_EXAMINADOR
            assert [s["id"] for s in cuerpo["skills"]]


# ---------------------------------------------------------------------------
# 7 · EL test que importa · la conexión con el diagnóstico que ya existe
# ---------------------------------------------------------------------------

def _respuestas_de_ames(aciertos: int) -> dict:
    """Contesta bien los primeros `aciertos` ítems del examen de AMES."""
    respuestas = {}
    for n, q in enumerate(ENGLISH_TEST_QUESTIONS):
        if n < aciertos:
            respuestas[q["id"]] = q["correct"]
        else:
            # Una opción que no sea la correcta · así el puntaje es exacto.
            respuestas[q["id"]] = next(
                o for o in q["options"] if o != q["correct"]
            )
    return respuestas


class TestConexionConElDiagnosticoDeIngles:
    def test_hacer_el_diagnostico_de_ames_cambia_el_nivel_de_la_practica(
        self, app_with_db
    ):
        """El camino real, de punta a punta y por HTTP.

        Antes del diagnóstico la práctica de lengua sale con niveles mezclados;
        después de presentar el examen de AMES (el de 60 ítems que YA existe en
        el repo) arranca en el nivel que ese examen determinó. Si alguien
        desconectara las dos piezas, este test es el único que se entera.
        """
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.ames@grasshopper.dev", grade=12)
        with TestClient(app) as client:
            h = _headers(client, "prep.ames@grasshopper.dev")

            antes = client.get(
                f"{BASE}/{EXAMEN_IELTS}/practice?skill=ielts_gramatica&limit=6",
                headers=h,
            ).json()
            assert antes["englishDiagnostic"]["completed"] is False
            assert antes["englishDiagnostic"]["practiceLevel"] is None
            assert len({i["level"] for i in antes["items"]}) > 1

            # 50/60 · la tabla de AMES ubica ese puntaje en B2.
            envio = client.post(
                "/api/v1/english-test/submit",
                json={"answers": _respuestas_de_ames(50)},
                headers=h,
            )
            assert envio.status_code == 200, envio.text
            assert envio.json()["score"] == 50
            assert envio.json()["cefr_level"] == "B2"

            despues = client.get(
                f"{BASE}/{EXAMEN_IELTS}/practice?skill=ielts_gramatica&limit=6",
                headers=h,
            ).json()
            diagnostico = despues["englishDiagnostic"]
            assert diagnostico["completed"] is True
            assert diagnostico["cefrLevel"] == "B2"
            assert diagnostico["practiceLevel"] == NIVEL_AVANZADO
            # Y los ejercicios que llegan ya no son una mezcla: arrancan arriba.
            assert despues["items"][0]["level"] == NIVEL_AVANZADO

    def test_la_equivalencia_ielts_sale_de_la_tabla_de_la_agencia(self, app_with_db):
        """No se calcula aquí: se reusa `placement_for`, que reproduce la tabla
        que publica la propia agencia."""
        app, SessionLocal = app_with_db
        _estudiante(SessionLocal, "prep.equiv@grasshopper.dev", grade=12)
        with TestClient(app) as client:
            h = _headers(client, "prep.equiv@grasshopper.dev")
            client.post(
                "/api/v1/english-test/submit",
                json={"answers": _respuestas_de_ames(50)},
                headers=h,
            )
            cuerpo = client.get(BASE, headers=h).json()
            diagnostico = cuerpo["englishDiagnostic"]
            assert diagnostico["instrument"] == "AMES English Placement Test"
            assert diagnostico["ieltsEquivalent"] == "6.0"
            assert diagnostico["classPlacement"] == "Avanzado académico"

    def test_un_resultado_del_banco_viejo_de_20_no_se_lee_contra_la_tabla_de_60(
        self, app_with_db
    ):
        """Misma salvedad que `english_test.get_result`: un 15/20 leído como
        15/60 diría un nivel que no es."""
        app, SessionLocal = app_with_db
        user_id = _estudiante(
            SessionLocal,
            "prep.viejo@grasshopper.dev",
            english_test_completed=True,
            english_cefr_level="B1",
        )
        from app.db.models import EnglishTestResult

        db = SessionLocal()
        try:
            db.add(
                EnglishTestResult(
                    user_id=user_id,
                    answers={},
                    score=15,
                    total_questions=20,
                    cefr_level="B1",
                    section_scores={},
                )
            )
            db.commit()
        finally:
            db.close()

        with TestClient(app) as client:
            h = _headers(client, "prep.viejo@grasshopper.dev")
            diagnostico = client.get(BASE, headers=h).json()["englishDiagnostic"]
            assert diagnostico["completed"] is True
            # El nivel de práctica sí sale (es el CEFR que la app ya usa)…
            assert diagnostico["practiceLevel"] == NIVEL_INTERMEDIO
            # …pero la equivalencia de la tabla de 60 NO se inventa.
            assert diagnostico["ieltsEquivalent"] is None
            assert diagnostico["classPlacement"] is None
            assert diagnostico["instrument"] is None

    def test_no_se_construyo_un_segundo_diagnostico_de_ingles(self):
        """La clienta ya se quejó de la fatiga de cuestionarios. Si alguien
        agrega aquí un test de nivel propio, este test lo caza: el módulo debe
        apuntar al diagnóstico que ya existe, no reemplazarlo."""
        assert servicio.ENDPOINT_DIAGNOSTICO_INGLES == "/api/v1/english-test/questions"
        u = _usuario()
        info = servicio.diagnostico_de_ingles(None, u)
        assert info["endpoint"] == servicio.ENDPOINT_DIAGNOSTICO_INGLES
        assert "diagnóstico de inglés" in info["message"]
