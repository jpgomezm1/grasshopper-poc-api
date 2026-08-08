"""RM-1 · El acompañamiento periódico · a quién se le escribe y a quién no.

Verónica, 21-07: *"periódicamente él debe escribirte: hola, ¿cómo vas con tu
proyecto? ¿tomaste el curso de inglés?… él se vuelve tu amigo"*.

**Este archivo protege sobre todo lo que NO debe pasar.** Un bug aquí no rompe
una pantalla: le manda correo a un menor de edad sin permiso de sus padres, o
convierte al asistente en spam. En orden de gravedad:

  1. Con el kill switch apagado no sale nada. Es lo que permite desplegar esto y
     agendar el cron sin que le llegue nada a nadie.
  2. Sin consentimiento explícito no sale nada — y "no dio permiso" incluye "no
     sabemos su edad", porque `is_minor` asume menor cuando falta la fecha.
  3. A un menor sin consentimiento parental no le llega nada.
  4. A nadie se le escribe dos veces seguidas.
  5. A quien está al día no se le escribe.

El modelo se mockea en la FRONTERA (`call_claude_tool`), no la función que se
está probando: es la regla que el repo documenta después de que once tests en
verde convivieran con una funcionalidad rota al 100%.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import outreach_sender as snd
from app.services import outreach_service as svc


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture(autouse=True)
def _sin_modelo_real(monkeypatch):
    """Frontera mockeada · el redactor cree que habló con Claude."""
    from app.core import ai_client

    monkeypatch.setattr(
        ai_client,
        "call_claude_tool",
        lambda *a, **k: (
            {"cuerpo": "Vi que dejaste algo a medias y quería recordártelo con calma.",
             "cta": "Continuar"},
            {},
        ),
    )
    from app.services import outreach_writer

    monkeypatch.setattr(outreach_writer, "call_claude_tool", ai_client.call_claude_tool)
    yield


@pytest.fixture(autouse=True)
def _apagado_por_defecto(monkeypatch):
    """El estado real de produccion: el interruptor viene apagado."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _prender(monkeypatch, **extra):
    from app.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    monkeypatch.setattr(s, "outreach_enabled", True, raising=False)
    for k, v in extra.items():
        monkeypatch.setattr(s, k, v, raising=False)
    return s


HACE_MUCHO = datetime.utcnow() - timedelta(days=40)


def _estudiante(db, **kw):
    from app.db.models import User, UserRole

    campos = dict(
        email=kw.pop("email", "e@test.com"),
        hashed_password="x",
        name="Ana Ruiz",
        role=UserRole.STUDENT,
        is_active=True,
        created_at=HACE_MUCHO,
        # Por defecto: consintió todo y es mayor de edad.
        birthdate=datetime(2000, 1, 1).date(),
        consent_data_processing_at=HACE_MUCHO,
        consent_communications_at=HACE_MUCHO,
    )
    campos.update(kw)
    u = User(**campos)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _sesion(db, user, *, completada=False, actualizada=HACE_MUCHO):
    from app.db.models import Session as DBSession

    s = DBSession(user_id=user.id, answers={}, is_completed=completada)
    db.add(s)
    db.commit()
    s.updated_at = actualizada
    db.commit()
    db.refresh(s)
    return s


def _con_tests(monkeypatch, valor: bool):
    from app.services import recommendation_service as rs

    monkeypatch.setattr(rs, "user_has_tests", lambda db, user: valor)


