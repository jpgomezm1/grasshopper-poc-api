"""F-003 etapa 1 · scholarships_for_latam flag en programs (2026-05-28).

Revision ID: 047_programs_scholarships_latam
Revises: 046_human_intervention_notes
Create Date: 2026-05-28

GH-LOCAL-CLIENT-MODULES · cliente docx §1 + §3.G: "Filtro de Financial Fit
avanzado · debe considerar la disponibilidad de becas de cada universidad"
y "El catálogo debe tener un campo booleano (Sí/No) para `Becas para
Latinoamericanos`, de modo que la IA pueda priorizar estas opciones en el
matching."

Mantenemos el campo `scholarships` JSON existente (lista detallada) y agregamos
``scholarships_for_latam`` BOOLEAN nullable como flag de matching rápido.
- TRUE  → la institución tiene beca explícita aplicable a estudiantes LatAm
- FALSE → no la tiene
- NULL  → no se ha curado el dato todavía (no asumir nada)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '047_programs_scholarships_latam'
# Depende sólo de 044 (last revision en main al 2026-05-28) para poder
# mergear independientemente del catalog (045) o F-006 (046). Cuando se
# mergeen los tres PRs, el merge resolverá automáticamente.
down_revision = '044_programs_visa_roi'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        cols = insp.get_columns(table)
    except Exception:
        return False
    return any(c["name"] == name for c in cols)


def _has_index(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(ix["name"] == name for ix in insp.get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "programs", "scholarships_for_latam"):
        op.add_column(
            "programs",
            sa.Column("scholarships_for_latam", sa.Boolean(), nullable=True),
        )
    if not _has_index(bind, "programs", "ix_programs_scholarships_for_latam"):
        op.create_index(
            "ix_programs_scholarships_for_latam",
            "programs",
            ["scholarships_for_latam"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, "programs", "ix_programs_scholarships_for_latam"):
        try:
            op.drop_index("ix_programs_scholarships_for_latam", "programs")
        except Exception:
            pass
    if _has_column(bind, "programs", "scholarships_for_latam"):
        op.drop_column("programs", "scholarships_for_latam")
