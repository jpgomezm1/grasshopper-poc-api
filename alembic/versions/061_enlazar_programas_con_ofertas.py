"""Enlaza cada programa investigado con la ficha del catálogo a la que pertenece.

Revision ID: 061_enlazar_programas_con_ofertas
Revises: 060_vectores_perfil_y_catalogo

Sin este enlace hay dos catálogos que hablan de lo mismo y no se saben
relacionados: el estudiante ve "Murdoch University" en las ofertas y "Bachelor
of Veterinary Science · Murdoch University" en la búsqueda, sin nada que le diga
que son la misma institución. Es redundancia desde su punto de vista, aunque
para nosotros sean dos tablas con dueños distintos.

Con `program_id` cada programa sabe de qué ficha cuelga, y entonces:

  · la ficha de una institución puede mostrar SUS programas;
  · un programa puede llevar a la ficha de su institución;
  · la búsqueda puede decir cuáles instituciones ya están autorizadas.

Es **nullable** a propósito: hay instituciones cuyos programas extrajimos y que
no tienen ficha en el catálogo del cliente (redes que se descompusieron en sus
miembros, colegios que aparecieron dentro de un holding). Esos programas siguen
siendo válidos y visibles; sólo no cuelgan de ninguna oferta.

`ondelete=SET NULL` y no CASCADE: si la agencia da de baja una ficha, sus
programas investigados no deben desaparecer con ella — quedan huérfanos y
visibles, que es lo honesto mientras nadie confirme lo contrario.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "061_enlazar_programas_con_ofertas"
down_revision = "060_vectores_perfil_y_catalogo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columnas = {c["name"] for c in inspector.get_columns("programas_investigados")}
    if "program_id" in columnas:
        return

    op.add_column(
        "programas_investigados",
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_prog_inv_program", "programas_investigados", "programs",
        ["program_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "ix_prog_inv_program_id", "programas_investigados", ["program_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_prog_inv_program_id", table_name="programas_investigados")
    op.drop_constraint("fk_prog_inv_program", "programas_investigados",
                       type_="foreignkey")
    op.drop_column("programas_investigados", "program_id")
