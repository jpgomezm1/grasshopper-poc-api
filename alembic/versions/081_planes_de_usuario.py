"""Planes por usuario (gratis · pago · VIP) y las cuentas que ya existían.

Revision ID: 081_planes_de_usuario
Revises: 080_practica_vista

D-1 · Sprint 4 (2026-10-29). Crea `user_plans` (ver el modelo `UserPlan`) y
aplica la decisión D9 de JP: **ninguna cuenta que ya existe pierde acceso**.

- Estudiantes de un colegio: no se les escribe nada. Su plan se deriva de la
  licencia del colegio (`plan_service.plan_vigente`).
- Estudiantes sin colegio (B2C) que ya existían: se les escribe un plan `pago`
  sin vencimiento, marcado como de la migración. El vencimiento real de estas
  cuentas está pendiente con la clienta (insumo V-2); cuando se decida, se
  agrega una fila nueva con `hasta`, sin tocar esta.

Desde aquí, toda cuenta nueva sin licencia arranca `gratis`.
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "081_planes_de_usuario"
down_revision = "080_practica_vista"
branch_labels = None
depends_on = None

_TABLA = "user_plans"
METODO_MIGRACION = "cuenta existente antes de Sprint 4 (D9)"


def _has_table(bind, name: str) -> bool:
    try:
        return name in inspect(bind).get_table_names()
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, _TABLA):
        op.create_table(
            _TABLA,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("plan", sa.String(10), nullable=False),
            sa.Column("desde", sa.DateTime(), nullable=False),
            sa.Column("hasta", sa.DateTime(), nullable=True),
            sa.Column(
                "activado_por_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("metodo", sa.String(120), nullable=True),
            sa.Column("notas", sa.Text(), nullable=True),
            sa.Column("creado_en", sa.DateTime(), nullable=False),
        )
        op.create_index(f"ix_{_TABLA}_user_id", _TABLA, ["user_id"])

    # D9 · los estudiantes B2C que ya existían quedan como `pago`. Idempotente:
    # solo a quien no tenga ya una fila de esta migración.
    ahora = datetime.utcnow()
    filas = bind.execute(
        sa.text(
            "SELECT u.id FROM users u "
            # El enum vivo guarda el NOMBRE ('STUDENT', ver la nota en la 013);
            # se acepta también el valor por si alguna base quedó con el de la 003.
            "WHERE CAST(u.role AS TEXT) IN ('STUDENT', 'student') AND u.school_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM user_plans p WHERE p.user_id = u.id AND p.metodo = :m)"
        ),
        {"m": METODO_MIGRACION},
    ).fetchall()
    if filas:
        op.bulk_insert(
            sa.table(
                _TABLA,
                sa.column("id", UUID(as_uuid=True)),
                sa.column("user_id", UUID(as_uuid=True)),
                sa.column("plan", sa.String),
                sa.column("desde", sa.DateTime),
                sa.column("metodo", sa.String),
                sa.column("creado_en", sa.DateTime),
            ),
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": f[0],
                    "plan": "pago",
                    "desde": ahora,
                    "metodo": METODO_MIGRACION,
                    "creado_en": ahora,
                }
                for f in filas
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        op.drop_table(_TABLA)
