"""M-006 · token de e-sign de consentimiento parental en users (2026-06-04).

Revision ID: m006_parental_consent
Revises: 048_programs_nullable_financials
Create Date: 2026-06-04

Agrega a `users` el soporte del e-sign nativo de consentimiento parental:
- parental_consent_token (un solo uso · enviado por email al acudiente)
- parental_consent_token_expires
- parental_consent_parent_email

NOTA DE RAMA: esta migración nace de 048 igual que `049_user_test_disclaimers`
(rama F-005). Son ramas paralelas → al integrar ambas a main quedan DOS heads
y hay que crear una migración de merge (`alembic merge`). Idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'm006_parental_consent'
down_revision = '048_programs_nullable_financials'
branch_labels = None
depends_on = None

_COLS = {
    "parental_consent_token": sa.String(length=255),
    "parental_consent_token_expires": sa.DateTime(),
    "parental_consent_parent_email": sa.String(length=255),
}


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    for name, type_ in _COLS.items():
        if not _has_column(bind, "users", name):
            op.add_column("users", sa.Column(name, type_, nullable=True))
    # Índice para buscar por token (un solo uso).
    try:
        op.create_index(
            "ix_users_parental_consent_token", "users", ["parental_consent_token"]
        )
    except Exception:
        pass  # ya existe / dialecto sin soporte → no crítico


def downgrade() -> None:
    bind = op.get_bind()
    try:
        op.drop_index("ix_users_parental_consent_token", table_name="users")
    except Exception:
        pass
    for name in _COLS:
        if _has_column(bind, "users", name):
            op.drop_column("users", name)
