# MIGRATION_MERGE_PLAN · Resolución conflicto 3x 037 en branches paralelas

**Fecha**: 2026-05-15
**Autor**: gh-backend (AI agent)
**Estado**: LISTO PARA EJECUCION POR JP

---

## Contexto del problema

Tres branches paralelas crearon archivos de migración Alembic numerados `037_*.py` partiendo
del mismo `down_revision = "036_flags_prompts_configs"`. Si se mergean en cualquier orden
sin renumerar, Alembic detecta múltiples cabezas (multi-head) y colapsa al hacer `upgrade head`.

---

## Cadena final de migraciones (post-renumber)

```
... 034 → 035 → 036 (main actual HEAD)
                  |
                  └─→ 037_encrypt_clinical_analysis      (F1 · merge primero)
                            |
                            └─→ 038_pipeline_status_version   (F3.4 · merge segundo)
                                      |
                                      └─→ 039_webhook_nonces      (F3.3 · merge tercero)
```

### Qué hace cada migración

| # | Archivo | Branch | Tabla(s) tocadas | Descripción |
|---|---|---|---|---|
| 037 | `037_encrypt_clinical_analysis.py` | `feature/F1-security-hardening` | `users` (ADD COLUMN) | Agrega columna `clinical_analysis_cache_enc` (BYTEA) para cifrado AES-256-GCM at-rest. Ley 1581/2012 + Ley 1090/2006. |
| 038 | `038_pipeline_status_version.py` | `feature/F3-pipeline-race-conditions` | `users` (ADD COLUMN) | Agrega columna `pipeline_status_version` (INTEGER default 1) para optimistic locking / anti-race-condition en update_pipeline_status. |
| 039 | `039_webhook_nonces.py` | `feature/F3-BE-08-11-bitrix-hardening` | `webhook_nonces` (CREATE TABLE) | Crea tabla nueva `webhook_nonces` para persistir nonces de replay-guard en Postgres (cross-dyno safe). |

---

## Orden estricto de merge a `main`

**CRITICO: los merges deben hacerse en este orden. Nunca dos ramas simultaneamente.**

### Paso 1 · F1 · `feature/F1-security-hardening` → `main`

**Prerrequisito**: ninguno (apunta a 036 que ya existe en main).

```bash
# Verificar antes del merge:
git checkout feature/F1-security-hardening
git log --oneline -3 feature/F1-security-hardening
# Confirmar que 037_encrypt_clinical_analysis.py tiene:
#   revision = "037_encrypt_clinical_analysis"
#   down_revision = "036_flags_prompts_configs"

# Merge (via PR en GitHub, no directo):
# 1. Abrir PR: feature/F1-security-hardening → main
# 2. Esperar CI verde
# 3. Merge

# Post-merge verificar en Heroku:
heroku run alembic current -a grasshopper-poc-api
# Esperado: 037_encrypt_clinical_analysis (head)
```

### Paso 2 · F3.4 · `feature/F3-pipeline-race-conditions` → `main`

**Prerrequisito**: Paso 1 completado y en produccion.

ATENCION: Esta branch toca `app/db/models.py`. Al momento del merge, si F1 tambien
modifico `app/db/models.py`, habra conflicto que resolver. Estrategia de resolucion:
- Preservar AMBAS adiciones (la columna `clinical_analysis_cache_enc` de F1 Y la columna
  `pipeline_status_version` de F3.4).
- El archivo fusionado debe tener las dos columnas.
- Ver seccion "Conflictos conocidos" mas abajo.

```bash
# Verificar que la migration apunta correcto:
git checkout feature/F3-pipeline-race-conditions
grep -E "^revision|^down_revision" alembic/versions/038_pipeline_status_version.py
# Esperado:
#   revision = "038_pipeline_status_version"
#   down_revision = "037_encrypt_clinical_analysis"

# Post-merge verificar en Heroku:
heroku run alembic current -a grasshopper-poc-api
# Esperado: 038_pipeline_status_version (head)
```

### Paso 3 · F3.3 · `feature/F3-BE-08-11-bitrix-hardening` → `main`

**Prerrequisito**: Pasos 1 y 2 completados y en produccion.

ATENCION: Esta branch toca `app/db/models.py` y `app/config.py`. Al momento del merge,
habra conflictos con F1 y F3.4. Ver seccion "Conflictos conocidos".

```bash
# Verificar que la migration apunta correcto:
git checkout feature/F3-BE-08-11-bitrix-hardening
grep -E "^revision|^down_revision" alembic/versions/039_webhook_nonces.py
# Esperado:
#   revision = "039_webhook_nonces"
#   down_revision = "038_pipeline_status_version"

# Post-merge verificar en Heroku:
heroku run alembic current -a grasshopper-poc-api
# Esperado: 039_webhook_nonces (head)
```

