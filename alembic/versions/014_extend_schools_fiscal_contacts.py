"""Extend schools with fiscal + contacts + center metadata

Revision ID: 014_extend_schools_fiscal_contacts
Revises: 013_add_gh_team_roles
Create Date: 2026-05-03

Bloque A · Sprint super_admin fixes 2026-05-03 · issue 2 from BITACORA_TESTING.md
(form de creación de colegio le falta info clave). The bare schools table only
captured `name`/`slug`/`logo_url`/`license_*`. Operating the B2B portfolio also
requires:

  Identidad fiscal:
    rut                  · Colombian RUT/NIT (string · keeps formatting)
    razon_social         · legal name (may differ from `name`)
    direccion_fiscal     · billing address (text)
    tipo_persona         · juridica | natural

  Contacto comercial (decisor / firma propuestas):
    commercial_contact_name
    commercial_contact_role
    commercial_contact_email
    commercial_contact_phone

  Contacto académico (operativo · school_admin / coordinador):
    academic_contact_name
    academic_contact_email
    academic_contact_phone

  Centro educativo:
    estimated_students   · int · sanity check vs license seats
    city
    country
    timezone             · IANA tz string (e.g. America/Bogota)
    academic_year        · 'A' | 'B' (Colombian calendars) or other

All columns are NULLable on purpose · existing rows must keep working. The
super_admin wizard (FE) collects them in steps 1 + 3 and the SchoolDetailPage
exposes them on tabs Overview/Config.

Idempotent · re-runs are safe.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '014_extend_schools_fiscal_contacts'
down_revision = '013_add_gh_team_roles'
branch_labels = None
depends_on = None


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


# ----------------------------------------------------------------------------
# upgrade
# ----------------------------------------------------------------------------

NEW_COLUMNS = [
    # identidad fiscal
    ("rut", sa.String(40), True),
    ("razon_social", sa.String(255), True),
    ("direccion_fiscal", sa.Text(), True),
    ("tipo_persona", sa.String(20), True),  # 'juridica' | 'natural'
    # contacto comercial
    ("commercial_contact_name", sa.String(255), True),
    ("commercial_contact_role", sa.String(120), True),
    ("commercial_contact_email", sa.String(255), True),
    ("commercial_contact_phone", sa.String(50), True),
    # contacto académico
    ("academic_contact_name", sa.String(255), True),
    ("academic_contact_email", sa.String(255), True),
    ("academic_contact_phone", sa.String(50), True),
    # centro
    ("estimated_students", sa.Integer(), True),
    ("city", sa.String(120), True),
    ("country", sa.String(120), True),
    ("timezone", sa.String(80), True),
    ("academic_year", sa.String(20), True),
]


def upgrade() -> None:
    for col_name, col_type, nullable in NEW_COLUMNS:
        if not _column_exists('schools', col_name):
            op.add_column(
                'schools',
                sa.Column(col_name, col_type, nullable=nullable),
            )


# ----------------------------------------------------------------------------
# downgrade
# ----------------------------------------------------------------------------


def downgrade() -> None:
    for col_name, _t, _n in reversed(NEW_COLUMNS):
        if _column_exists('schools', col_name):
            op.drop_column('schools', col_name)
