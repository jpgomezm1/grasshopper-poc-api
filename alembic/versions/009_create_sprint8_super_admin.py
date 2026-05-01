"""Sprint 8 · Panel Super Administrador

Revision ID: 009_create_sprint8_super_admin
Revises: 008_create_reports
Create Date: 2026-04-30

GH-S8-BE-03/06/10 + soft-delete schools (D-017).

What this migration does:

  1. Adds `archived_at` (DateTime, nullable) to `schools` for soft-delete.
     Existing FK `users.school_id` keeps SET NULL on delete, but in practice
     we never hard-delete; super_admin DELETE only flips archived_at and
     license_active=false. (D-017)

  2. Creates `licenses` table:
        id, school_id (FK), tier (enum: starter/pro/enterprise),
        seats (int · cantidad de estudiantes permitidos),
        starts_at, expires_at,
        status (active/expired/cancelled),
        created_at, updated_at.

     One school may have multiple license rows over time; the "current"
     one is the latest where status=active and expires_at > now().

  3. Creates `programs` table:
        id (UUID PK), program_id (str biz · unique), name, slug,
        country, city, institution, type, area, subject,
        duration_months, cost_total, currency, budget_tier,
        alliance_type, language_requirement, active,
        raw (JSON · payload original Excel), created_at, updated_at.

     Replaces the in-memory `app.data.ofertas` for the canonical catalogue
     stored in DB. The Excel import script (GH-S1-BE-02) now upserts here.

  4. Creates `audit_logs` table:
        id, user_id (FK nullable), action (str), resource_type, resource_id,
        payload (JSON), ip_address, user_agent, created_at.

     Logs every super_admin and school_admin sensitive mutation.

Idempotent: uses table_exists / column_exists guards.
Rollback: tested · drops in reverse order.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '009_create_sprint8_super_admin'
down_revision = '008_create_reports'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    # ---------- 1. schools.archived_at (soft delete) ----------
    if table_exists('schools') and not column_exists('schools', 'archived_at'):
        op.add_column(
            'schools',
            sa.Column('archived_at', sa.DateTime, nullable=True),
        )
        op.create_index('ix_schools_archived_at', 'schools', ['archived_at'])

    # ---------- 2. licenses ----------
    if not table_exists('licenses'):
        op.create_table(
            'licenses',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='CASCADE'),
                nullable=False,
                index=True,
            ),
            sa.Column('tier', sa.String(30), nullable=False, server_default='starter'),
            sa.Column('seats', sa.Integer, nullable=False, server_default='50'),
            sa.Column('starts_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('expires_at', sa.DateTime, nullable=True),
            sa.Column('status', sa.String(30), nullable=False, server_default='active'),
            sa.Column('notes', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column(
                'updated_at',
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index('ix_licenses_school_id', 'licenses', ['school_id'])
        op.create_index('ix_licenses_status', 'licenses', ['status'])

    # ---------- 3. programs ----------
    if not table_exists('programs'):
        op.create_table(
            'programs',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('program_id', sa.String(120), nullable=False, unique=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('slug', sa.String(255), nullable=False, unique=True),
            sa.Column('country', sa.String(120), nullable=False, index=True),
            sa.Column('city', sa.String(120), nullable=True),
            sa.Column('institution', sa.String(255), nullable=False, index=True),
            sa.Column('type', sa.String(60), nullable=False, index=True),
            sa.Column('area', sa.String(120), nullable=True),
            sa.Column('subject', sa.String(255), nullable=True),
            sa.Column('duration_months', sa.Integer, nullable=False),
            sa.Column('cost_total', sa.Integer, nullable=False),
            sa.Column('currency', sa.String(10), nullable=False, server_default='USD'),
            sa.Column('budget_tier', sa.String(20), nullable=False, index=True),
            sa.Column('alliance_type', sa.String(30), nullable=False, server_default='estandar'),
            sa.Column('language_requirement', sa.String(50), nullable=True),
            sa.Column('active', sa.Boolean, nullable=False, server_default=sa.text('true'), index=True),
            sa.Column('raw', sa.JSON, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column(
                'updated_at',
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index('ix_programs_program_id', 'programs', ['program_id'], unique=True)
        op.create_index('ix_programs_slug', 'programs', ['slug'], unique=True)
        op.create_index('ix_programs_country', 'programs', ['country'])
        op.create_index('ix_programs_budget_tier', 'programs', ['budget_tier'])
        op.create_index('ix_programs_active', 'programs', ['active'])

    # ---------- 4. audit_logs ----------
    if not table_exists('audit_logs'):
        op.create_table(
            'audit_logs',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
                index=True,
            ),
            sa.Column('action', sa.String(80), nullable=False, index=True),
            sa.Column('resource_type', sa.String(60), nullable=False, index=True),
            sa.Column('resource_id', sa.String(120), nullable=True, index=True),
            sa.Column('payload', sa.JSON, nullable=True),
            sa.Column('ip_address', sa.String(60), nullable=True),
            sa.Column('user_agent', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
        op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
        op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
        op.create_index('ix_audit_logs_resource_id', 'audit_logs', ['resource_id'])
        op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade() -> None:
    # 4 → 1
    if table_exists('audit_logs'):
        op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
        op.drop_index('ix_audit_logs_resource_id', table_name='audit_logs')
        op.drop_index('ix_audit_logs_resource_type', table_name='audit_logs')
        op.drop_index('ix_audit_logs_action', table_name='audit_logs')
        op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
        op.drop_table('audit_logs')

    if table_exists('programs'):
        op.drop_index('ix_programs_active', table_name='programs')
        op.drop_index('ix_programs_budget_tier', table_name='programs')
        op.drop_index('ix_programs_country', table_name='programs')
        op.drop_index('ix_programs_slug', table_name='programs')
        op.drop_index('ix_programs_program_id', table_name='programs')
        op.drop_table('programs')

    if table_exists('licenses'):
        op.drop_index('ix_licenses_status', table_name='licenses')
        op.drop_index('ix_licenses_school_id', table_name='licenses')
        op.drop_table('licenses')

    if column_exists('schools', 'archived_at'):
        op.drop_index('ix_schools_archived_at', table_name='schools')
        op.drop_column('schools', 'archived_at')
