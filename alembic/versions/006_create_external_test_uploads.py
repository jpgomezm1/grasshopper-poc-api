"""Create external_test_uploads + extend vocational_test_results

Revision ID: 006_create_external_test_uploads
Revises: 005_add_school_id_to_users
Create Date: 2026-04-30

GH-S5-DB-01 + GH-S5-DB-02 · Sprint 5 (parsing IA tests externos).

What this migration does:
  1. Creates `external_test_uploads` to persist user-uploaded PDFs/images of
     vocational tests done outside the platform (with a psychologist) so the
     IA pipeline can parse them.
  2. Extends `vocational_test_results` with `source` (internal | external_upload)
     and `external_upload_id` (FK nullable) so consolidated profiles can trace
     where each result came from.

Idempotent: safe to re-run · uses table_exists / column_exists guards. Aligns
with project convention from migrations 003-005.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '006_create_external_test_uploads'
down_revision = '005_add_school_id_to_users'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # 1) external_test_uploads
    if not table_exists('external_test_uploads'):
        op.create_table(
            'external_test_uploads',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
                index=True,
            ),
            # Test type (mbti · istrong · big5 · riasec) — text not enum so we
            # can grow without migrations if a new test arrives mid-sprint.
            sa.Column('test_type', sa.String(50), nullable=False, index=True),
            # Storage path returned by storage_service (e.g. "{user_id}/test_uploads/abc.pdf")
            sa.Column('file_path', sa.String(500), nullable=False),
            sa.Column('original_filename', sa.String(500), nullable=True),
            sa.Column('content_type', sa.String(100), nullable=True),
            sa.Column('size_bytes', sa.Integer, nullable=True),
            # Parsing pipeline status:
            #   pending       · just uploaded, not parsed yet
            #   processing    · parser is running
            #   done          · parser succeeded with confidence above threshold
            #   needs_review  · parser ran but confidence below threshold (manual review)
            #   failed        · parser raised or returned no usable output
            sa.Column(
                'parsing_status',
                sa.String(30),
                nullable=False,
                server_default=sa.text("'pending'"),
                index=True,
            ),
            # Raw text extracted from the PDF (pdfplumber output) · null if vision-only path
            sa.Column('raw_text', sa.Text, nullable=True),
            # Structured JSON validated by Pydantic schemas in
            # app/schemas/external_tests.py · shape depends on test_type.
            sa.Column('parsed_data', postgresql.JSONB, nullable=True),
            sa.Column('confidence_score', sa.Float, nullable=True),
            sa.Column('parser_version', sa.String(20), nullable=True),
            sa.Column('error_message', sa.Text, nullable=True),
            sa.Column(
                'uploaded_at',
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('parsed_at', sa.DateTime, nullable=True),
        )
        op.create_index(
            'ix_external_test_uploads_user_test',
            'external_test_uploads',
            ['user_id', 'test_type'],
        )

    # 2) extend vocational_test_results
    if not column_exists('vocational_test_results', 'source'):
        op.add_column(
            'vocational_test_results',
            sa.Column(
                'source',
                sa.String(30),
                nullable=False,
                server_default=sa.text("'internal'"),
            ),
        )

    if not column_exists('vocational_test_results', 'external_upload_id'):
        op.add_column(
            'vocational_test_results',
            sa.Column(
                'external_upload_id',
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        # FK with SET NULL so deleting an upload doesn't drop the consolidated result
        op.create_foreign_key(
            'fk_vtr_external_upload_id',
            'vocational_test_results',
            'external_test_uploads',
            ['external_upload_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    if column_exists('vocational_test_results', 'external_upload_id'):
        op.drop_constraint('fk_vtr_external_upload_id', 'vocational_test_results', type_='foreignkey')
        op.drop_column('vocational_test_results', 'external_upload_id')

    if column_exists('vocational_test_results', 'source'):
        op.drop_column('vocational_test_results', 'source')

    if table_exists('external_test_uploads'):
        op.drop_index('ix_external_test_uploads_user_test', table_name='external_test_uploads')
        op.drop_table('external_test_uploads')