# ---------------------------------------------------------------------------
# 1 · El kill switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_apagado_no_sale_nada(self, db, monkeypatch):
        """EL test de este archivo. Permite desplegar el motor y agendar el cron
        sin que le llegue un solo correo a nadie."""
        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        enviados = []
        from app.services import email_service

        monkeypatch.setattr(
            email_service, "send_email", lambda **k: enviados.append(k)
        )

        r = snd.enviar(db, u, svc.detectar_motivo(db, u))
        assert r.resultado == snd.APAGADO
        assert enviados == []

    def test_apagado_ni_siquiera_llama_al_modelo(self, db, monkeypatch):
        """No se gastan tokens redactando mensajes que no van a salir."""
        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        llamadas = []
        from app.services import outreach_writer

        monkeypatch.setattr(
            outreach_writer, "call_claude_tool",
            lambda *a, **k: llamadas.append(1) or ({"cuerpo": "x" * 50, "cta": "y"}, {}),
        )

        snd.enviar(db, u, svc.detectar_motivo(db, u))
        assert llamadas == []

    def test_el_apagado_queda_registrado(self, db, monkeypatch):
        """Para poder responder despues 'por que no le llego nada a nadie'."""
        from app.db.models import OutreachLog

        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        snd.enviar(db, u, svc.detectar_motivo(db, u))

        fila = db.query(OutreachLog).one()
        assert fila.resultado == snd.APAGADO
        assert fila.detalle == "outreach_enabled=false"


# ---------------------------------------------------------------------------
# 2 y 3 · Consentimiento y menores
# ---------------------------------------------------------------------------

class TestConsentimiento:
    def test_sin_consentimiento_de_comunicaciones_no_sale_nada(self, db, monkeypatch):
        _prender(monkeypatch)
        _con_tests(monkeypatch, False)
        u = _estudiante(db, consent_communications_at=None)
        enviados = []
        from app.services import email_service

        monkeypatch.setattr(email_service, "send_email", lambda **k: enviados.append(k))

        r = snd.enviar(db, u, svc.detectar_motivo(db, u))
        assert r.resultado == snd.SIN_CONSENTIMIENTO
        assert r.detalle == "no_communications_consent"
        assert enviados == []

    def test_a_un_menor_sin_permiso_parental_no_le_llega_nada(self, db, monkeypatch):
        _prender(monkeypatch)
        _con_tests(monkeypatch, False)
        menor = _estudiante(
            db,
            birthdate=(datetime.utcnow() - timedelta(days=365 * 14)).date(),
            consent_parental_at=None,
        )
        enviados = []
        from app.services import email_service

        monkeypatch.setattr(email_service, "send_email", lambda **k: enviados.append(k))

        r = snd.enviar(db, menor, svc.detectar_motivo(db, menor))
        assert r.resultado == snd.SIN_CONSENTIMIENTO
        assert r.detalle == "no_parental_consent"
        assert enviados == []

    def test_sin_fecha_de_nacimiento_se_asume_menor(self, db, monkeypatch):
        """`is_minor` devuelve True cuando no hay fecha · ante la duda, nada."""
        _prender(monkeypatch)
        _con_tests(monkeypatch, False)
        u = _estudiante(db, birthdate=None, consent_parental_at=None)

        r = snd.enviar(db, u, svc.detectar_motivo(db, u))
        assert r.resultado == snd.SIN_CONSENTIMIENTO

    def test_con_todo_en_regla_si_sale(self, db, monkeypatch):
        """El caso feliz · si esto falla, RM-1 no sirve para nada."""
        _prender(monkeypatch)
        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        enviados = []
        from app.services import email_service, outreach_sender

        class _Ok:
            delivered = True
            reason = None

        monkeypatch.setattr(
            email_service, "send_email", lambda **k: enviados.append(k) or _Ok()
        )
        monkeypatch.setattr(outreach_sender, "send_email", email_service.send_email, raising=False)

        r = snd.enviar(db, u, svc.detectar_motivo(db, u))
        assert r.resultado == snd.ENVIADO
        assert len(enviados) == 1
        assert enviados[0]["to"] == u.email

    def test_el_gate_por_fin_se_llama_desde_produccion(self, db, monkeypatch):
        """Hasta esta tanda `can_send_communications` sólo la llamaban tests: el
        campo existía y ningún camino real lo leía."""
        _prender(monkeypatch)
        _con_tests(monkeypatch, False)
        llamadas = []
        from app.services import consent_service, outreach_sender

        original = consent_service.can_send_communications
        monkeypatch.setattr(
            outreach_sender, "can_send_communications",
            lambda u: llamadas.append(u.id) or original(u),
        )
        u = _estudiante(db)
        snd.enviar(db, u, svc.detectar_motivo(db, u))
        assert llamadas == [u.id]


