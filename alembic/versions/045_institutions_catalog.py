"""Institutions catalogue table · cliente xlsx 2026-05-28.

Revision ID: 045_institutions_catalog
Revises: 044_programs_visa_roi
Create Date: 2026-05-28

GH-LOCAL-CLIENT-CATALOG · el cliente entregó el xlsx
`Resumen nuevo contratos - Google Sheets - Trabajar sobre este.xlsx`
con ~730 instituciones reales + relaciones comerciales (partner
groups · estado de contrato · comisiones · vigencia). Esto NO encaja
en `programs` (que es catálogo de programas concretos con cost +
duration); requiere su propia tabla.

La tabla es read-mostly: la pobla `scripts/import_institutions.py`
parseando el xlsx. El super_admin la puede editar; el gh_advisor solo
lectura.

Table:
    institutions_catalog
        id                   UUID PRIMARY KEY
        name                 VARCHAR(255) NOT NULL    · nombre de la institución
        category             VARCHAR(60) NULL         · Universidad | College Privado | Instituto Idiomas | College Público | High School | Proveedor | Polytechnic | Business School | Summer School | Camps
        country              VARCHAR(120) NULL        · canónico (Canada, USA, UK, Australia, ...)
        country_raw          VARCHAR(120) NULL        · valor original del xlsx (Canadá, Estados Unidos, ...)
        city                 VARCHAR(255) NULL
        partner_group        VARCHAR(120) NULL        · Shorelight | Navitas | INTO | Study Group | Kaplan HED | UP | Wellspring | Oxford International | ...
        programs_offered     JSON NULL                · lista de strings: ['Idiomas', 'Foundation', 'Pregrado', 'Postgrado', ...]
        agreement_status     VARCHAR(40) NULL         · Signed | Al Día | Vencido | Pendiente | Cancelado
        starting_date        DATE NULL
        end_date             DATE NULL
        contact_name         VARCHAR(255) NULL
        contact_email        VARCHAR(255) NULL
        website              VARCHAR(500) NULL
        territories          VARCHAR(255) NULL
        commissions          JSON NULL                · lista de {value, description}
        source_sheet         VARCHAR(60) NULL         · nombre del sheet de origen (Instituciones / Instituciones Resumen / INTO / ...)
        active               BOOLEAN NOT NULL DEFAULT TRUE
        raw                  JSON NULL                · row completa original para trazabilidad
        created_at           TIMESTAMP NOT NULL
        updated_at           TIMESTAMP NOT NULL

Indexes:
    - (name) lower
    - (country)
    - (category)
    - (partner_group)
    - (agreement_status)
    - (active)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '045_institutions_catalog'
down_revision = '044_programs_visa_roi'
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    insp = inspect(bind)
    return name in insp.get_table_names()


def _has_index(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        indexes = insp.get_indexes(table)
    except Exception:
        return False
    return any(ix["name"] == name for ix in indexes)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    UUID = sa.dialects.postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    JSON_T = sa.dialects.postgresql.JSONB if is_pg else sa.JSON

    if not _has_table(bind, "institutions_catalog"):
        op.create_table(
            "institutions_catalog",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("category", sa.String(60), nullable=True),
            sa.Column("country", sa.String(120), nullable=True),
            sa.Column("country_raw", sa.String(120), nullable=True),
            sa.Column("city", sa.String(255), nullable=True),
            sa.Column("partner_group", sa.String(120), nullable=True),
            sa.Column("programs_offered", JSON_T, nullable=True),
            sa.Column("agreement_status", sa.String(40), nullable=True),
            sa.Column("starting_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("contact_name", sa.String(255), nullable=True),
            sa.Column("contact_email", sa.String(255), nullable=True),
            sa.Column("website", sa.String(500), nullable=True),
            sa.Column("territories", sa.String(255), nullable=True),
            sa.Column("commissions", JSON_T, nullable=True),
            sa.Column("source_sheet", sa.String(60), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("raw", JSON_T, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    for col, idx in (
        ("country", "ix_institutions_catalog_country"),
        ("category", "ix_institutions_catalog_category"),
        ("partner_group", "ix_institutions_catalog_partner_group"),
        ("agreement_status", "ix_institutions_catalog_agreement_status"),
        ("active", "ix_institutions_catalog_active"),
    ):
        if not _has_index(bind, "institutions_catalog", idx):
            op.create_index(idx, "institutions_catalog", [col])

    if is_pg and not _has_index(bind, "institutions_catalog", "ix_institutions_catalog_name_lower"):
        op.execute(
            "CREATE INDEX ix_institutions_catalog_name_lower "
            "ON institutions_catalog (lower(name))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "institutions_catalog"):
        for ix in (
            "ix_institutions_catalog_country",
            "ix_institutions_catalog_category",
            "ix_institutions_catalog_partner_group",
            "ix_institutions_catalog_agreement_status",
            "ix_institutions_catalog_active",
            "ix_institutions_catalog_name_lower",
        ):
            try:
                op.drop_index(ix, "institutions_catalog")
            except Exception:
                pass
        op.drop_table("institutions_catalog")
