"""RM-1 · consentimiento para el acompañamiento periódico (2026-08-05).

Revision ID: 053_communications_consent
Revises: 052_cv_profile
Create Date: 2026-08-05

En la reunión del 21-07 se pidió que el asistente contacte cada tanto:

    "¿cómo vas con tu proyecto? ¿tomaste el curso de inglés?" · "se vuelve tu
    amigo… como decir: Claudio, mi asistente."

Antes de escribir una sola línea del scheduler hace falta poder responder si a
una persona **se le puede escribir**, y hoy no se podía: existía el consentimiento
de tratamiento de datos (Ley 1581/2012), el de sincronización con el CRM y el
parental, pero **ninguno de comunicaciones**.

Es un consentimiento aparte a propósito. Alguien puede aceptar que tratemos su
información y no querer que le mandemos mensajes; meterlo dentro del de datos
sería obtenerlo por arrastre, que es justo lo que la ley no quiere.

Importa especialmente porque **una parte de los usuarios son menores de edad**.
`consent_service.can_send_communications` exige, además de este consentimiento,
el parental cuando la persona es menor — y `is_minor` devuelve True si no hay
fecha de nacimiento, así que ante la duda no se manda nada.

    consent_communications_at    datetime · NULL = no otorgado

Aditiva y nullable: el deploy la aplica sola (`release: alembic upgrade head`) sin
tocar ninguna fila existente. Idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '053_communications_consent'
down_revision = '052_cv_profile'
branch_labels = None
depends_on = None

_TABLE = 'users'
_COLUMN = 'consent_communications_at'


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, _TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, _TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
