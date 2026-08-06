"""RM-1 · ¿A quién se le puede mandar un mensaje de acompañamiento?

Se pidió que el asistente contacte cada tanto ("¿cómo vas con tu proyecto?").
Antes de escribir el scheduler hay que poder responder esta pregunta, y hoy no se
podía: no existía ningún consentimiento de comunicaciones.

Lo que protegen estos tests, en orden de importancia:

 1. **Que a un menor sin permiso de sus padres NO se le escriba.** Es la razón
    por la que este trabajo se paró antes de mandar nada.
 2. Que sin fecha de nacimiento se asuma menor. `is_minor` ya lo hace, y aquí se
    fija que la regla siga valiendo para comunicaciones.
 3. Que sea un consentimiento INDEPENDIENTE: aceptar el tratamiento de datos no
    puede implicar aceptar que te escriban.

Si alguien "simplifica" esto reutilizando `has_crm_consent`, varios de estos
tests fallan — y deben fallar: son consentimientos distintos con propósitos
distintos.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.db.models import User
from app.services import consent_service as cs


def _usuario(**kwargs) -> User:
    """Un User en memoria · no toca la base."""
    u = User()
    u.consent_data_processing_at = kwargs.get("datos")
    u.consent_communications_at = kwargs.get("comunicaciones")
    u.consent_parental_at = kwargs.get("parental")
    u.birthdate = kwargs.get("nacimiento")
    return u


AHORA = datetime.utcnow()
MAYOR = date.today() - timedelta(days=365 * 25)
MENOR = date.today() - timedelta(days=365 * 15)


# ---------------------------------------------------------------------------
# Lo que más importa · menores
# ---------------------------------------------------------------------------


def test_a_un_menor_sin_permiso_parental_no_se_le_escribe():
    puede, motivo = cs.can_send_communications(
        _usuario(datos=AHORA, comunicaciones=AHORA, nacimiento=MENOR)
    )
    assert puede is False
    assert motivo == "no_parental_consent"


def test_a_un_menor_CON_permiso_parental_si():
    puede, motivo = cs.can_send_communications(
        _usuario(
            datos=AHORA, comunicaciones=AHORA, parental=AHORA, nacimiento=MENOR
        )
    )
    assert puede is True
    assert motivo is None


def test_sin_fecha_de_nacimiento_se_asume_menor_y_no_se_manda():
    """Ante la duda, no se escribe. `is_minor` es deny-by-default."""
    puede, motivo = cs.can_send_communications(
        _usuario(datos=AHORA, comunicaciones=AHORA, nacimiento=None)
    )
    assert puede is False
    assert motivo == "no_parental_consent"


# ---------------------------------------------------------------------------
# Es un consentimiento independiente
# ---------------------------------------------------------------------------


def test_aceptar_el_tratamiento_de_datos_no_autoriza_a_escribirle():
    puede, motivo = cs.can_send_communications(
        _usuario(datos=AHORA, comunicaciones=None, nacimiento=MAYOR)
    )
    assert puede is False
    assert motivo == "no_communications_consent"


def test_sin_consentimiento_de_datos_tampoco():
    puede, motivo = cs.can_send_communications(
        _usuario(datos=None, comunicaciones=AHORA, nacimiento=MAYOR)
    )
    assert puede is False
    assert motivo == "no_data_processing_consent"


def test_un_adulto_con_ambos_consentimientos_si_recibe():
    puede, motivo = cs.can_send_communications(
        _usuario(datos=AHORA, comunicaciones=AHORA, nacimiento=MAYOR)
    )
    assert puede is True
    assert motivo is None


def test_sin_usuario_no_revienta():
    puede, motivo = cs.can_send_communications(None)
    assert puede is False
    assert motivo == "no_user"


# ---------------------------------------------------------------------------
# Otorgar y revocar · deja rastro auditable
# ---------------------------------------------------------------------------


def test_communications_es_un_tipo_de_consentimiento_valido():
    assert "communications" in cs.CONSENT_KINDS
    assert "communications.granted" in cs.CONSENT_EVENTS
    assert "communications.revoked" in cs.CONSENT_EVENTS


def test_el_estado_de_consentimientos_lo_incluye():
    """La persona tiene que poder verlo y revocarlo en la misma pantalla."""
    estado = cs.consent_state(
        _usuario(datos=AHORA, comunicaciones=AHORA, nacimiento=MAYOR)
    )
    assert estado["communications"]["granted"] is True
    assert estado["communications"]["granted_at"] is not None


def test_revocar_deja_de_permitir_el_envio():
    u = _usuario(datos=AHORA, comunicaciones=AHORA, nacimiento=MAYOR)
    assert cs.can_send_communications(u)[0] is True
    u.consent_communications_at = None
    assert cs.can_send_communications(u)[0] is False
