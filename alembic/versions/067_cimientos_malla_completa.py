"""Cimientos del modelo de datos para la malla completa (2026-08-24).

Revision ID: 067_cimientos_malla_completa
Revises: 066_lugares
Create Date: 2026-08-24

Fase 1 de 4 (Cimientos) de la malla completa: 5 rutas -> grado 9, grado 10,
grado 11, grado 12, adulto profesional. "MEMORIA SÍ, LLAVE NO": el sistema
recuerda y compara año a año, pero NO bloquea contenido ni maneja calendario
escolar — esta migración no crea ningún mecanismo de bloqueo.

Tres cosas, ver `app/db/models.py` para el detalle y el porqué de cada una:

1. `users.grade` · el grado real (9-12) como columna tipada, no sólo dentro de
   `onboarding_answers`. `life_stage` no tiene la resolución que necesita la
   malla de 5 rutas (`high_school_early` junta 9° y 10°, `high_school` sólo
   llega a 11°). Precedente: mismo patrón dual que ya tiene `birthdate`
   (columna + espejo en `onboarding_answers`).
2. `users.school_reported_last_grade` / `users.school_reported_accreditation`
   · lo que el ESTUDIANTE cree de su colegio (hasta qué grado llega, y su
   acreditación IB/AP/americano/bilingüe/local/no-sé), NO un dato verificado
   del colegio — de ahí el prefijo `school_reported_`.
3. `student_year_snapshots` · tabla nueva, mínima, para la memoria entre años
   escolares. Una fila = una foto de `onboarding_answers` + `grade` de un
   estudiante en un año dado. No se guarda una fila para "hoy" (eso ya vive en
   `users`); sólo conserva lo que deja de estar vigente cuando el estudiante
   pasa de año. Quién la escribe y cuándo es decisión de una fase posterior.

Todo aditivo, nullable e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


revision = '067_cimientos_malla_completa'
down_revision = '066_lugares'
branch_labels = None
depends_on = None

_USERS = 'users'
_SNAPSHOTS = 'student_year_snapshots'


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def _has_table(bind, name: str) -> bool:
    try:
        return inspect(bind).has_table(name)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()

    # ---- 1. El grado real del estudiante ----
    if not _has_column(bind, _USERS, 'grade'):
        op.add_column(_USERS, sa.Column('grade', sa.Integer(), nullable=True))

    # ---- 2. Lo que el estudiante cree de su colegio (no verificado) ----
    if not _has_column(bind, _USERS, 'school_reported_last_grade'):
        op.add_column(
            _USERS,
            sa.Column('school_reported_last_grade', sa.Integer(), nullable=True),
        )
    if not _has_column(bind, _USERS, 'school_reported_accreditation'):
        op.add_column(
            _USERS,
            sa.Column('school_reported_accreditation', sa.String(20), nullable=True),
        )

    # ---- 3. Memoria por año escolar ----
    if not _has_table(bind, _SNAPSHOTS):
        op.create_table(
            _SNAPSHOTS,
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id', UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('school_year', sa.Integer(), nullable=False),
            sa.Column('grade', sa.Integer(), nullable=True),
            sa.Column('onboarding_answers_snapshot', sa.JSON(), nullable=True),
            sa.Column('captured_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                'user_id', 'school_year', name='uq_student_year_snapshot',
            ),
        )
        op.create_index(
            'ix_student_year_snapshots_user_id', _SNAPSHOTS, ['user_id'],
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, _SNAPSHOTS):
        op.drop_table(_SNAPSHOTS)

    for col in (
        'school_reported_accreditation',
        'school_reported_last_grade',
        'grade',
    ):
        if _has_column(bind, _USERS, col):
            op.drop_column(_USERS, col)
