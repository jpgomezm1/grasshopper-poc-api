"""La ficha académica del estudiante · GPA, SAT, AP e IB.

Revision ID: 072_ficha_academica
Revises: 071_counselor_sync
Create Date: 2026-08-30

Verónica, revisión Sprint 2 (Paso 3 · College List):

    "Para construir esto es importante preguntarle al estudiante su GPA
     (promedio acumulado) y su sistema de colegio: acreditación local, IB,
     colegio americano (¿tienes AP? ¿cuántas? ¿qué puntajes? ¿tienes SAT?),
     colegio alemán o colegio francés."

## Lo que ya existía y NO se duplica

`school_accreditation` (IB / AP / americano / bilingüe / local) ya se captura
estructurado en el onboarding, y vive en `users.onboarding_answers`. Copiarlo
aquí sería la segunda fuente de verdad que este repo ya pagó cuatro veces.

Lo que faltaba de verdad es lo NUMÉRICO:
- el **GPA**, que no se preguntaba en ningún lado;
- los **puntajes**, que sí se preguntan en 11° y 12° (`g11_psat_sat`,
  `g12_puntajes`) pero **como texto libre** — el estudiante escribe "saqué como
  1200 creo", y con eso no se clasifica nada.

## Por qué `gpa_scale` es obligatoria si hay `gpa`

Porque un 4.2 colombiano sobre 5.0 y un 3.8 gringo sobre 4.0 son el mismo
número en dos idiomas distintos: traducido, el 4.2 es 3.36 y está POR DEBAJO.

El catálogo de programas ya tiene ese defecto latente — `avg_admitted_gpa` es
un `Float` pelado, sin escala en ninguna parte — y hoy es inofensivo sólo
porque el GPA del estudiante siempre llega `None`. Guardar aquí el número sin
su escala sería reproducir el mismo error en el otro lado y activarlo.

## Por qué AP va en JSON y no en columnas

Porque son N materias con su puntaje ("Calculus AB: 5, Biology: 4"), y no hay
un número fijo. Volverlo columnas obligaría a migrar cada vez que alguien haga
un examen más.

Aditiva, nullable e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


revision = '072_ficha_academica'
down_revision = '071_counselor_sync'
branch_labels = None
depends_on = None

_TABLA = 'student_academic_profiles'


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
            sa.Column(
                'user_id',
                UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
                unique=True,
            ),

            # --- El promedio, con su escala. Ver la cabecera: uno sin la otra
            #     no significa nada.
            sa.Column('gpa', sa.Float(), nullable=True),
            sa.Column('gpa_scale', sa.Float(), nullable=True),

            # --- SAT · 400-1600 en todo el mundo, sin ambigüedad de escala.
            #     Es la única métrica académica comparable tal cual.
            sa.Column('sat_score', sa.Integer(), nullable=True),
            sa.Column('sat_taken_on', sa.Date(), nullable=True),

            # --- AP · [{"materia": "Calculus AB", "puntaje": 5}, ...]
            sa.Column('ap_scores', sa.JSON(), nullable=True),

            # --- IB · el total previsto del Diploma (0-45). Es lo que la
            #     universidad mira mientras el estudiante todavía cursa.
            sa.Column('ib_predicted_total', sa.Integer(), nullable=True),

            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        op.create_index(f'ix_{_TABLA}_user_id', _TABLA, ['user_id'])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        op.drop_table(_TABLA)
