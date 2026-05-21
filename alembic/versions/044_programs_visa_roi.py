"""Add visa + ROI fields to programs · F-002 etapa 1.

Revision ID: 044_programs_visa_roi
Revises: 043_extracurricular_activities
Create Date: 2026-05-21

GH-LOCAL-CLIENT-MODULES · cliente pidió en docx §1 párrafo 2 una calculadora
ROI + lógica de visado laboral (OPT/CPT/PGWP/etc.) integrada al catálogo.

ALTER TABLE programs ADD:
    visa_type                       VARCHAR(40)  NULL · ej. OPT | PGWP | PSW | TVR
    visa_max_years_work             INTEGER      NULL · años post-grad de trabajo
    visa_requires_degree_alignment  BOOLEAN      NULL · trabajo debe alinear con la carrera
    visa_notes                      TEXT         NULL
    entry_salary_local_usd          INTEGER      NULL · salario inicial USD/año
    living_cost_city_usd_year       INTEGER      NULL · costo vida USD/año en la ciudad

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '044_programs_visa_roi'
down_revision = '043_extracurricular_activities'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        cols = insp.get_columns(table)
    except Exception:
        return False
    return any(c["name"] == name for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "programs", "visa_type"):
        op.add_column("programs", sa.Column("visa_type", sa.String(40), nullable=True))
    if not _has_column(bind, "programs", "visa_max_years_work"):
        op.add_column("programs", sa.Column("visa_max_years_work", sa.Integer(), nullable=True))
    if not _has_column(bind, "programs", "visa_requires_degree_alignment"):
        op.add_column(
            "programs", sa.Column("visa_requires_degree_alignment", sa.Boolean(), nullable=True)
        )
    if not _has_column(bind, "programs", "visa_notes"):
        op.add_column("programs", sa.Column("visa_notes", sa.Text(), nullable=True))
    if not _has_column(bind, "programs", "entry_salary_local_usd"):
        op.add_column("programs", sa.Column("entry_salary_local_usd", sa.Integer(), nullable=True))
    if not _has_column(bind, "programs", "living_cost_city_usd_year"):
        op.add_column(
            "programs", sa.Column("living_cost_city_usd_year", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    for col in (
        "visa_type",
        "visa_max_years_work",
        "visa_requires_degree_alignment",
        "visa_notes",
        "entry_salary_local_usd",
        "living_cost_city_usd_year",
    ):
        if _has_column(bind, "programs", col):
            op.drop_column("programs", col)
