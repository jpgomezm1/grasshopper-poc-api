"""G-4 / G-5 · Sprint 4 · avisos al equipo comercial y topes del bot gratuito.

Lo que protegen:
 G-4
  1. Un caliente del bot gratuito avisa: notificación en la app a cada comercial
     activo y un correo con lo que el asesor necesita antes de llamar.
  2. A quién va el correo: a los comerciales activos, o solo a
     `AVISO_PROSPECTOS_EMAIL` si está configurada (decidido por JP).
  3. Un tibio no avisa al momento; el perfilador avisa UNA vez aunque recalcule
     en cada turno.
  4. El resumen diario solo lleva los tibios nuevos de 24 horas, y no manda nada
     si no hay.
 G-5
  5. El mismo contacto con las mismas respuestas en 10 minutos (un reenvío) no
     crea otro prospecto ni otro aviso; con respuestas distintas sí (dos hijos).
  6. Hay tope diario por IP además del de por minuto.

Se mockea la frontera del correo (`email_service.send_email`), no el aviso.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import RESPUESTAS, URL, _leads, _pedido, app_db  # noqa: F401
from tests.test_planes_d1 import _usuario


@pytest.fixture()
def correos(monkeypatch):
    enviados = []

    def falso(*, to, subject, html_body, text_body=None):
        enviados.append({"to": to, "subject": subject, "html": html_body, "text": text_body})

    monkeypatch.setattr("app.services.email_service.send_email", falso)
    return enviados


@pytest.fixture()
def equipo(app_db):
    from app.db.models import UserRole

    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "ana.comercial@g4.dev", role=UserRole.GH_COMMERCIAL)
    _usuario(s, "beto.comercial@g4.dev", role=UserRole.GH_COMMERCIAL)
    inactivo = _usuario(s, "viejo.comercial@g4.dev", role=UserRole.GH_COMMERCIAL)
    inactivo.is_active = False
    _usuario(s, "orientadora@g4.dev", role=UserRole.GH_ADVISOR)
    s.commit()
    s.close()
    return app, Sesion


def _contacto(nombre="Sara", email="sara@correo.com", cuando="soon", whatsapp="+57 300 000 0000"):
    return {"nombre": nombre, "whatsapp": whatsapp, "email": email, "cuando": cuando}


def _notificaciones(Sesion, tipo="prospecto.caliente"):
    from app.db.models import Notification

    s = Sesion()
    try:
        return s.query(Notification).filter(Notification.type == tipo).all()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# G-4
# ---------------------------------------------------------------------------


def test_un_caliente_avisa_en_la_app_y_por_correo_a_los_comerciales_activos(equipo, correos):
    app, Sesion = equipo
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(contacto=_contacto()))
    assert r.status_code == 200, r.text

    [lead] = _leads(Sesion)
    assert lead.band == "hot"
    assert lead.hechos.get("_aviso_caliente")

    notifs = _notificaciones(Sesion)
    assert len(notifs) == 2  # Ana y Beto; ni el inactivo ni la orientadora
    assert notifs[0].title == "Prospecto caliente: Sara"

    assert sorted(m["to"] for m in correos) == ["ana.comercial@g4.dev", "beto.comercial@g4.dev"]
    correo = correos[0]
    assert correo["subject"] == "Prospecto caliente: Sara"
    for dato in ("sara@correo.com", "Estudiante de colegio", "11°", "/gh/prospectos"):
        assert dato in correo["text"], dato


def test_con_correo_fijo_configurado_va_solo_ahi(equipo, correos, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "aviso_prospectos_email", "ventas@agencia.co, jefe@agencia.co")
    app, _ = equipo
    with TestClient(app) as c:
        c.post(URL, json=_pedido(contacto=_contacto()))
    assert sorted(m["to"] for m in correos) == ["jefe@agencia.co", "ventas@agencia.co"]


def test_un_tibio_no_avisa_al_momento(equipo, correos):
    app, Sesion = equipo
    with TestClient(app) as c:
        c.post(URL, json=_pedido(
            respuestas={**RESPUESTAS, "budget": "b1"}, contacto=_contacto(cuando="later"),
        ))
    [lead] = _leads(Sesion)
    assert lead.band == "warm"
    assert correos == [] and _notificaciones(Sesion) == []


def test_avisar_dos_veces_el_mismo_prospecto_no_manda_dos(equipo, correos):
    """El perfilador recalcula en cada turno: sin la marca, un correo por mensaje."""
    from app.db.models import BotConversation
    from app.services import aviso_prospectos

    _, Sesion = equipo
    s = Sesion()
    lead = BotConversation(name="Pedro", email="p@correo.com", hechos={}, transcript=[], band="hot", score=90)
    s.add(lead)
    s.commit()
    assert aviso_prospectos.avisar_caliente(s, lead) is True
    assert aviso_prospectos.avisar_caliente(s, lead) is False
    s.close()
    assert len(correos) == 2  # una vez, a los dos comerciales


def test_si_el_correo_falla_el_bot_igual_responde(equipo, monkeypatch):
    def roto(**_):
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr("app.services.email_service.send_email", roto)
    app, Sesion = equipo
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(contacto=_contacto()))
    assert r.status_code == 200
    assert len(_leads(Sesion)) == 1


def test_el_resumen_diario_lleva_solo_los_tibios_nuevos_de_24_horas(equipo, correos):
    from app.db.models import BotConversation
    from app.services import aviso_prospectos

    _, Sesion = equipo
    s = Sesion()
    ahora = datetime.utcnow()
    base = dict(hechos={"_fuente": "bot_gratuito", "respuestas": {}}, transcript=[], band="warm", route="perfilamiento")
    s.add(BotConversation(name="Tibio Hoy", email="hoy@correo.com", created_at=ahora - timedelta(hours=2), **base))
    s.add(BotConversation(name="Tibio Viejo", email="viejo@correo.com", created_at=ahora - timedelta(days=3), **base))
    s.add(BotConversation(name="Tibio Contactado", email="c@correo.com", created_at=ahora - timedelta(hours=1),
                          estado="contactado", **base))
    s.commit()
    assert aviso_prospectos.resumen_tibios(s, ahora=ahora) == 1
    s.close()
    assert {m["to"] for m in correos} == {"ana.comercial@g4.dev", "beto.comercial@g4.dev"}
    assert "Tibio Hoy" in correos[0]["text"]
    assert "Tibio Viejo" not in correos[0]["text"] and "Tibio Contactado" not in correos[0]["text"]


def test_sin_tibios_no_se_manda_nada(equipo, correos):
    from app.services import aviso_prospectos

    _, Sesion = equipo
    s = Sesion()
    assert aviso_prospectos.resumen_tibios(s) == 0
    s.close()
    assert correos == []


# ---------------------------------------------------------------------------
# G-5
# ---------------------------------------------------------------------------


def test_el_mismo_contacto_en_10_minutos_no_crea_otro_ni_avisa_otra_vez(equipo, correos):
    app, Sesion = equipo
    with TestClient(app) as c:
        a = c.post(URL, json=_pedido(contacto=_contacto()))
        b = c.post(URL, json=_pedido(contacto=_contacto(whatsapp="")))  # mismo correo
        otro = c.post(URL, json=_pedido(contacto=_contacto(nombre="Otra", email="otra@correo.com",
                                                             whatsapp="+57 311 111 1111")))
    assert a.json()["lead_id"] == b.json()["lead_id"]
    assert otro.json()["lead_id"] != a.json()["lead_id"]
    assert len(_leads(Sesion)) == 2
    assert len(correos) == 4  # dos prospectos × dos comerciales, no tres


def test_el_mismo_contacto_con_otras_respuestas_si_es_otro_prospecto(equipo, correos):
    """Un papá o una mamá que llena el bot para dos hijos usa el mismo WhatsApp."""
    app, Sesion = equipo
    with TestClient(app) as c:
        a = c.post(URL, json=_pedido(contacto=_contacto()))
        b = c.post(URL, json=_pedido(respuestas={**RESPUESTAS, "stage": "9"}, contacto=_contacto()))
    assert a.json()["lead_id"] != b.json()["lead_id"]
    assert len(_leads(Sesion)) == 2


def test_despues_de_10_minutos_si_crea_uno_nuevo(equipo, correos):
    app, Sesion = equipo
    with TestClient(app) as c:
        a = c.post(URL, json=_pedido(contacto=_contacto()))
        s = Sesion()
        [lead] = _leads(Sesion)
        s.query(type(lead)).filter(type(lead).id == lead.id).update(
            {"created_at": datetime.utcnow() - timedelta(minutes=11)}
        )
        s.commit()
        s.close()
        b = c.post(URL, json=_pedido(contacto=_contacto()))
    assert a.json()["lead_id"] != b.json()["lead_id"]


def test_hay_tope_diario_ademas_del_de_por_minuto():
    from app.api.v1 import bot_gratuito
    from app.main import app

    assert bot_gratuito.TOPE_DIARIO == "200/day"
    [ruta] = [r for r in app.routes if getattr(r, "path", "") == "/api/v1/bot-gratuito/lead"]
    deps = {d.call for d in ruta.dependant.dependencies}
    assert {bot_gratuito._rate_limit, bot_gratuito._tope_diario} <= deps
