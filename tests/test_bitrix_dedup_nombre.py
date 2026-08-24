"""Bitrix · el cambio de nombre de un estudiante nunca llegaba al CRM.

Encontrado el 2026-08-07 verificando otra cosa. Es un bug de producción sobre el
CRM del cliente, no una molestia interna: si una estudiante corrige su nombre
—porque lo escribió mal al registrarse, o porque se casó, o porque usa su
segundo nombre— el asesor la sigue llamando como estaba antes.

## La causa

`_is_duplicate_of_last` comparaba **los dos lados enmascarados**:

    _payload_hash(prior.payload) == _payload_hash(safe_summary(fields))

`prior.payload` es lo que quedó guardado en el log, que ya pasó por
`safe_summary` — y esa función convierte cualquier campo con "name" en `***`
(correcto: los logs no deben llevar PII). Al enmascarar también el lado nuevo,
`NAME: "Ana"` y `NAME: "Ana María"` producen el MISMO hash. El cambio se
declaraba duplicado y no se sincronizaba nunca.

El `TITLE` del lead tampoco salva la situación: no lleva el nombre.

## La forma del arreglo

El log **sigue guardando el payload enmascarado** — eso no se toca, es lo
correcto para PII. Lo que se agrega es un hash del payload REAL en su propia
columna. Así el dedup compara datos reales sin que el nombre quede escrito en
ningún log.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)
    s = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield s
    finally:
        s.close()


CAMPOS_BASE = {
    "TITLE": "Lead Mentoring",
    "NAME": "Ana",
    "LAST_NAME": "Ruiz",
    "EMAIL": [{"VALUE": "ana@test.com"}],
    "UF_CRM_SCORE": 72,
}


def _log(db, fields, action="create_lead"):
    """Guarda un log como lo hace producción: payload enmascarado + hash real."""
    from app.db.models import BitrixSyncLog
    from app.services.bitrix_sync_service import _payload_hash
    from app.services.bitrix_client import safe_summary

    fila = BitrixSyncLog(
        entity_type="lead",
        entity_id="123",
        action=action,
        payload=safe_summary(fields),
        payload_hash=_payload_hash(fields),
        status="success",
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def test_cambiar_el_nombre_SI_se_sincroniza(db):
    """El bug, en una línea.

    Antes: `NAME: "Ana"` y `NAME: "Ana María"` daban el mismo hash porque los
    dos se enmascaraban a `***`. El cambio se descartaba como duplicado.
    """
    from app.services.bitrix_sync_service import _is_duplicate_of_last

    previo = _log(db, CAMPOS_BASE)
    con_nombre_nuevo = {**CAMPOS_BASE, "NAME": "Ana María"}

    assert _is_duplicate_of_last(previo, con_nombre_nuevo) is False


def test_cambiar_el_apellido_tambien(db):
    from app.services.bitrix_sync_service import _is_duplicate_of_last

    previo = _log(db, CAMPOS_BASE)
    assert _is_duplicate_of_last(previo, {**CAMPOS_BASE, "LAST_NAME": "Ruiz Gómez"}) is False


def test_cambiar_el_correo_tambien(db):
    """`safe_summary` enmascara el correo a `a***@test.com`, así que dos correos
    con la misma primera letra y dominio colisionaban igual."""
    from app.services.bitrix_sync_service import _is_duplicate_of_last

    previo = _log(db, CAMPOS_BASE)
    otro = {**CAMPOS_BASE, "EMAIL": [{"VALUE": "ana.ruiz@test.com"}]}
    assert _is_duplicate_of_last(previo, otro) is False


def test_un_payload_identico_sigue_siendo_duplicado(db):
    """El dedup no se rompió: para eso existe, y evita llamadas redundantes a
    Bitrix cada vez que se dispara un trigger sin que nada haya cambiado."""
    from app.services.bitrix_sync_service import _is_duplicate_of_last

    previo = _log(db, CAMPOS_BASE)
    assert _is_duplicate_of_last(previo, dict(CAMPOS_BASE)) is True


def test_el_orden_de_las_claves_no_cambia_el_hash(db):
    """`json.dumps(sort_keys=True)` · un dict reordenado es el mismo payload."""
    from app.services.bitrix_sync_service import _is_duplicate_of_last

    previo = _log(db, CAMPOS_BASE)
    reordenado = dict(reversed(list(CAMPOS_BASE.items())))
    assert _is_duplicate_of_last(previo, reordenado) is True


def test_el_log_sigue_SIN_el_nombre_en_claro(db):
    """El arreglo no puede filtrar PII a los logs · eso es lo que `safe_summary`
    protege y sigue vigente. El hash es irreversible."""
    fila = _log(db, CAMPOS_BASE)

    assert fila.payload["NAME"] == "***"
    assert fila.payload["LAST_NAME"] == "***"
    assert "Ana" not in str(fila.payload)
    assert "Ruiz" not in str(fila.payload)
    # …y el hash no deja leer el nombre.
    assert "Ana" not in fila.payload_hash


def test_un_skip_dedup_no_cuenta_como_ultima_sincronizacion(db):
    """La causa de que `test_sync_user_lead_creates_then_updates` fuera
    intermitente (fallaba ~1 de cada 3).

    El `skip_dedup` se guarda con estado exitoso, así que entraba en la consulta
    de "última sincronización". Pero su `payload` es un marcador
    (`{"reason": "payload_unchanged"}`), no los campos enviados: comparar contra
    él **nunca** da duplicado.

    Con marcas de tiempo empatadas, el `prior` salía unas veces el `create` (y
    entonces el bug del nombre enmascarado afloraba → el test fallaba) y otras
    el `skip_dedup` (que nunca deduplica → el test pasaba por casualidad). Dos
    defectos tapándose el uno al otro.
    """
    from app.db.models import BitrixSyncLog
    from app.services.bitrix_sync_service import _last_successful_log, _payload_hash
    from app.services.bitrix_client import safe_summary

    real = BitrixSyncLog(
        entity_type="user", entity_id="u1", action="create",
        payload=safe_summary(CAMPOS_BASE), payload_hash=_payload_hash(CAMPOS_BASE),
        status="stub",
    )
    db.add(real)
    db.commit()

    marcador = BitrixSyncLog(
        entity_type="user", entity_id="u1", action="skip_dedup",
        payload={"reason": "payload_unchanged"},
        payload_hash=_payload_hash({"reason": "payload_unchanged"}),
        status="stub",
    )
    db.add(marcador)
    db.commit()

    ultimo = _last_successful_log(db, entity_type="user", entity_id="u1")
    assert ultimo is not None
    assert ultimo.action == "create", "el marcador de skip se tomó como sincronización"
    assert ultimo.id == real.id


def test_un_log_viejo_sin_hash_no_bloquea_la_sincronizacion(db):
    """Compatibilidad hacia atrás · las filas anteriores a la migración tienen
    `payload_hash` NULL.

    Ante la duda se SINCRONIZA: una llamada de más a Bitrix es barata; un
    cambio que no llega al CRM es el bug que estamos arreglando.
    """
    from app.db.models import BitrixSyncLog
    from app.services.bitrix_client import safe_summary
    from app.services.bitrix_sync_service import _is_duplicate_of_last

    viejo = BitrixSyncLog(
        entity_type="lead", entity_id="123", action="create_lead",
        payload=safe_summary(CAMPOS_BASE), payload_hash=None, status="success",
    )
    db.add(viejo)
    db.commit()

    assert _is_duplicate_of_last(viejo, dict(CAMPOS_BASE)) is False
