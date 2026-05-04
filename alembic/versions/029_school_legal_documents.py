"""School-specific legal documents (TyC, privacy) + signatures

Revision ID: 029_school_legal_documents
Revises: 028_school_events
Create Date: 2026-05-04

GH-SCHOOL-ADMIN · Bloque H · Sprint school_admin 2026-05-04.

    school_legal_documents
        id              UUID PK
        school_id       UUID FK schools(id) ON DELETE CASCADE  · idx
        type            VARCHAR(40)     · 'privacy'|'terms'|'parental_consent'|'other'
        version         VARCHAR(20)
        content         TEXT            · markdown
        effective_at    TIMESTAMP NULL
        created_at      TIMESTAMP
        UNIQUE (school_id, type, version)

    school_legal_signatures
        id              UUID PK
        document_id     UUID FK school_legal_documents(id) ON DELETE CASCADE
        signer_user_id  UUID FK users(id) ON DELETE SET NULL · idx
        signer_name     VARCHAR(200)    · cached at sign time
        signer_email    VARCHAR(200)    · cached at sign time
        signed_at       TIMESTAMP
        ip_address      VARCHAR(64)
        user_agent      VARCHAR(255)
        UNIQUE (document_id, signer_user_id)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = '029_school_legal_documents'
down_revision = '028_school_events'
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
    if not _table_exists('school_legal_documents'):
        op.create_table(
            'school_legal_documents',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('type', sa.String(40), nullable=False),
            sa.Column('version', sa.String(20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('effective_at', sa.DateTime(), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint('school_id', 'type', 'version', name='uq_school_legal_doc'),
        )

    if not _index_exists('school_legal_documents', 'ix_school_legal_docs_school_id'):
        op.create_index(
            'ix_school_legal_docs_school_id',
            'school_legal_documents',
            ['school_id'],
        )

    if not _table_exists('school_legal_signatures'):
        op.create_table(
            'school_legal_signatures',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'document_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('school_legal_documents.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'signer_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('signer_name', sa.String(200), nullable=True),
            sa.Column('signer_email', sa.String(200), nullable=True),
            sa.Column(
                'signed_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('ip_address', sa.String(64), nullable=True),
            sa.Column('user_agent', sa.String(255), nullable=True),
        )

    if not _index_exists('school_legal_signatures', 'ix_school_legal_sig_signer_user_id'):
        op.create_index(
            'ix_school_legal_sig_signer_user_id',
            'school_legal_signatures',
            ['signer_user_id'],
        )


def downgrade() -> None:
    if _table_exists('school_legal_signatures'):
        op.drop_table('school_legal_signatures')
    if _table_exists('school_legal_documents'):
        op.drop_table('school_legal_documents')
