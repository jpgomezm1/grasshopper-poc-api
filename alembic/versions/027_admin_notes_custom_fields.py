"""Student admin notes + custom fields per school

Revision ID: 027_admin_notes_custom_fields
Revises: 026_cohorts_and_assignments
Create Date: 2026-05-04

GH-SCHOOL-ADMIN · Bloque C+H · Sprint school_admin 2026-05-04.

Admin notes are NON-clinical · separate from psychologist's clinical
dossier. Custom fields let each school define their own attributes.

    student_admin_notes
        id              UUID PK
        student_user_id UUID FK users(id) ON DELETE CASCADE  · idx
        school_id       UUID FK schools(id) ON DELETE CASCADE · idx
        author_user_id  UUID FK users(id) ON DELETE SET NULL · idx
        content         TEXT NOT NULL    · markdown
        created_at      TIMESTAMP
        updated_at      TIMESTAMP

    school_custom_fields
        id              UUID PK
        school_id       UUID FK schools(id) ON DELETE CASCADE · idx
        key             VARCHAR(60)     · machine readable
        label           VARCHAR(120)    · human readable
        type            VARCHAR(20)     · 'text'|'number'|'boolean'|'enum'
        options         JSONB           · for enum (list of strings)
        is_active       BOOLEAN DEFAULT TRUE
        created_at      TIMESTAMP
        UNIQUE (school_id, key)

    student_custom_field_values
        id              UUID PK
        student_user_id UUID FK users(id) ON DELETE CASCADE
        field_id        UUID FK school_custom_fields(id) ON DELETE CASCADE
        value           JSONB
        updated_at      TIMESTAMP
        UNIQUE (student_user_id, field_id)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = '027_admin_notes_custom_fields'
down_revision = '026_cohorts_and_assignments'
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
    # student_admin_notes
    if not _table_exists('student_admin_notes'):
        op.create_table(
            'student_admin_notes',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'student_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'author_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _index_exists('student_admin_notes', 'ix_student_admin_notes_student_user_id'):
        op.create_index(
            'ix_student_admin_notes_student_user_id',
            'student_admin_notes',
            ['student_user_id'],
        )

    if not _index_exists('student_admin_notes', 'ix_student_admin_notes_school_id'):
        op.create_index(
            'ix_student_admin_notes_school_id',
            'student_admin_notes',
            ['school_id'],
        )

    # school_custom_fields
    if not _table_exists('school_custom_fields'):
        op.create_table(
            'school_custom_fields',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('key', sa.String(60), nullable=False),
            sa.Column('label', sa.String(120), nullable=False),
            sa.Column('type', sa.String(20), nullable=False),
            sa.Column('options', postgresql.JSONB(), nullable=True),
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
            sa.UniqueConstraint('school_id', 'key', name='uq_school_custom_field_key'),
        )

    if not _index_exists('school_custom_fields', 'ix_school_custom_fields_school_id'):
        op.create_index(
            'ix_school_custom_fields_school_id',
            'school_custom_fields',
            ['school_id'],
        )

    # student_custom_field_values
    if not _table_exists('student_custom_field_values'):
        op.create_table(
            'student_custom_field_values',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'student_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'field_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('school_custom_fields.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('value', postgresql.JSONB(), nullable=True),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint('student_user_id', 'field_id', name='uq_student_field_value'),
        )

    if not _index_exists('student_custom_field_values', 'ix_student_cfv_student_user_id'):
        op.create_index(
            'ix_student_cfv_student_user_id',
            'student_custom_field_values',
            ['student_user_id'],
        )


def downgrade() -> None:
    if _table_exists('student_custom_field_values'):
        op.drop_table('student_custom_field_values')
    if _table_exists('school_custom_fields'):
        op.drop_table('school_custom_fields')
    if _table_exists('student_admin_notes'):
        op.drop_table('student_admin_notes')
