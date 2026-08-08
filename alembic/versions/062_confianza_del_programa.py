"""Cuánto se puede confiar en cada programa investigado.

Revision ID: 062_confianza_del_programa
Revises: 061_enlazar_programas_con_ofertas

Los 15.483 programas no son igual de sólidos y hasta ahora se mostraban todos
igual. Eso es lo peligroso: no que haya filas flojas —las hay y es inevitable
cuando el dato sale de leer sitios web— sino que **nada distinga una fila
verificable de una reconstruida**.

Los tres niveles salen de señales que ya están en la fila, no de una opinión:

  `verificable`  · publica un código oficial (CRICOS, RTO, código nacional).
                   Un asesor puede confirmarlo en el registro público del país.
                   3.430 programas.
  `publicado`    · sin código, pero su URL apunta a su propia ficha: el nombre
                   se copió de la página del programa. 7.186 programas.
  `indicativo`   · sin código y su URL la comparte con otros programas, o sea
                   que apunta a un listado. El nombre puede venir de esa lista o
                   del slug de la URL, no de una ficha propia. 4.867 programas.

**No hay nivel "confirmado"**, y su ausencia es deliberada: ninguno de estos
programas lo ha validado la agencia. El día que llegue el Excel de la clienta,
lo confirmado no vive aquí — pasa a `programs`.
"""
from alembic import op
import sqlalchemy as sa

revision = "062_confianza_del_programa"
down_revision = "061_enlazar_programas_con_ofertas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columnas = {c["name"] for c in inspector.get_columns("programas_investigados")}
    if "confianza" in columnas:
        return

    # Sin `server_default`: una fila nueva sin confianza calculada debe verse
    # como NULL y no colarse en el tramo bueno por omisión.
    op.add_column(
        "programas_investigados",
        sa.Column("confianza", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_prog_inv_confianza", "programas_investigados", ["confianza"],
    )


def downgrade() -> None:
    op.drop_index("ix_prog_inv_confianza", table_name="programas_investigados")
    op.drop_column("programas_investigados", "confianza")
