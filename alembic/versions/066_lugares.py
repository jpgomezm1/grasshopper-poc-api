"""Dónde queda cada ciudad · caché de geocodificación (2026-08-10).

Revision ID: 066_lugares
Revises: 065_foto_en_la_base
Create Date: 2026-08-10

Los dos catálogos guardan país y ciudad como texto libre y en idiomas distintos
(`programs` tiene hasta `Ireland` e `Irlanda` a la vez). `services/lugares.py`
los normaliza a una clave común —`gb:london`— y esta tabla le pone coordenadas.

**Es una caché, no data de negocio**: se puede vaciar y regenerar con
`scripts/geocodificar_lugares.py`. Por eso no tiene relación con `programs` ni
con `programas_investigados`: el cruce se hace por la clave calculada, no por
una FK, y así una ficha nueva de la agencia no necesita que nadie la registre
aquí antes de poder aparecer.

Aditiva y sin tocar nada existente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '066_lugares'
down_revision = '065_foto_en_la_base'
branch_labels = None
depends_on = None

_TABLE = 'lugares'


def _has_table(bind, name: str) -> bool:
    try:
        return inspect(bind).has_table(name)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        return

    op.create_table(
        _TABLE,
        # `<iso>:<ciudad normalizada>` · la produce `lugares.clave_lugar()`.
        sa.Column('clave', sa.String(160), primary_key=True),
        sa.Column('ciudad', sa.String(160), nullable=True),
        sa.Column('pais_iso', sa.String(8), nullable=False, index=True),
        # Nullable a propósito: un lugar que no se pudo resolver se queda sin
        # coordenadas en vez de con unas inventadas.
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        # ciudad | region | sin_resolver
        sa.Column('precision', sa.String(20), nullable=True),
        sa.Column('fuente', sa.String(40), nullable=True),
        sa.Column('verificado_en', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        op.drop_table(_TABLE)
