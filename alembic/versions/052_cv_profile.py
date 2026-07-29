"""A3 · lo que el estudiante responde y edita de su hoja de vida (2026-07-29).

Revision ID: 052_cv_profile
Revises: 051_test_self_assessment
Create Date: 2026-07-29

Feedback A3, literal:

    "Hoja de vida: antes de generarla debe preguntar QUÉ HAGO ACTUALMENTE y EN QUÉ
     COLEGIO ESTUDIO (si estoy en colegio). El resto (integrar perfiles + tests +
     lo subido) está muy chévere. Además DEBE PODER EDITARSE (habrá cosas que uno
     quiera quitar o mejorar)."

Hoy `GET /me/cv` arma el PDF de una y no pregunta nada ni deja tocar nada. Esta
tabla guarda las dos respuestas y las ediciones del estudiante.

`overrides` es JSON y no columnas porque son exactamente los campos que ya arma
`build_cv_data` (titular, resumen, fortalezas, intereses, valores, caminos) más
las listas de lo que decidió quitar. Volverlos columnas obligaría a una migración
cada vez que el CV gane una sección.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = '052_cv_profile'
down_revision = '051_test_self_assessment'
branch_labels = None
depends_on = None

_TABLE = 'cv_profiles'


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
        sa.Column(
            'user_id', uuid_type,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False, unique=True, index=True,
        ),
        # --- Las dos preguntas que ella pidió ---------------------------
        sa.Column('current_occupation', sa.String(80), nullable=True),
        sa.Column('occupation_detail', sa.String(200), nullable=True),
        sa.Column('studies_at_school', sa.Boolean(), nullable=True),
        sa.Column('school_name', sa.String(200), nullable=True),
        # --- Lo que el estudiante editó o quitó -------------------------
        sa.Column('overrides', sa.JSON(), nullable=True),
        sa.Column('answered_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        op.drop_table(_TABLE)
