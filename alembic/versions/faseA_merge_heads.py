"""Merge de heads de Fase A (alembic) · listo para usar al integrar.

Copiar este archivo a `Back/grasshopper-poc-api/alembic/versions/` DESPUÉS de
haber mergeado a main las ramas que agregan migración (F-005 y M-006 y D-002).
Unifica los heads paralelos que nacen de 048. Es un merge no-op (no altera schema).

Si NO se mergean las tres, ajustar la tupla `down_revision` a las que sí entren
(o generarlo con: `alembic merge -m "merge fase A" <heads...>`).
"""
from alembic import op  # noqa: F401  (requerido por convención alembic)
import sqlalchemy as sa  # noqa: F401


revision = "faseA_merge_heads"
down_revision = (
    "049_user_test_disclaimers",   # F-005
    "m006_parental_consent",       # M-006
    "d002_admission_fields",       # D-002
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op · solo unifica los heads paralelos."""
    pass


def downgrade() -> None:
    pass
