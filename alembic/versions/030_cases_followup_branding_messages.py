"""Cases followup + school branding extensions + mass messages + clinical alerts

Revision ID: 030_cases_followup_branding_messages
Revises: 029_school_legal_documents
Create Date: 2026-05-04

GH-SCHOOL-ADMIN · Bloque K + E + H · Sprint school_admin 2026-05-04.

Last migration of the sprint · combines several smaller surfaces:

    student_cases_followup
        id                UUID PK
        student_user_id   UUID FK users(id) ON DELETE CASCADE   · idx
        school_id         UUID FK schools(id) ON DELETE CASCADE · idx
        opened_by_user_id UUID FK users(id) ON DELETE SET NULL
        case_type         VARCHAR(40)   · 'academic'|'emocional'|'familiar'|'otro'
        status            VARCHAR(20)   · 'open'|'in_progress'|'resolved'|'escalated'
        title             VARCHAR(200)
        description       TEXT NULL
        resolution_notes  TEXT NULL
        created_at        TIMESTAMP
        updated_at        TIMESTAMP
        resolved_at       TIMESTAMP NULL

    case_interventions
        id                UUID PK
        case_id           UUID FK student_cases_followup(id) ON DELETE CASCADE · idx
        author_user_id    UUID FK users(id) ON DELETE SET NULL
        action            VARCHAR(60)   · 'note'|'meeting'|'referral'|'parent_contact'|'closure'
        content           TEXT NOT NULL
        created_at        TIMESTAMP

    clinical_alerts
        id                UUID PK
        student_user_id   UUID FK users(id) ON DELETE CASCADE · idx
        school_id         UUID FK schools(id) ON DELETE CASCADE · idx
        severity          VARCHAR(20)    · 'medium'|'high'
        pattern_type      VARCHAR(60)    · matches behavioral_patterns label
        summary           TEXT
        source            VARCHAR(40)    · 'ai_analysis'|'manual'
        acknowledged_at   TIMESTAMP NULL
        acknowledged_by   UUID FK users(id) ON DELETE SET NULL
        case_id           UUID FK student_cases_followup(id) ON DELETE SET NULL
        created_at        TIMESTAMP

    school_mass_messages
        id                UUID PK
        school_id         UUID FK schools(id) ON DELETE CASCADE · idx
        author_user_id    UUID FK users(id) ON DELETE SET NULL
        subject           VARCHAR(200) NOT NULL
        body              TEXT NOT NULL
        audience          VARCHAR(20)        · 'students'|'parents'|'both'
        cohort_id         UUID FK cohorts(id) ON DELETE SET NULL · NULL = all cohorts
        sent_at           TIMESTAMP
        sent_count        INTEGER DEFAULT 0
        opened_count      INTEGER DEFAULT 0

    schools (extension)
        + secondary_color    VARCHAR(20) NULL
        + locale             VARCHAR(10) NULL DEFAULT 'es-CO'
        + timezone           VARCHAR(60) NULL DEFAULT 'America/Bogota'

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = '030_cases_followup_branding_messages'
down_revision = '029_school_legal_documents'
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


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    # student_cases_followup
    if not _table_exists('student_cases_followup'):
        op.create_table(
            'student_cases_followup',
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
                'opened_by_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('case_type', sa.String(40), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='open'),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('resolution_notes', sa.Text(), nullable=True),
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
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
        )

    if not _index_exists('student_cases_followup', 'ix_student_cases_school_id'):
        op.create_index(
            'ix_student_cases_school_id',
            'student_cases_followup',
            ['school_id'],
        )

    if not _index_exists('student_cases_followup', 'ix_student_cases_student_user_id'):
        op.create_index(
            'ix_student_cases_student_user_id',
            'student_cases_followup',
            ['student_user_id'],
        )

    # case_interventions
    if not _table_exists('case_interventions'):
        op.create_table(
            'case_interventions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'case_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('student_cases_followup.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'author_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('action', sa.String(60), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _index_exists('case_interventions', 'ix_case_interventions_case_id'):
        op.create_index(
            'ix_case_interventions_case_id',
            'case_interventions',
            ['case_id'],
        )

    # clinical_alerts
    if not _table_exists('clinical_alerts'):
        op.create_table(
            'clinical_alerts',
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
            sa.Column('severity', sa.String(20), nullable=False),
            sa.Column('pattern_type', sa.String(60), nullable=False),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('source', sa.String(40), nullable=False, server_default='ai_analysis'),
            sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
            sa.Column(
                'acknowledged_by',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column(
                'case_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('student_cases_followup.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _index_exists('clinical_alerts', 'ix_clinical_alerts_school_id'):
        op.create_index(
            'ix_clinical_alerts_school_id',
            'clinical_alerts',
            ['school_id'],
        )

    if not _index_exists('clinical_alerts', 'ix_clinical_alerts_student_user_id'):
        op.create_index(
            'ix_clinical_alerts_student_user_id',
            'clinical_alerts',
            ['student_user_id'],
        )

    # school_mass_messages
    if not _table_exists('school_mass_messages'):
        op.create_table(
            'school_mass_messages',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
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
            sa.Column('subject', sa.String(200), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('audience', sa.String(20), nullable=False, server_default='both'),
            sa.Column(
                'cohort_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('cohorts.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column(
                'sent_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('opened_count', sa.Integer(), nullable=False, server_default='0'),
        )

    if not _index_exists('school_mass_messages', 'ix_school_mass_msgs_school_id'):
        op.create_index(
            'ix_school_mass_msgs_school_id',
            'school_mass_messages',
            ['school_id'],
        )

    # Schools branding extension
    if not _column_exists('schools', 'secondary_color'):
        op.add_column(
            'schools',
            sa.Column('secondary_color', sa.String(20), nullable=True),
        )

    if not _column_exists('schools', 'locale'):
        op.add_column(
            'schools',
            sa.Column('locale', sa.String(10), nullable=True, server_default='es-CO'),
        )

    # 'timezone' already exists (migration 014) · skipped intentionally.


def downgrade() -> None:
    if _column_exists('schools', 'locale'):
        op.drop_column('schools', 'locale')
    if _column_exists('schools', 'secondary_color'):
        op.drop_column('schools', 'secondary_color')
    if _table_exists('school_mass_messages'):
        op.drop_table('school_mass_messages')
    if _table_exists('clinical_alerts'):
        op.drop_table('clinical_alerts')
    if _table_exists('case_interventions'):
        op.drop_table('case_interventions')
    if _table_exists('student_cases_followup'):
        op.drop_table('student_cases_followup')
