"""Extend programs catalog with editorial fields + expanded type enum

Revision ID: 015_extend_programs_editorial
Revises: 014_extend_schools_fiscal_contacts
Create Date: 2026-05-03

Bloque B · Sprint super_admin fixes 2026-05-03 · issue 3 from
BITACORA_TESTING.md (catálogo de programas pobre · prerrequisito para IA).

Adds 14 editorial JSONB / text columns + expands accepted program types.
Designed for the SchoolDetailPage-style editorial detail screen ·
Idealist/Hotcourses-style hero + tabs.

Schema changes:
    description_long          TEXT       · 200-500 word pitch
    images                    JSONB      · list[{url,alt,caption,order}]
    institution_logo_url      VARCHAR(500)
    highlights                JSONB      · list[str]   3-5 differentiators
    syllabus                  JSONB      · list[{semester, courses[]}]
    academic_requirements     JSONB      · {gpa, courses, exam, interview}
    language_requirement_detail TEXT     · TOEFL/IELTS/DELE thresholds (free-form)
    admission_dates           JSONB      · list[{cohort, application_deadline, start_date}]
    scholarships              JSONB      · list[{name, type, coverage_pct, requirements}]
    employability             JSONB      · {placement_rate, avg_salary, top_employers[]}
    ranking                   JSONB      · {global, regional, by_area[]}
    testimonials              JSONB      · list[{quote, name, year, link}]
    location                  JSONB      · {address, lat, lon, neighborhood, monthly_cost}
    accreditations            JSONB      · list[str] (CNEAI, ABET, AACSB, ...)
    tags                      JSONB      · list[str] (search-vector ready)

Type enum: programs.type stays as VARCHAR (no DB enum) but we add a
non-blocking CHECK constraint that allows the expanded set:
  pregrado · posgrado · maestria · doctorado · diplomado ·
  especializacion · curso_corto · vacacional · intercambio ·
  bootcamp · mba · bachelor (legacy)

Existing data: any non-null `type` not in the list is migrated to
`pregrado` (covers the seeded `bachelor`).
Idempotent · safe re-run.

NOTE on pgvector: this migration deliberately does NOT install the
extension nor create an embedding column. The bitácora flagged it as
follow-up. The new `tags` + `description_long` give us the substrate to
build embeddings later without another schema migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '015_extend_programs_editorial'
down_revision = '014_extend_schools_fiscal_contacts'
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


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table, "c": constraint},
    ).fetchall()
    return bool(rows)


# ----------------------------------------------------------------------------
# upgrade
# ----------------------------------------------------------------------------


JSONB_COLS = [
    "images",
    "highlights",
    "syllabus",
    "academic_requirements",
    "admission_dates",
    "scholarships",
    "employability",
    "ranking",
    "testimonials",
    "location",
    "accreditations",
    "tags",
]

TEXT_COLS = [
    ("description_long", sa.Text()),
    ("language_requirement_detail", sa.Text()),
]

VARCHAR_COLS = [
    ("institution_logo_url", sa.String(500)),
]


ALLOWED_TYPES = (
    "pregrado",
    "posgrado",
    "maestria",
    "doctorado",
    "diplomado",
    "especializacion",
    "curso_corto",
    "vacacional",
    "intercambio",
    "bootcamp",
    "mba",
    "bachelor",  # legacy · kept to avoid breaking the seed migration path
)


def upgrade() -> None:
    # 1. JSONB columns · default empty list / dict where convenient
    for col in JSONB_COLS:
        if not _column_exists('programs', col):
            op.add_column(
                'programs',
                sa.Column(col, postgresql.JSONB(), nullable=True),
            )

    # 2. TEXT columns
    for col, ttype in TEXT_COLS:
        if not _column_exists('programs', col):
            op.add_column('programs', sa.Column(col, ttype, nullable=True))

    # 3. VARCHAR columns
    for col, vtype in VARCHAR_COLS:
        if not _column_exists('programs', col):
            op.add_column('programs', sa.Column(col, vtype, nullable=True))

    # 4. Migrate any unknown type to 'pregrado' to keep the constraint happy.
    #    The seed used 'bachelor'; we keep 'bachelor' as an allowed value to
    #    avoid breaking pre-existing rows yet steer new content to pregrado.
    op.execute(
        sa.text(
            """
            UPDATE programs
            SET type = 'pregrado'
            WHERE type IS NULL
               OR type NOT IN ({allowed})
            """.format(
                allowed=", ".join(f"'{t}'" for t in ALLOWED_TYPES)
            )
        )
    )

    # 5. CHECK constraint on type · idempotent
    if not _constraint_exists('programs', 'ck_programs_type_allowed'):
        op.create_check_constraint(
            'ck_programs_type_allowed',
            'programs',
            "type IN ({allowed})".format(
                allowed=", ".join(f"'{t}'" for t in ALLOWED_TYPES)
            ),
        )


# ----------------------------------------------------------------------------
# downgrade
# ----------------------------------------------------------------------------


def downgrade() -> None:
    if _constraint_exists('programs', 'ck_programs_type_allowed'):
        op.drop_constraint('ck_programs_type_allowed', 'programs', type_='check')

    for col, _t in reversed(VARCHAR_COLS):
        if _column_exists('programs', col):
            op.drop_column('programs', col)
    for col, _t in reversed(TEXT_COLS):
        if _column_exists('programs', col):
            op.drop_column('programs', col)
    for col in reversed(JSONB_COLS):
        if _column_exists('programs', col):
            op.drop_column('programs', col)