# ---------------------------------------------------------------------------
# 4 · No convertirse en spam
# ---------------------------------------------------------------------------

class TestFrecuencia:
    def test_no_se_le_escribe_dos_veces_seguidas(self, db, monkeypatch):
        from app.db.models import OutreachLog

        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        db.add(OutreachLog(
            user_id=u.id, motivo="sin_tests", canal="email", resultado=snd.ENVIADO,
        ))
        db.commit()

        assert svc.ya_se_le_escribio_hace_poco(db, u) is True
        assert [x[0].id for x in svc.candidatos(db)] == []

    def test_pasado_el_plazo_vuelve_a_entrar(self, db, monkeypatch):
        from app.db.models import OutreachLog

        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        viejo = OutreachLog(
            user_id=u.id, motivo="sin_tests", canal="email", resultado=snd.ENVIADO,
        )
        db.add(viejo)
        db.commit()
        viejo.created_at = datetime.utcnow() - timedelta(
            days=svc.DIAS_ENTRE_MENSAJES + 1
        )
        db.commit()

        assert svc.ya_se_le_escribio_hace_poco(db, u) is False

    def test_un_simulacro_no_bloquea_el_envio_real(self, db, monkeypatch):
        """El preview escribe filas `simulacro`. Si contaran como "ya le
        escribimos", revisar el preview con la clienta dejaría a esa persona sin
        mensaje por 14 días — y el preview es justo lo que se hace ANTES de
        prender el interruptor."""
        from app.db.models import OutreachLog

        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        db.add(OutreachLog(
            user_id=u.id, motivo="sin_tests", canal="email", resultado=snd.SIMULACRO,
        ))
        db.commit()

        assert svc.ya_se_le_escribio_hace_poco(db, u) is False

    def test_una_corrida_con_el_switch_apagado_no_bloquea_nada(self, db, monkeypatch):
        """El defecto más grave de esta tanda, y el más fácil de no ver.

        El despliegue recomendado es: agendar el cron con el interruptor APAGADO
        (para que corra de verdad sin mandar nada), revisar el preview, y recién
        ahí prender. Si las filas `apagado` contaran como "ya le escribimos",
        al prender el interruptor **nadie recibiría nada durante 14 días** — la
        funcionalidad se vería rota justo cuando la clienta la está mirando.
        """
        from app.db.models import OutreachLog

        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        db.add(OutreachLog(
            user_id=u.id, motivo="sin_tests", canal="email", resultado=snd.APAGADO,
        ))
        db.commit()

        assert svc.ya_se_le_escribio_hace_poco(db, u) is False
        assert [x[0].id for x in svc.candidatos(db)] == [u.id]

    def test_un_no_envio_por_falta_de_permiso_tampoco_bloquea(self, db, monkeypatch):
        """Si la persona da el permiso mañana, no tiene que esperar 14 días."""
        from app.db.models import OutreachLog

        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        db.add(OutreachLog(
            user_id=u.id, motivo="sin_tests", canal="email",
            resultado=snd.SIN_CONSENTIMIENTO,
        ))
        db.commit()

        assert svc.ya_se_le_escribio_hace_poco(db, u) is False

    def test_el_tope_es_por_persona_no_por_motivo(self, db, monkeypatch):
        """Alternar motivos para escribir cada semana es exactamente lo que
        convierte a un asistente en spam."""
        from app.db.models import OutreachLog

        from app.db.models import Route

        _con_tests(monkeypatch, True)
        u = _estudiante(db, english_test_completed=False)
        s = _sesion(db, u, completada=True)
        db.add(Route(
            session_id=s.id, key="k", name="Ruta", why="w",
            what_it_looks_like="x", next_step="y",
        ))
        db.add(OutreachLog(
            user_id=u.id, motivo="sin_tests", canal="email", resultado=snd.ENVIADO,
        ))
        db.commit()

        # Su motivo AHORA seria otro (ingles), pero igual no se le escribe.
        assert svc.detectar_motivo(db, u).clave == "ingles_pendiente"
        assert svc.candidatos(db) == []


