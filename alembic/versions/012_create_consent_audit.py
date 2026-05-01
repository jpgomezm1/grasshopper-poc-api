"""Sprint 11.5 · Habeas Data consent gate · GH-S11.5-BE-07

Revision ID: 012_create_consent_audit
Revises: 011_create_bitrix_sync_log
Create Date: 2026-04-30

D-026 · QA-AUD-062 · Ley 1581/2012 (Colombia) Art. 7+8.

Adds the schema needed to gate Bitrix CRM sync (and any future third-party
data share) behind explicit consent of the data subject and, when minor,
the legal guardian.

Schema changes
--------------

`users` · 5 new columns (all nullable for backward compat with existing rows):

    birthdate                       Date
        Optional birthdate · used to compute is_minor (<18). When NULL we
        assume minor for safety (more restrictive default).

    consent_data_processing_at      DateTime
        Timestamp when the user accepted the global Privacy Policy (signup
        or accept-invite). Required for any active session post-S11.5
        cutover. Existing users (pre-cutover) keep NULL · backfilled at
        login via re-acceptance flow if `consent_data_processing_version`
        differs from `settings.privacy_policy_version`.

    consent_data_processing_version String(20)
        Privacy policy version accepted (e.g. "1.0.0"). Triggers re-accept
        on policy bumps.

    consent_crm_sync_at             DateTime
        Timestamp when the user explicitly opted in to CRM (Bitrix) share.
        NULL = no opt-in · sync MUST be skipped.

    consent_parental_at             DateTime
        Timestamp when the legal guardian authorized data processing on
        behalf of a minor. Required only when is_minor.

`consent_audit_log` · new immutable audit trail table:

    id              UUID PK
    user_id         UUID FK users.id ON DELETE SET NULL · indexed
    event           String(60) · whitelisted in service layer (NOT enum'd
                    in DB to allow extension without migrations) · values
                    include: data_processing.granted | data_processing.revoked
                    | crm_sync.granted | crm_sync.revoked | parental.granted
                    | parental.revoked | data_export | data_deletion
    ip              String(50)  · X-Forwarded-For first hop · nullable
    user_agent      String(500) · nullable · truncated
    policy_version  String(20)  · for context
    created_at      DateTime    default now() · indexed

Indexes
-------
    consent_audit_log: (user_id) · (created_at desc) · (event)

Idempotent: uses table_exists / column inspection guards.
Rollback: drops columns + indexes + table in reverse order.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '012_create_consent_audit'
down_revision = '011_create_bitrix_sync_log'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    # 1. users · consent + birthdate columns
    if not column_exists('users', 'birthdate'):
        op.add_column('users', sa.Column('birthdate', sa.Date(), nullable=True))
    if not column_exists('users', 'consent_data_processing_at'):
        op.add_column(
            'users',
            sa.Column('consent_data_processing_at', sa.DateTime(), nullable=True),
        )
    if not column_exists('users', 'consent_data_processing_version'):
        op.add_column(
            'users',
            sa.Column('consent_data_processing_version', sa.String(20), nullable=True),
        )
    if not column_exists('users', 'consent_crm_sync_at'):
        op.add_column(
            'users',
            sa.Column('consent_crm_sync_at', sa.DateTime(), nullable=True),
        )
    if not column_exists('users', 'consent_parental_at'):
        op.add_column(
            'users',
            sa.Column('consent_parental_at', sa.DateTime(), nullable=True),
        )

    # 2. consent_audit_log table
    if not table_exists('consent_audit_log'):
        op.create_table(
            'consent_audit_log',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('event', sa.String(60), nullable=False),
            sa.Column('ip', sa.String(50), nullable=True),
            sa.Column('user_agent', sa.String(500), nullable=True),
            sa.Column('policy_version', sa.String(20), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            'ix_consent_audit_log_user_id',
            'consent_audit_log',
            ['user_id'],
        )
        op.create_index(
            'ix_consent_audit_log_created_at',
            'consent_audit_log',
            ['created_at'],
        )
        op.create_index(
            'ix_consent_audit_log_event',
            'consent_audit_log',
            ['event'],
        )


def downgrade() -> None:
    if table_exists('consent_audit_log'):
        if index_exists('consent_audit_log', 'ix_consent_audit_log_event'):
            op.drop_index(
                'ix_consent_audit_log_event',
                table_name='consent_audit_log',
            )
        if index_exists('consent_audit_log', 'ix_consent_audit_log_created_at'):
            op.drop_index(
                'ix_consent_audit_log_created_at',
                table_name='consent_audit_log',
            )
        if index_exists('consent_audit_log', 'ix_consent_audit_log_user_id'):
            op.drop_index(
                'ix_consent_audit_log_user_id',
                table_name='consent_audit_log',
            )
        op.drop_table('consent_audit_log')

    if column_exists('users', 'consent_parental_at'):
        op.drop_column('users', 'consent_parental_at')
    if column_exists('users', 'consent_crm_sync_at'):
        op.drop_column('users', 'consent_crm_sync_at')
    if column_exists('users', 'consent_data_processing_version'):
        op.drop_column('users', 'consent_data_processing_version')
    if column_exists('users', 'consent_data_processing_at'):
        op.drop_column('users', 'consent_data_processing_at')
    if column_exists('users', 'birthdate'):
        op.drop_column('users', 'birthdate')
