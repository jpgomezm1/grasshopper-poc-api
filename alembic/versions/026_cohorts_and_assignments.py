"""Cohorts + student/psy assignments

Revision ID: 026_cohorts_and_assignments
Revises: 025_add_parent_role
Create Date: 2026-05-04

GH-SCHOOL-ADMIN · Bloque B · Sprint school_admin 2026-05-04.

Adds three tables that allow a school_admin to organize students and
psychologists into cohorts (e.g. "11A-2026", "12B-2026") for workload
distribution and isolated KPIs.

    cohorts
        id               UUID PK
        school_id        UUID FK schools(id) ON DELETE CASCADE  · idx
        key              VARCHAR(40)  · unique per school
        label            VARCHAR(120)
        grade            VARCHAR(20)
        academic_year    INT
        color            VARCHAR(20)        · hex tag color
        is_active        BOOLEAN NOT NULL DEFAULT TRUE
        created_at       TIMESTAMP
        archived_at      TIMESTAMP NULL
        UNIQUE (school_id, key)

    student_cohort_assignments
        id               UUID PK
        student_user_id  UUID FK users(id) ON DELETE CASCADE   · idx
        cohort_id        UUID FK cohorts(id) ON DELETE CASCADE · idx
        assigned_at      TIMESTAMP
        assigned_by      UUID FK users(id) ON DELETE SET NULL
        UNIQUE (student_user_id, cohort_id)

    cohort_psychologist_assignments
        id                   UUID PK
        psychologist_user_id UUID FK users(id) ON DELETE CASCADE · idx
        cohort_id            UUID FK cohorts(id) ON DELETE CASCADE · idx
        assigned_at          TIMESTAMP
        assigned_by          UUID FK users(id) ON DELETE SET NULL
        UNIQUE (psychologist_user_id, cohort_id)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = '026_cohorts_and_assignments'
down_revision = '025_add_parent_role'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return name in inspector.get_table_names()


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists('cohorts'):
        op.create_table(
            'cohorts',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('key', sa.String(40), nullable=False),
            sa.Column('label', sa.String(120), nullable=False),
            sa.Column('grade', sa.String(20), nullable=True),
            sa.Column('academic_year', sa.Integer(), nullable=True),
            sa.Column('color', sa.String(20), nullable=True),
            sa.Column(
                'is_active',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('TRUE'),
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('archived_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('school_id', 'key', name='uq_cohort_school_key'),
        )

    if not _index_exists('cohorts', 'ix_cohorts_school_id'):
        op.create_index('ix_cohorts_school_id', 'cohorts', ['school_id'])

    # student_cohort_assignments
    if not _table_exists('student_cohort_assignments'):
        op.create_table(
            'student_cohort_assignments',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'student_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'cohort_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('cohorts.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'assigned_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                'assigned_by',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.UniqueConstraint('student_user_id', 'cohort_id', name='uq_student_cohort'),
        )

    if not _index_exists('student_cohort_assignments', 'ix_student_cohort_assignments_student_user_id'):
        op.create_index(
            'ix_student_cohort_assignments_student_user_id',
            'student_cohort_assignments',
            ['student_user_id'],
        )

    if not _index_exists('student_cohort_assignments', 'ix_student_cohort_assignments_cohort_id'):
        op.create_index(
            'ix_student_cohort_assignments_cohort_id',
            'student_cohort_assignments',
            ['cohort_id'],
        )

    # cohort_psychologist_assignments
    if not _table_exists('cohort_psychologist_assignments'):
        op.create_table(
            'cohort_psychologist_assignments',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'psychologist_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'cohort_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('cohorts.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'assigned_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                'assigned_by',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.UniqueConstraint('psychologist_user_id', 'cohort_id', name='uq_psy_cohort'),
        )

    if not _index_exists('cohort_psychologist_assignments', 'ix_cohort_psy_assignments_psy_user_id'):
        op.create_index(
            'ix_cohort_psy_assignments_psy_user_id',
            'cohort_psychologist_assignments',
            ['psychologist_user_id'],
        )

    if not _index_exists('cohort_psychologist_assignments', 'ix_cohort_psy_assignments_cohort_id'):
        op.create_index(
            'ix_cohort_psy_assignments_cohort_id',
            'cohort_psychologist_assignments',
            ['cohort_id'],
        )


def downgrade() -> None:
    if _table_exists('cohort_psychologist_assignments'):
        op.drop_table('cohort_psychologist_assignments')
    if _table_exists('student_cohort_assignments'):
        op.drop_table('student_cohort_assignments')
    if _table_exists('cohorts'):
        op.drop_table('cohorts')
