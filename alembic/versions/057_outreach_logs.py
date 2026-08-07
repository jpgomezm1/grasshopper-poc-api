"""RM-1 · Registro del acompañamiento periódico (2026-08-07).

Revision ID: 057_outreach_logs
Revises: 056_program_priority
Create Date: 2026-08-07

Verónica, 21-07: *"periódicamente él debe escribirte: hola, ¿cómo vas con tu
proyecto? ¿tomaste el curso de inglés?"*.

`outreach_logs` guarda una fila por mensaje. Es lo que impide que cada corrida
del scheduler le vuelva a escribir a todo el mundo, y lo que permite responder
"¿qué se le mandó a esta persona y con qué permiso?" — que con menores de edad
no es una pregunta opcional.

Se registra también lo que NO se envió (`resultado` = sin_consentimiento ·
fallo_envio · simulacro). Un log que sólo guarda los éxitos no sirve para
auditar.

Tabla nueva, así que no hay backfill ni riesgo sobre datos existentes. Creación
idempotente como el resto de la serie 05*.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = '057_outreach_logs'
down_revision = '056_program_priority'
branch_labels = None
depends_on = None

_TABLE = 'outreach_logs'


def _tiene_tabla(bind, tabla: str) -> bool:
    try:
        return tabla in inspect(bind).get_table_names()
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if _tiene_tabla(bind, _TABLE):
        return

    # UUID nativo en Postgres · VARCHAR(36) en SQLite (los tests).
    uuid_type = (
        postgresql.UUID(as_uuid=True)
        if bind.dialect.name == 'postgresql'
        else sa.String(36)
    )

    op.create_table(
        _TABLE,
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
        sa.Column(
            'user_id', uuid_type,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False, index=True,
        ),
        sa.Column('motivo', sa.String(50), nullable=False, index=True),
        sa.Column('canal', sa.String(20), nullable=False),
        sa.Column('resultado', sa.String(30), nullable=False, index=True),
        sa.Column('asunto', sa.String(255), nullable=True),
        sa.Column('cuerpo', sa.Text(), nullable=True),
        sa.Column('es_plantilla', sa.Boolean(), nullable=True),
        sa.Column('detalle', sa.String(255), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _tiene_tabla(bind, _TABLE):
        op.drop_table(_TABLE)
