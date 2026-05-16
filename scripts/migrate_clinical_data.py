"""Script de migración FASE B · cifra clinical_analysis_cache existente.

FASE A (Alembic migration 037): agrega columna `clinical_analysis_cache_enc`.
FASE B (este script):           mueve datos plaintext → cifrado + nullea original.

USO:
    # Simular sin escribir en DB:
    python scripts/migrate_clinical_data.py --dry-run

    # Migrar en lotes de 100 (default):
    python scripts/migrate_clinical_data.py

    # Lotes más pequeños para DBs muy grandes:
    python scripts/migrate_clinical_data.py --chunk-size 50

PREREQUISITOS antes de correr en producción:
  1. alembic upgrade head ya corrió (columna _enc existe)
  2. FIELD_ENCRYPTION_KEY está configurada en el entorno
  3. DATABASE_URL apunta a la DB correcta
  4. La app (Heroku) ya está leyendo de _enc (código F1-SECURITY desplegado)

Ver docs/runbooks/MIGRATION_037_PHASE_B.md para checklist completo.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

# Imports de app a nivel de módulo para permitir mocking en tests.
# Se cargan aquí (no en la función) de modo que patch() puede interceptarlos.
from app.db.database import SessionLocal
from app.db.models import User
from app.core.crypto import encrypt_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("migrate_clinical_data")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra clinical_analysis_cache plaintext → AES-256-GCM cifrado"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la migración sin escribir en la DB",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Rows por transacción (default: 100)",
    )
    return parser.parse_args()


def run_migration(dry_run: bool = False, chunk_size: int = 100) -> dict[str, int]:
    """Ejecuta la migración de datos con manejo transaccional seguro.

    Estrategia por chunk:
      1. Cargar hasta `chunk_size` rows con clinical_analysis_cache IS NOT NULL
         y clinical_analysis_cache_enc IS NULL.
      2. Por cada row: cifrar, asignar _enc, flush, verificar que _enc IS NOT NULL
         antes de nullear la columna vieja.
      3. db.commit() al final del chunk exitoso.
      4. Si cualquier row del chunk falla: db.rollback() del chunk entero,
         incrementar `failed`, continuar con el siguiente chunk.

    Returns:
        dict con claves: migrated, failed, skipped.
    """
    stats: dict[str, int] = {"migrated": 0, "failed": 0, "skipped": 0}

    db = SessionLocal()
    try:
        offset = 0
        while True:
            # Carga el siguiente chunk de rows pendientes
            rows = (
                db.query(User)
                .filter(
                    User.clinical_analysis_cache.isnot(None),
                    User.clinical_analysis_cache_enc.is_(None),
                )
                .order_by(User.id)
                .limit(chunk_size)
                .offset(offset)
                .all()
            )

            if not rows:
                break

            logger.info(
                "chunk offset=%d rows=%d (dry_run=%s)", offset, len(rows), dry_run
            )

            chunk_had_error = False
            for user in rows:
                try:
                    raw_value: Any = user.clinical_analysis_cache

                    # Saltar si por alguna razón ya está cifrado
                    if user.clinical_analysis_cache_enc is not None:
                        stats["skipped"] += 1
                        continue

                    if dry_run:
                        # Solo verificar que el valor es serializable
                        json.dumps(raw_value)
                        stats["migrated"] += 1
                        continue

                    # Cifrar
                    encrypted_bytes = encrypt_json(raw_value)

                    # Asignar y flush para materializar en la sesión
                    user.clinical_analysis_cache_enc = encrypted_bytes
                    db.flush()

                    # Verificar que _enc quedó non-null ANTES de limpiar la vieja
                    db.refresh(user)
                    if user.clinical_analysis_cache_enc is None:
                        raise ValueError(
                            f"user_id={user.id}: _enc es None después del flush"
                        )

                    # Ahora es seguro nullear la columna vieja
                    user.clinical_analysis_cache = None
                    stats["migrated"] += 1

                except Exception as exc:
                    logger.error(
                        "row_error user_id=%s error=%r · row se deja intacta",
                        str(user.id),
                        str(exc),
                    )
                    chunk_had_error = True
                    stats["failed"] += 1
                    # Rollback de la sesión entera del chunk para no dejar estado sucio
                    db.rollback()
                    break

            if not dry_run and not chunk_had_error:
                db.commit()
                logger.info(
                    "chunk committed offset=%d", offset,
                )
            elif dry_run:
                db.rollback()

            # Avanzar offset. Si hubo errores en el chunk, avanzar igualmente
            # para evitar bucle infinito sobre rows problemáticas.
            offset += chunk_size

    finally:
        db.close()

    return stats


def main() -> None:
    args = _parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN · no se escribirá en la DB ===")

    logger.info(
        "Iniciando migración clinical_analysis_cache · chunk_size=%d dry_run=%s",
        args.chunk_size,
        args.dry_run,
    )

    stats = run_migration(dry_run=args.dry_run, chunk_size=args.chunk_size)

    logger.info(
        "Migración completada · migrated=%d · failed=%d · skipped=%d",
        stats["migrated"],
        stats["failed"],
        stats["skipped"],
    )

    if stats["failed"] > 0:
        logger.error(
            "%d rows fallaron. Revisar logs arriba para user_ids problemáticos. "
            "Correr de nuevo el script para reintentar.",
            stats["failed"],
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
