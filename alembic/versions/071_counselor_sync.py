"""Counselor Sync · el reporte que el estudiante le manda a su consejera.

Revision ID: 071_counselor_sync
Revises: 070_ruta_de_videos
Create Date: 2026-08-29

Verónica, revisión Sprint 2 (Paso 5 de su flujo):

    "Al finalizar cada etapa, el sistema genera un reporte ejecutivo de
     progreso que el estudiante envía a su consejera antes de su reunión
     presencial."

Y el porqué, con sus palabras: *"cuando el alumno se sienta con la consejera,
ya sabe qué quiere, qué opciones realistas tiene y qué le falta por hacer. La
reunión pasa de ser una lluvia de ideas caótica a una sesión de estrategia de
alto nivel."*

## Por qué una tabla nueva y no el dossier

El dossier del asesor (`student_dossier_notes`) es lo contrario de esto: lo
escribe el profesional y **el estudiante nunca lo ve** (así lo dice su propio
servicio). Aquí el reporte lo genera y lo envía el ESTUDIANTE. Meterlo en la
misma tabla mezclaría dos cosas con dueños y permisos opuestos.

Tampoco cabe en las alertas clínicas: ahí van señales de riesgo que revisa la
psicóloga. "Mi estudiante me mandó su avance" no es una alerta.

## Por qué se guarda el CONTENIDO y no sólo el envío

Porque la consejera prepara la reunión con lo que recibió. Si el reporte se
recalculara al abrirlo, un estudiante que hace tres tests más entre el envío y
la cita cambiaría en silencio el documento sobre el que ella ya trabajó.

Es la misma razón por la que `student_year_snapshots` congela el año saliente:
un recuerdo que se actualiza solo no es un recuerdo.

## A quién le llega

Al COLEGIO del estudiante, no a una persona: el modelo no asigna psicóloga a
estudiante — el staff ve a los de su escuela (`SCHOOL_STAFF_ROLES`). Guardar
un destinatario individual inventaría un vínculo que no existe.

`school_id` es nullable a propósito: un estudiante B2C no tiene colegio y no
puede mandar nada, pero si mañana se une a uno, sus envíos viejos no deben
quedar apuntando a un colegio que entonces no tenía.

Aditiva, nullable e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


revision = '071_counselor_sync'
down_revision = '070_ruta_de_videos'
branch_labels = None
depends_on = None

_TABLA = 'counselor_sync_reports'


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
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'student_user_id',
                UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            # El colegio al que se envió · ver la cabecera.
            sa.Column(
                'school_id',
                UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('sent_at', sa.DateTime(), nullable=False),
            # La foto del reporte en el momento del envío.
            sa.Column('content', sa.JSON(), nullable=False),
            # Lo que el estudiante quiera añadir de su puño · opcional.
            sa.Column('student_note', sa.Text(), nullable=True),
            # Cuándo lo abrió alguien del colegio · para que el estudiante sepa
            # que llegó, no para medir a la consejera.
            sa.Column('read_at', sa.DateTime(), nullable=True),
        )
        op.create_index(f'ix_{_TABLA}_student', _TABLA, ['student_user_id'])
        op.create_index(f'ix_{_TABLA}_school', _TABLA, ['school_id'])
        # El panel del colegio lista "lo más reciente primero" filtrando por
        # colegio · sin este índice esa consulta escanea la tabla entera.
        op.create_index(f'ix_{_TABLA}_school_sent', _TABLA, ['school_id', 'sent_at'])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        op.drop_table(_TABLA)