# ---------------------------------------------------------------------------
# 5 · A quién se le escribe y por qué
# ---------------------------------------------------------------------------

class TestDeteccion:
    def test_quien_esta_al_dia_no_recibe_nada(self, db, monkeypatch):
        """Devolver None es el resultado deseable, no un fallo. Un mensaje sin
        nada específico que decir entrena a la gente a ignorar los que sí."""
        _con_tests(monkeypatch, True)
        u = _estudiante(db, english_test_completed=True, english_cefr_level="C1")
        s = _sesion(db, u, completada=True)
        from app.db.models import Route

        db.add(Route(
            session_id=s.id, key="k", name="Ruta", why="w",
            what_it_looks_like="x", next_step="y",
        ))
        db.commit()

        assert svc.detectar_motivo(db, u) is None

    def test_sin_tests_es_el_primer_motivo(self, db, monkeypatch):
        _con_tests(monkeypatch, False)
        u = _estudiante(db)
        assert svc.detectar_motivo(db, u).clave == "sin_tests"

    def test_journey_a_medias(self, db, monkeypatch):
        """El caso exacto de Verónica: hizo tests y dejó el recorrido a medias."""
        _con_tests(monkeypatch, True)
        u = _estudiante(db)
        _sesion(db, u, completada=False)
        assert svc.detectar_motivo(db, u).clave == "journey_a_medias"

    def test_el_ingles_es_la_pregunta_que_ella_puso_de_ejemplo(self, db, monkeypatch):
        """*"¿tomaste el curso de inglés?"* · literal de la reunión.

        Con rutas ya generadas, el inglés queda como el único paso pendiente.
        """
        from app.db.models import Route

        _con_tests(monkeypatch, True)
        u = _estudiante(db, english_test_completed=False)
        s = _sesion(db, u, completada=True)
        db.add(Route(
            session_id=s.id, key="k", name="Ruta", why="w",
            what_it_looks_like="x", next_step="y",
        ))
        db.commit()

        assert svc.detectar_motivo(db, u).clave == "ingles_pendiente"

    def test_un_nivel_bajo_tambien_dispara_lo_del_ingles(self, db, monkeypatch):
        """Presentar el examen no basta: un B1 limita a qué puede aplicar."""
        from app.db.models import Route

        _con_tests(monkeypatch, True)
        u = _estudiante(db, english_test_completed=True, english_cefr_level="B1")
        s = _sesion(db, u, completada=True)
        db.add(Route(
            session_id=s.id, key="k", name="Ruta", why="w",
            what_it_looks_like="x", next_step="y",
        ))
        db.commit()

        assert svc.detectar_motivo(db, u).clave == "ingles_pendiente"

    def test_a_quien_acaba_de_entrar_no_se_le_escribe(self, db, monkeypatch):
        """Sin 7 días de inactividad no hay mensaje: si no, se le escribe a
        quien simplemente no entró el fin de semana."""
        _con_tests(monkeypatch, False)
        u = _estudiante(db, created_at=datetime.utcnow())
        _sesion(db, u, actualizada=datetime.utcnow())
        assert svc.detectar_motivo(db, u) is None

    def test_nadie_queda_invisible_por_el_tope_de_la_corrida(self, db, monkeypatch):
        """El tope por corrida no puede mirar SIEMPRE a la misma gente.

        `candidatos` limitaba la consulta de usuarios sin orden ni rotación: los
        que quedaban fuera del primer bloque no habrían recibido un mensaje
        nunca, y nadie se habría enterado — la corrida reporta "revisados=N" y
        se ve sana.
        """
        _con_tests(monkeypatch, False)
        usuarios = [_estudiante(db, email=f"u{i}@test.com") for i in range(5)]

        vistos = set()
        for _ in range(5):
            lista = svc.candidatos(db, limite=2)
            for u, _m in lista:
                vistos.add(u.id)
                # Simula el envío para que no vuelva a salir en la próxima.
                from app.db.models import OutreachLog

                db.add(OutreachLog(
                    user_id=u.id, motivo="sin_tests", canal="email",
                    resultado=snd.ENVIADO,
                ))
            db.commit()

        assert vistos == {u.id for u in usuarios}, (
            "hay estudiantes que el motor nunca mira"
        )

    def test_a_los_asesores_no_se_les_escribe(self, db, monkeypatch):
        """Al asesor ya le llegan sus resúmenes de CRM · son otra cosa."""
        from app.db.models import UserRole

        _con_tests(monkeypatch, False)
        asesor = _estudiante(db, email="asesor@test.com", role=UserRole.GH_ADVISOR)
        assert svc.detectar_motivo(db, asesor) is None


