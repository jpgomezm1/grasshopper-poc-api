"""El presupuesto que declara el acudiente · privado, por hijo.

Revision ID: 073_presupuesto_familiar
Revises: 072_ficha_academica
Create Date: 2026-08-30

Verónica, revisión Sprint 2 (Padres de Familia, Paso 2):

    "Calculadora Financiera. Módulo PRIVADO para ingresar presupuesto
     disponible para la educación de su hijo."

## Por qué no reusa `users.budget_band` / `budget_max_usd`

Porque esas columnas son del ESTUDIANTE: las llena él en su onboarding y las
lee el recomendador para elegir qué le propone. Escribir ahí el número del
padre haría dos cosas malas a la vez:

  1. **Pisaría lo que dijo el estudiante.** Son dos declaraciones distintas y
     legítimas — el hijo puede decir "no sé" y el padre "hasta 15.000 USD".
  2. **Rompería el "privado" que ella subraya.** El recomendador del estudiante
     cambiaría sus resultados sin que él sepa por qué, y de ahí a inferir la
     cifra de su familia hay un paso.

Por eso vive en su propia tabla, colgada de la relación padre-hijo.

## Por qué se ata a `parent_relationships` y no al padre a secas

Porque un acudiente puede tener varios hijos y el presupuesto no tiene por qué
ser el mismo para cada uno. Y porque si la relación se revoca
(`is_active=False`: divorcio, cambio de custodia), el dato deja de ser
alcanzable por la misma puerta.

Aditiva, nullable e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


revision = '073_presupuesto_familiar'
down_revision = '072_ficha_academica'
branch_labels = None
depends_on = None

_TABLA = 'family_budgets'


def _has_table(bind, name: str) -> bool:
    try:
        return name in inspect(bind).get_table_names()
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, _TABLA):
        op.create_table(
            _TABLA,
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            # La RELACIÓN, no el padre · ver la cabecera.
            sa.Column(
                'parent_relationship_id',
                UUID(as_uuid=True),
                sa.ForeignKey('parent_relationships.id', ondelete='CASCADE'),
                nullable=False,
                unique=True,
            ),
            # Techo anual disponible. Entero: los centavos no cambian ninguna
            # decisión de este módulo y sí invitan a falsa precisión.
            sa.Column('anual_max', sa.Integer(), nullable=True),
            sa.Column('moneda', sa.String(3), nullable=True),
            # Si contempla o no crédito/beca · cambia por completo qué es
            # alcanzable, y preguntarlo evita recomendar sólo lo barato.
            sa.Column('con_financiacion', sa.Boolean(), nullable=True),
            sa.Column('nota', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        op.create_index(f'ix_{_TABLA}_relacion', _TABLA, ['parent_relationship_id'])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        op.drop_table(_TABLA)
