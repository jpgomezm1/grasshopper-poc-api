"""D-002 · variables de admisión en programs (Reach/Match/Safety) · 2026-06-04.

Revision ID: d002_admission_fields
Revises: 048_programs_nullable_financials
Create Date: 2026-06-04

Agrega a `programs` las variables de admisión para clasificar Reach/Match/Safety
(cliente docx §3.G): acceptance_rate, avg_admitted_gpa, min_sat, avg_sat,
min_english_level. Todas nullable (NULL = no curado → sin badge). Idempotente.

NOTA DE RAMA: nace de 048 igual que `049_user_test_disclaimers` (F-005) y
`m006_parental_consent` (M-006). Son ramas paralelas → al integrar varias a main
quedan múltiples heads y hay que crear migración(es) de merge (`alembic merge`).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'd002_admission_fields'
down_revision = '048_programs_nullable_financials'
branch_labels = None
depends_on = None

_COLS = {
    "acceptance_rate": sa.Float(),
    "avg_admitted_gpa": sa.Float(),
    "min_sat": sa.Integer(),
    "avg_sat": sa.Integer(),
    "min_english_level": sa.String(length=10),
}


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    for name, type_ in _COLS.items():
        if not _has_column(bind, "programs", name):
            op.add_column("programs", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for name in _COLS:
        if _has_column(bind, "programs", name):
            op.drop_column("programs", name)
