# Runbook: Migration 037 · Fase B
## Cifrado at-rest de clinical_analysis_cache · datos existentes

**Contexto**: La migración Alembic `037_encrypt_clinical_analysis` (Fase A) agrega
la columna `clinical_analysis_cache_enc` pero NO migra datos existentes. Este
runbook documenta cómo ejecutar la Fase B: mover datos plaintext a la columna
cifrada de forma transaccionalmente segura.

**Cuándo ejecutar**: Una vez que el código de la Fase A esté desplegado en
producción Y la app esté leyendo de `_enc` (código `GH-F1-SECURITY` mergeado y
activo en Heroku).

---

## Prerequisitos

1. `alembic upgrade head` corrió exitosamente en prod (columna `_enc` existe).
2. `FIELD_ENCRYPTION_KEY` está configurada como variable de entorno en Heroku.
3. La app (Heroku dyno) ya usa el código F1-SECURITY que lee de `_enc` primero.
4. Hay backup reciente de la DB de Neon antes de correr.
5. Ventana de mantenimiento reservada (el script no requiere downtime, pero
   conviene correr fuera de horas pico por el overhead de CPU de cifrado).

---

## Pasos

### 1. Verificar prerequisitos

```bash
# Confirmar que la columna existe en prod
heroku run "python -c \"
from app.db.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text(\\\"SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='clinical_analysis_cache_enc'\\\")).fetchone()
print('columna existe:', r is not None)
db.close()
\"" -a grasshopper-api

# Confirmar que FIELD_ENCRYPTION_KEY está seteada
heroku config:get FIELD_ENCRYPTION_KEY -a grasshopper-api | wc -c
# Debe ser > 1 (si imprime solo "0" o "" la key no está configurada)
```

### 2. Dry run primero

```bash
heroku run "python scripts/migrate_clinical_data.py --dry-run" -a grasshopper-api
```

Verificar que el output dice `migrated=N · failed=0 · skipped=0` sin errores.

### 3. Migración real en chunks de 100 (default)

```bash
heroku run "python scripts/migrate_clinical_data.py" -a grasshopper-api
```

Si la DB tiene muchos rows con datos clínicos o la conexión Heroku es inestable,
usar chunks más pequeños:

```bash
heroku run "python scripts/migrate_clinical_data.py --chunk-size 25" -a grasshopper-api
```

### 4. Verificar resultado

```bash
heroku run "python -c \"
from app.db.database import SessionLocal
from app.db.models import User
db = SessionLocal()
total = db.query(User).count()
with_plaintext = db.query(User).filter(User.clinical_analysis_cache.isnot(None)).count()
with_enc = db.query(User).filter(User.clinical_analysis_cache_enc.isnot(None)).count()
print(f'total={total} with_plaintext={with_plaintext} with_enc={with_enc}')
db.close()
\"" -a grasshopper-api
```

Esperado: `with_plaintext=0` (o solo rows sin datos clínicos).

### 5. (Opcional · sprint posterior) Dropear columna vieja

Una vez confirmado que `with_plaintext=0` y la app lleva al menos 7 días
en prod sin leer de `clinical_analysis_cache`, es seguro crear un migration
que droppee la columna vieja.

```python
# En una nueva migration (ej. 038_drop_clinical_plaintext.py):
def upgrade() -> None:
    op.drop_column("users", "clinical_analysis_cache")

def downgrade() -> None:
    op.add_column("users", sa.Column("clinical_analysis_cache", postgresql.JSONB(), nullable=True))
```

**NO correr este paso hasta tener confirmación de JP y validar 7 días sin
incidentes en producción.**

---

## Rollback

Si la migración de datos falla o produce resultados inesperados:

1. El script hace rollback por chunk, así que las rows no migradas quedan
   intactas en `clinical_analysis_cache`.
2. La app sigue funcionando (lee de `_enc` primero, cae a la vieja para legacy).
3. Corregir el problema (ver logs con `user_id` problemáticos) y volver a
   correr el script (es idempotente: solo procesa rows donde `_enc IS NULL`).
4. Si se necesita revertir la Fase A (columna _enc):
   ```bash
   heroku run "alembic downgrade -1" -a grasshopper-api
   ```
   Esto droppea `clinical_analysis_cache_enc`. Los datos siguen en la columna vieja.

---

## Responsable

DRI de este runbook: **Tomás** (tech lead Grasshopper) · revisión previa **JP**.
Fecha de creación: 2026-05-15 · GH-F1-SECURITY Tarea 4 FASE B.
