"""Persistent webhook nonce store for cross-dyno replay protection.

Revision ID: 039_webhook_nonces
Revises: 038_pipeline_status_version
Create Date: 2026-05-15

GH-S11.5-BE-11 · Migra WebhookReplayGuard de in-memory a Postgres para
que múltiples dynos de Heroku compartan el mismo registro de nonces vistos.

Tabla:
    webhook_nonces
        nonce       VARCHAR(128)  PK  · hash/UUID proporcionado por el productor
        source      VARCHAR(64)   NOT NULL  · 'bitrix' · 'stripe' · etc.
        seen_at     TIMESTAMPTZ   NOT NULL  DEFAULT NOW()
        expires_at  TIMESTAMPTZ   NOT NULL  · seen_at + ttl; fila purgable tras este momento

Índices:
    ix_webhook_nonces_expires_at          · barre rows expirados eficientemente
    ix_webhook_nonces_source_seen_at      · queries de monitoreo/audit por fuente
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "039_webhook_nonces"
down_revision = "038_pipeline_status_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_nonces",
        sa.Column("nonce", sa.String(128), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_webhook_nonces_expires_at",
        "webhook_nonces",
        ["expires_at"],
    )
    op.create_index(
        "ix_webhook_nonces_source_seen_at",
        "webhook_nonces",
        ["source", "seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_nonces_source_seen_at", table_name="webhook_nonces")
    op.drop_index("ix_webhook_nonces_expires_at", table_name="webhook_nonces")
    op.drop_table("webhook_nonces")
