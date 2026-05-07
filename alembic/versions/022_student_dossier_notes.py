"""Student dossier notes · gh_advisor clinical toolkit

Revision ID: 022_student_dossier_notes
Revises: 021_pipeline_stages_and_rules
Create Date: 2026-05-04

GH-ADVISOR-CLINICAL · Bloque A · Sprint advisor clinical 2026-05-04.

Changes:

    student_dossier_notes
        id              UUID PK
        student_user_id UUID FK users(id) ON DELETE CASCADE   · idx
        advisor_user_id UUID FK users(id) ON DELETE SET NULL  · idx (autor)
        section         VARCHAR(40) NOT NULL                   · enum string
                        · demographics | family | academic | hobbies
                        · constraints | aspirations | general
        content         TEXT NOT NULL                          · markdown
        created_at      TIMESTAMP NOT NULL DEFAULT NOW
        updated_at      TIMESTAMP NOT NULL DEFAULT NOW

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '022_student_dossier_notes'
down_revision = '021_pipeline_stages_and_rules'
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
    if not _table_exists('student_dossier_notes'):
        op.create_table(
            'student_dossier_notes',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'student_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'advisor_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('section', sa.String(40), nullable=False),
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

    if not _index_exists('student_dossier_notes', 'ix_student_dossier_notes_student_user_id'):
        op.create_index(
            'ix_student_dossier_notes_student_user_id',
            'student_dossier_notes',
            ['student_user_id'],
        )

    if not _index_exists('student_dossier_notes', 'ix_student_dossier_notes_advisor_user_id'):
        op.create_index(
            'ix_student_dossier_notes_advisor_user_id',
            'student_dossier_notes',
            ['advisor_user_id'],
        )

    if not _index_exists('student_dossier_notes', 'ix_student_dossier_notes_section'):
        op.create_index(
            'ix_student_dossier_notes_section',
            'student_dossier_notes',
            ['section'],
        )


def downgrade() -> None:
    if _table_exists('student_dossier_notes'):
        if _index_exists('student_dossier_notes', 'ix_student_dossier_notes_section'):
            op.drop_index('ix_student_dossier_notes_section', table_name='student_dossier_notes')
        if _index_exists('student_dossier_notes', 'ix_student_dossier_notes_advisor_user_id'):
            op.drop_index('ix_student_dossier_notes_advisor_user_id', table_name='student_dossier_notes')
        if _index_exists('student_dossier_notes', 'ix_student_dossier_notes_student_user_id'):
            op.drop_index('ix_student_dossier_notes_student_user_id', table_name='student_dossier_notes')
        op.drop_table('student_dossier_notes')
