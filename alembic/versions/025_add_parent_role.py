"""Add PARENT role to userrole + parent_relationships table

Revision ID: 025_add_parent_role
Revises: 024_clinical_analysis_cache
Create Date: 2026-05-04

GH-SCHOOL-ADMIN · Bloque E · Sprint school_admin 2026-05-04.

Adds 'parent' to the userrole enum and creates the relationship table
that ties parent users to their student children. Multi-parent (mom/dad)
+ multi-child supported.

    userrole enum: + 'parent'

    parent_relationships
        id               UUID PK
        parent_user_id   UUID FK users(id) ON DELETE CASCADE   · idx
        student_user_id  UUID FK users(id) ON DELETE CASCADE   · idx
        relationship     VARCHAR(40) NOT NULL                  · 'mother'|'father'|'guardian'|'other'
        is_active        BOOLEAN NOT NULL DEFAULT TRUE
        created_at       TIMESTAMP NOT NULL DEFAULT NOW
        UNIQUE (parent_user_id, student_user_id)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '025_add_parent_role'
down_revision = '024_clinical_analysis_cache'
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


def _enum_has_value(enum_name: str, value: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = :enum_name AND e.enumlabel = :value"
        ),
        {"enum_name": enum_name, "value": value},
    ).fetchone()
    return result is not None


def upgrade() -> None:
    # 1. Add 'parent' to userrole enum if missing.
    if not _enum_has_value('userrole', 'parent'):
        # ALTER TYPE ... ADD VALUE must run outside transaction for some PG versions.
        # In Alembic with `transaction_per_migration=False` we wrap it in COMMIT/BEGIN.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'parent'")

    # 2. Create parent_relationships table.
    if not _table_exists('parent_relationships'):
        op.create_table(
            'parent_relationships',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'parent_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'student_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('relationship', sa.String(40), nullable=False),
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
            sa.UniqueConstraint('parent_user_id', 'student_user_id', name='uq_parent_student'),
        )

    if not _index_exists('parent_relationships', 'ix_parent_relationships_parent_user_id'):
        op.create_index(
            'ix_parent_relationships_parent_user_id',
            'parent_relationships',
            ['parent_user_id'],
        )

    if not _index_exists('parent_relationships', 'ix_parent_relationships_student_user_id'):
        op.create_index(
            'ix_parent_relationships_student_user_id',
            'parent_relationships',
            ['student_user_id'],
        )


def downgrade() -> None:
    # Note: cannot remove enum value in PostgreSQL · only drop table.
    if _table_exists('parent_relationships'):
        if _index_exists('parent_relationships', 'ix_parent_relationships_student_user_id'):
            op.drop_index(
                'ix_parent_relationships_student_user_id',
                table_name='parent_relationships',
            )
        if _index_exists('parent_relationships', 'ix_parent_relationships_parent_user_id'):
            op.drop_index(
                'ix_parent_relationships_parent_user_id',
                table_name='parent_relationships',
            )
        op.drop_table('parent_relationships')
