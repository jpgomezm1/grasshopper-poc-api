"""User admin lifecycle fields · suspended_at · last_login_at · created_by_user_id.

Revision ID: 033_user_admin_lifecycle
Revises: 032_parent_message_reads
Create Date: 2026-05-05

GH-SUPERADMIN-EXPERIENCE · Bloque A · global user CRUD.

Adds three lifecycle columns to `users`:
    suspended_at        TIMESTAMP NULL  · soft suspend (separate from is_active=false)
    last_login_at       TIMESTAMP NULL  · stamped on each successful login
    created_by_user_id  UUID NULL FK → users(id) · audit who created this user

`is_active=false` is preserved for backward compat (existing soft-delete);
`suspended_at` is the new dedicated column for super_admin-driven suspends.
The two are decoupled: a user can be suspended (suspended_at NOT NULL) without
flipping is_active, which keeps the existing flow untouched.

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '033_user_admin_lifecycle'
down_revision = '032_parent_message_reads'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, col: str) -> bool:
    insp = inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return col in cols


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "users", "suspended_at"):
        op.add_column("users", sa.Column("suspended_at", sa.DateTime(), nullable=True))

    if not _has_column(bind, "users", "last_login_at"):
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
        op.create_index("ix_users_last_login_at", "users", ["last_login_at"])

    if not _has_column(bind, "users", "created_by_user_id"):
        op.add_column(
            "users",
            sa.Column(
                "created_by_user_id",
                sa.dialects.postgresql.UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(36),
                nullable=True,
            ),
        )
        # FK only on PG (sqlite tests skip the constraint silently)
        if bind.dialect.name == "postgresql":
            op.create_foreign_key(
                "fk_users_created_by",
                "users",
                "users",
                ["created_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "users", "created_by_user_id"):
        if bind.dialect.name == "postgresql":
            try:
                op.drop_constraint("fk_users_created_by", "users", type_="foreignkey")
            except Exception:
                pass
        op.drop_column("users", "created_by_user_id")
    if _has_column(bind, "users", "last_login_at"):
        try:
            op.drop_index("ix_users_last_login_at", "users")
        except Exception:
            pass
        op.drop_column("users", "last_login_at")
    if _has_column(bind, "users", "suspended_at"):
        op.drop_column("users", "suspended_at")