---

## Conflictos conocidos al momento del merge (no bloqueantes · resolver manualmente)

### `app/db/models.py` · F3.4 vs F1

F1 agrega al principio del archivo:
- Import `LargeBinary`
- Clase `EncryptedJSON(TypeDecorator)`
- Columna `clinical_analysis_cache_enc` en la clase `User`

F3.4 agrega:
- Columna `pipeline_status_version` en la clase `User` (distinto bloque · pocas lineas arriba)

Resolucion esperada: mantener AMBAS adiciones. No hay conflicto logico, solo textual porque
ambas branches modificaron `models.py` partiendo del mismo base. Git puede resolver esto
automaticamente si los cambios estan en lineas no adyacentes; si no, resolver manualmente
preservando ambos bloques.

### `app/db/models.py` · F3.3 vs {F1 + F3.4}

F3.3 agrega la misma columna `pipeline_status_version` que F3.4 (comentario mas detallado).
Al mergear F3.3 despues de F3.4, la columna ya existira. Resolver:
- Si git detecta conflicto: aceptar la version de `main` (que ya tiene la columna de F3.4).
- La unica diferencia es el comentario; preservar el comentario mas largo de F3.3 si se desea.

### `app/config.py` · F3.3 vs F1

F1 agrega `model_validator`, `allowed_origins_str`, `allowed_origins_set`, `frontend_base_url`
y el metodo `_assert_production_secrets`.

F3.3 NO tiene estos cambios (fue creada antes de F1) y ademas agrega `bitrix_max_payload_kb`.

Resolucion: al mergear F3.3 sobre `main` (que ya tiene F1), preservar AMBAS:
- Todo lo que F1 agrego en `config.py` (validaciones de seguridad)
- El campo `bitrix_max_payload_kb` que F3.3 agrega

---

## Rollback plan

### Si 037 falla en Heroku post-deploy

```bash
heroku run alembic downgrade 036_flags_prompts_configs -a grasshopper-poc-api
# Revierte solo la columna clinical_analysis_cache_enc (downgrade limpio, no borra datos legacy)
```

### Si 038 falla en Heroku post-deploy

```bash
heroku run alembic downgrade 037_encrypt_clinical_analysis -a grasshopper-poc-api
# Revierte pipeline_status_version column
```

### Si 039 falla en Heroku post-deploy

```bash
heroku run alembic downgrade 038_pipeline_status_version -a grasshopper-poc-api
# Revierte tabla webhook_nonces (DROP TABLE + DROP INDEX)
```

### Rollback total (emergencia)

```bash
heroku run alembic downgrade 036_flags_prompts_configs -a grasshopper-poc-api
# Ojo: si ya corrio FASE B de migration 037 (migracion de datos clinicos),
# los datos en clinical_analysis_cache_enc se perderan.
# Solo hacer rollback total ANTES de correr FASE B.
# Ver docs/runbooks/MIGRATION_037_PHASE_B.md para precauciones.
```

---

## Verificacion post-deploy (checklist por cada merge)

```bash
# 1. Confirmar revision actual
heroku run alembic current -a grasshopper-poc-api

# 2. Confirmar historia lineal (sin multiple heads)
heroku run alembic history -a grasshopper-poc-api | head -10

# 3. Smoke test del endpoint mas critico del dominio
# Post-037: curl -X GET .../api/v1/advisor/123/clinical_analysis (debe responder 200 o 403)
# Post-038: curl -X PATCH .../api/v1/crm/pipeline (debe responder 200 con version field)
# Post-039: activar un webhook Bitrix y verificar que no hay 500 en logs

# 4. Verificar que no hay errores en boot
heroku logs --tail -a grasshopper-poc-api | head -20
```

---

## Notas de implementacion

**Por que sin rebase completo**: los tres branches tocan `app/db/models.py` y/o `app/config.py`
en secciones que generan conflictos textuales complejos si se rebasan automaticamente. Dado que
la operacion es solo de renumber de migraciones (quirurgica), se eligio renombrar solo los archivos
`.py` de Alembic y documentar los conflictos para resolucion manual al momento del merge secuencial.
Esta decision evita riesgo de mezclar codigo de seguridad (F1 · Habeas Data) inadvertidamente.

**Referencia**: decision tomada por `gh-backend` el 2026-05-15 · validada contra instrucciones
en prompt de tarea del `gh-orchestrator`.
