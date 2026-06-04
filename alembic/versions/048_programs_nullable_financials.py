"""F-CATALOG-REAL · financieros de programs opcionales (2026-06-03).

Revision ID: 048_programs_nullable_financials
Revises: aa03aec05374
Create Date: 2026-06-03

GH-LOCAL-CLIENT-MODULES · La hoja de programas pasa a alimentarse del catálogo
REAL de instituciones (xlsx del cliente), que NO trae precio, duración ni
presupuesto de cara al estudiante. Por eso estos tres campos dejan de ser
obligatorios:
- ``cost_total``      → NULL = "a confirmar"
- ``duration_months`` → NULL = "a confirmar"
- ``budget_tier``     → NULL = sin clasificar (la UI/IA no asume nada)

Cuando lleguen precios reales se vuelven a poblar y el ROI se reactiva.
Idempotente: sólo altera si la columna existe y aún es NOT NULL.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '048_programs_nullable_financials'
down_revision = 'aa03aec05374'
branch_labels = None
depends_on = None

_COLS = ("cost_total", "duration_months", "budget_tier")


def _col(bind, table: str, name: str):
    insp = inspect(bind)
    try:
        for c in insp.get_columns(table):
            if c["name"] == name:
                return c
    except Exception:
        return None
    return None


def upgrade() -> None:
    bind = op.get_bind()
    types = {
        "cost_total": sa.Integer(),
        "duration_months": sa.Integer(),
        "budget_tier": sa.String(length=20),
    }
    for name in _COLS:
        col = _col(bind, "programs", name)
        if col is not None and col.get("nullable") is False:
            op.alter_column("programs", name, existing_type=types[name], nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    types = {
        "cost_total": sa.Integer(),
        "duration_months": sa.Integer(),
        "budget_tier": sa.String(length=20),
    }
    # Best-effort: sólo re-aplica NOT NULL si no hay filas con NULL (evita romper).
    for name in _COLS:
        col = _col(bind, "programs", name)
        if col is None or col.get("nullable") is True:
            try:
                n = bind.execute(
                    sa.text(f"SELECT COUNT(*) FROM programs WHERE {name} IS NULL")
                ).scalar()
            except Exception:
                n = 1  # si falla la verificación, no forzar NOT NULL
            if not n:
                op.alter_column("programs", name, existing_type=types[name], nullable=False)
