"""Estado de los prospectos (nuevo · contactado · convertido · descartado).

Revision ID: 082_estado_de_prospectos
Revises: 081_planes_de_usuario

G-1 · Sprint 4 (2026-10-31). El panel de prospectos une tres fuentes (el bot
gratuito y el perfilador en `bot_conversations`, el quiz viejo en
`lead_profiles`) y el equipo comercial necesita marcar en qué va cada uno. Antes
no había dónde: un prospecto llamado y uno sin tocar se veían igual.

Aditiva y nullable, como pide el repo: NULL = "nuevo", o "convertido" si la
persona ya creó cuenta (se deriva al leer, ver `prospectos_service`). No se
escribe nada en las filas que ya existen.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "082_estado_de_prospectos"
down_revision = "081_planes_de_usuario"
branch_labels = None
depends_on = None

_TABLAS = ("bot_conversations", "lead_profiles")
_COLUMNAS = (
    ("estado", sa.String(20)),
    ("estado_actualizado_en", sa.DateTime()),
)


def _columnas(bind, tabla: str) -> set:
    try:
        return {c["name"] for c in inspect(bind).get_columns(tabla)}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    for tabla in _TABLAS:
        existentes = _columnas(bind, tabla)
        for nombre, tipo in _COLUMNAS:
            if nombre not in existentes:
                op.add_column(tabla, sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for tabla in _TABLAS:
        existentes = _columnas(bind, tabla)
        for nombre, _ in reversed(_COLUMNAS):
            if nombre in existentes:
                op.drop_column(tabla, nombre)
