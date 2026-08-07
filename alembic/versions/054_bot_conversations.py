"""BOT · conversaciones del perfilador comercial (2026-08-06).

Revision ID: 054_bot_conversations
Revises: 053_communications_consent
Create Date: 2026-08-06

El bot que reemplaza el Typeform de la web de la agencia. Feedback de Verónica,
primera línea del documento de Sprint 3:

    "EL BOT YA ESTA? DONDE LO PUEDO VER?"

Y en la reunión del 21-07 (12:03), lo que el bot tiene que decidir:

    "el bot debe hacer un scoring que le haga una valoración a la persona, le
     diga tú tienes un buen perfil, te tiro ya a una asesoría con asesor, o no
     tienes tan buen perfil, te tiran al equipo de telemercadeo"

**Tabla nueva, no columnas sobre `lead_profiles`.** Son cosas distintas: el quiz
público es de orientación (6 preguntas vocacionales) y este es comercial (los
~20 hechos del Typeform). Mezclarlas obligaría a que la mitad de las columnas
estuvieran siempre vacías según el origen.

`hechos` y `transcript` son JSON y no columnas porque el catálogo de hechos vive
en `app/data/perfilador_typeform.py` y va a cambiar cuando la clienta mande las
opciones de respuesta que faltan — volverlos columnas obligaría a una migración
por cada ajuste de un formulario que todavía se está validando con ella.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = '054_bot_conversations'
down_revision = '053_communications_consent'
branch_labels = None
depends_on = None

_TABLE = 'bot_conversations'


def _has_table(bind, name: str) -> bool:
    try:
        return inspect(bind).has_table(name)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        return

    es_postgres = bind.dialect.name == 'postgresql'
    uuid_type = postgresql.UUID(as_uuid=True) if es_postgres else sa.String(36)

    op.create_table(
        _TABLE,
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        # --- Contacto · se llena a medida que lo va diciendo ----------------
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        # --- Estado de la conversación -------------------------------------
        sa.Column('hechos', sa.JSON(), nullable=False),
        sa.Column('transcript', sa.JSON(), nullable=False),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
        # --- Veredicto comercial -------------------------------------------
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('band', sa.String(20), nullable=True),
        sa.Column('route', sa.String(20), nullable=True),
        sa.Column('alarms', sa.JSON(), nullable=True),
        sa.Column('score_rationale', sa.JSON(), nullable=True),
        # --- Miga de pan hacia GrassHopper ----------------------------------
        sa.Column(
            'wants_orientation', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        # --- Conversión a cuenta --------------------------------------------
        sa.Column(
            'converted_user_id', uuid_type,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
        ),
        # --- Campaña ---------------------------------------------------------
        sa.Column('utm_source', sa.String(120), nullable=True),
        sa.Column('utm_medium', sa.String(120), nullable=True),
        sa.Column('utm_campaign', sa.String(120), nullable=True),
        # --- CRM (Bitrix, hoy en stub) ---------------------------------------
        sa.Column('crm_synced_at', sa.DateTime(), nullable=True),
    )

    # La bandeja se ordena por fecha y se filtra por ruta · son los dos accesos
    # que va a hacer el equipo comercial todos los días.
    op.create_index(f'ix_{_TABLE}_created_at', _TABLE, ['created_at'])
    op.create_index(f'ix_{_TABLE}_route', _TABLE, ['route'])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        op.drop_index(f'ix_{_TABLE}_route', table_name=_TABLE)
        op.drop_index(f'ix_{_TABLE}_created_at', table_name=_TABLE)
        op.drop_table(_TABLE)
