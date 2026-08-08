"""Bitrix · hash del payload real, para que el cambio de nombre SÍ se sincronice
(2026-08-07).

Revision ID: 058_bitrix_payload_hash
Revises: 057_outreach_logs
Create Date: 2026-08-07

Bug de producción sobre el CRM del cliente. `_is_duplicate_of_last` comparaba
los dos lados **enmascarados**:

    _payload_hash(prior.payload) == _payload_hash(safe_summary(fields))

`safe_summary` convierte cualquier campo con "name" en `***` — correcto, porque
los logs no deben llevar PII. Pero al enmascarar también el lado nuevo,
`NAME: "Ana"` y `NAME: "Ana María"` daban el MISMO hash: el cambio se declaraba
duplicado y **nunca se sincronizaba**. Lo mismo con el apellido y con correos que
compartieran primera letra y dominio.

`bitrix_sync_log.payload_hash` guarda el hash del payload REAL. El `payload`
sigue enmascarado — el arreglo no filtra PII a los logs, porque un hash es
irreversible.

NULL en las filas existentes. El dedup lo trata como "no sé" y sincroniza: una
llamada de más a Bitrix es barata, un cambio que no llega al CRM es el bug que
esto arregla.

Aditiva, nullable e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '058_bitrix_payload_hash'
down_revision = '057_outreach_logs'
branch_labels = None
depends_on = None

_TABLE = 'bitrix_sync_log'
_COLUMNA = 'payload_hash'
_INDICE = 'ix_bitrix_sync_log_payload_hash'


def _tiene_columna(bind, tabla: str, columna: str) -> bool:
    try:
        return columna in {c['name'] for c in inspect(bind).get_columns(tabla)}
    except Exception:
        return False


def _tiene_indice(bind, tabla: str, indice: str) -> bool:
    try:
        return indice in {i['name'] for i in inspect(bind).get_indexes(tabla)}
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _tiene_columna(bind, _TABLE, _COLUMNA):
        op.add_column(_TABLE, sa.Column(_COLUMNA, sa.String(32), nullable=True))
    if not _tiene_indice(bind, _TABLE, _INDICE):
        op.create_index(_INDICE, _TABLE, [_COLUMNA])


def downgrade() -> None:
    bind = op.get_bind()
    if _tiene_indice(bind, _TABLE, _INDICE):
        op.drop_index(_INDICE, table_name=_TABLE)
    if _tiene_columna(bind, _TABLE, _COLUMNA):
        op.drop_column(_TABLE, _COLUMNA)