# ---------------------------------------------------------------------------
# El redactor
# ---------------------------------------------------------------------------

class TestRedaccion:
    def test_si_la_ia_falla_sale_la_plantilla_del_motivo(self, db, monkeypatch):
        """Un correo que no sale porque el modelo se cayó es un estudiante que
        no vuelve. La plantilla dice menos, pero dice algo cierto."""
        from app.services import outreach_writer

        def _explota(*a, **k):
            raise RuntimeError("sin red")

        monkeypatch.setattr(outreach_writer, "call_claude_tool", _explota)
        motivo = svc.Motivo(
            clave="sin_tests", asunto="a", contexto="c", destino="/tests"
        )
        m = outreach_writer.redactar(motivo, nombre="Ana", user_id="u1")
        assert m.es_plantilla is True
        assert "test" in m.cuerpo.lower()

    def test_un_cuerpo_vacio_tambien_cae_en_la_plantilla(self, monkeypatch):
        from app.services import outreach_writer

        monkeypatch.setattr(
            outreach_writer, "call_claude_tool",
            lambda *a, **k: ({"cuerpo": "ok", "cta": "y"}, {}),
        )
        motivo = svc.Motivo(
            clave="sin_tests", asunto="a", contexto="c", destino="/tests"
        )
        assert outreach_writer.redactar(motivo, nombre="Ana", user_id="u1").es_plantilla

    def test_cada_motivo_tiene_su_plantilla(self):
        from app.services.outreach_writer import _PLANTILLAS

        for clave in svc._ORDEN:
            assert clave in _PLANTILLAS, f"falta plantilla de respaldo para {clave}"

    def test_el_correo_lleva_como_dejar_de_recibirlo(self, monkeypatch):
        """Requisito legal y de decencia · Ley 1581 art. 8.e."""
        from app.services.outreach_writer import Mensaje

        html = snd._html(
            "Ana", Mensaje(cuerpo="hola", cta="Ir", es_plantilla=True), "/tests"
        )
        assert "/preferencias" in html
        assert "dejar de recibirlos" in html


# ---------------------------------------------------------------------------
# El disparador
# ---------------------------------------------------------------------------

class TestDisparador:
    def test_sin_secreto_configurado_el_endpoint_esta_cerrado(self, monkeypatch):
        """Es preferible que el cron falle a que quede una URL pública capaz de
        dispararle correos a toda la base."""
        from fastapi import HTTPException
        from app.api.v1 import outreach
        from app.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setattr(get_settings(), "outreach_cron_secret", "", raising=False)
        with pytest.raises(HTTPException) as e:
            outreach._verificar_secreto("lo-que-sea")
        assert e.value.status_code == 503

    def test_secreto_incorrecto_da_401(self, monkeypatch):
        from fastapi import HTTPException
        from app.api.v1 import outreach
        from app.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setattr(get_settings(), "outreach_cron_secret", "bueno", raising=False)
        with pytest.raises(HTTPException) as e:
            outreach._verificar_secreto("malo")
        assert e.value.status_code == 401

    def test_secreto_correcto_pasa(self, monkeypatch):
        from app.api.v1 import outreach
        from app.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setattr(get_settings(), "outreach_cron_secret", "bueno", raising=False)
        outreach._verificar_secreto("bueno")  # no lanza
