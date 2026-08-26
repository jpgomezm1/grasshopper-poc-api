# Contexto para agentes · backend Mentoring

> FastAPI + SQLAlchemy + Alembic · Python **3.11.7** (fijado en `runtime.txt`) · Heroku.
> API de una plataforma de orientación profesional **en producción, con usuarios reales**,
> parte de ellos **menores de edad**.

---

## 🔴 Antes de tocar nada

1. **`main` es despliegue.** Pushear a `main` despliega Y corre `alembic upgrade head` en
   producción. No se mergea sin autorización de JP. Trabaja en ramas.
2. **Las migraciones deben ser aditivas y nullable**, e idempotentes (mira cualquiera de
   `alembic/versions/05*.py`: comprueban si la columna existe antes de crearla). Un
   `alembic heads` con **más de un head** rompe el release.
3. **No toques `clinical_analysis_service.py`.** El detector de riesgo suicida tiene falsos
   positivos conocidos —*"no quiero vivir en el exterior"* dispara protocolo— y **bajarle
   sensibilidad lo valida la psicóloga de la agencia**, no quien programa.
4. **`scripts/seed_test_data.py` no se corre tal cual**: mete ~50 programas con precios
   inventados en la tabla que sirve el catálogo real, y `--clean` borra cuentas de verdad.
5. **Bitrix es el CRM de producción del cliente.** Cero escrituras sin autorización.
6. **Datos clínicos: sólo psicóloga, asesor y super_admin** (`_require_clinical_role`). Nunca
   el estudiante ni la familia. Base legal: Ley 1581/2012 art. 5 y Ley 1090/2006.

---

## Los dos errores que más se repiten aquí

### 1. Escribir un campo que nadie lee, o leer uno que nadie escribe

Ha pasado **cuatro veces**: `voice_career` se sigue leyendo aunque ya nadie lo escriba;
`answers["city"]` se leía en tres sitios sin que ninguna pregunta lo produjera; el
`class_placement` del test de inglés era código muerto en el endpoint; y las respuestas de A9
se guardaban sin llegar al prompt.

**Regla:** si añades una pregunta, **conéctala al consumidor en el mismo commit**. Si añades
un campo que lee la IA, verifica que algo lo escriba. Ambos lados o ninguno.

### 2. Tests que pasan sin ejercitar el camino real

El 05-08, once tests en verde convivían con una funcionalidad **rota al 100%**: el módulo
importaba `app.services.ai_client` (no existe; es `app.core.ai_client`), y ese import vive
dentro de la función, así que ningún test lo tocaba — el archivo decía literalmente *"no se
llama al modelo de verdad en ningún test"*.

**Regla:** mockea la **frontera** (el cliente HTTP, el SDK), no la función que estás probando.
Y prueba tu test al revés: revierte el arreglo y comprueba que falla.

---

## Estructura

```
app/
  api/v1/      43 routers · auth.py, me.py, cv.py, vocational_tests.py, clinical.py…
  core/        state_machine.py (los 16 pasos del journey), ai_client.py, security…
  services/    48 servicios · ai_service, consolidation_service, crm_service, dossier_service…
  prompts/     14 prompts de IA · texto plano con {placeholders}
  data/        bancos de datos estáticos · english_test_questions.py (AMES, 60 preguntas)
  schemas/     Pydantic
  db/models.py  el modelo entero, incluidos los 7 roles
alembic/versions/   57 migraciones
tests/              94 archivos · ~1343 tests
```

**IA:** modelo por defecto `claude-sonnet-4-6` (`app/config.py`), sobreescribible con
`AI_MODEL`. **Todo consumo se registra** con `record_ai_usage(...)` — ojo, `provider` es
obligatorio y keyword-only; olvidarlo lanza `TypeError` que un `except` puede tragarse
dejando la auditoría vacía en silencio (ya pasó).

---

## Entorno local · lo que muerde

- **OneDrive deshidrata el `.venv`.** Si aparecen errores raros de import, recrearlo:
  `python3.11 -m venv .venv` + `pip install -r requirements.txt`.
- **La rama local de Neon (`local-jp`) no tiene las migraciones 051 y 052** → cualquier script
  que lea `vocational_test_results` o `cv_profiles` falla en local. Producción sí las tiene.
- **El PDF da 503 en Windows** (WeasyPrint necesita GTK). Pon `CLINICAL_PDF_ENABLED=false`.
- **El `.env` local NO apunta a la base de producción** — aquí decía lo contrario y es falso.
  Son dos endpoints distintos de Neon: el `.env` local es `ep-divine-mouse-…` y producción es
  `ep-bitter-feather-…`. Comprobado el 2026-08-11 de dos formas: comparando los hosts de
  `DATABASE_URL` (local vs `heroku config`), y porque el release que desplegó las migraciones
  063-066 las **corrió** en producción cuando la base local ya estaba en `066`.

  Importa en las dos direcciones: probar en local **no** escribe datos reales (el QA a mano
  contra el backend local es seguro), y `alembic current` en local **no** dice en qué versión
  está producción — eso se pregunta con `heroku releases:output` o contra la base de Heroku.
  Los tests usan SQLite en memoria a propósito, eso no cambia.
- **PowerShell suele funcionar donde Bash falla** (el clasificador bloquea comandos de forma
  intermitente).

---

## Antes de dar algo por terminado

```powershell
.venv\Scripts\python.exe -m pytest -q          # exit 0, no sólo "sin salida"
.venv\Scripts\python.exe -m alembic heads      # UN solo head
```

Comentarios **en español y explicando el porqué**, no el qué. Este repo documenta sus
decisiones no obvias en el propio código; mantenlo.

---

## Marca · Mentoring (rebrand 2026-08-19)

El producto se llama **Mentoring**. Manual en `docs/Marca/` (un nivel arriba del repo).

- **`app/services/brand.py` es la fuente única** de colores y `@font-face` para todo lo que
  el backend imprime. Antes había tres paletas incompatibles —el reporte y los correos con
  un morado del POC, la hoja de vida con el lima/azul viejo, el clínico con su verde— y
  ninguna era la marca vigente. No vuelvas a escribir hex a mano en una plantilla.
- **Los colores de riesgo del informe clínico NO son de marca** (rojo/ámbar/azul). Los lee
  la psicóloga; no los toques por estética.
- Las fuentes viven en `app/templates/static/fonts/`. WeasyPrint no sale a internet: se
  referencian relativas al `base_url` (= `app/templates`).
- **La mascota se llama Mento** (decidido el 2026-08-25 por AH). En código sigue siendo "Hop" (`hop_chat_service`,
  `/v1/hop/*`); en cualquier texto que vea el usuario —y en los prompts de `app/prompts/`—
  es **Mento**. Los prompts ahora le dicen su nombre; antes le prohibían tener uno.
- El dominio de los correos (`hola@grasshopper.co`) **no cambió**: sólo el nombre visible
  del remitente. Está pendiente con el cliente.

---

## 📄 Dónde está el contexto que NO vive en este repo

Este repo tiene el código; el **porqué** está en el workspace, un nivel por encima. Si lo
clonaste suelto desde GitHub, **pídelo antes de tomar decisiones de producto** — hay mucha
cosa que parece un descuido y es deliberada.

| Qué buscas | Dónde |
|---|---|
| Estado real, con evidencia `archivo:línea` | `Docs/Entrega/ESTADO_REAL_VERIFICADO.md` |
| **Por qué algo se hizo distinto a como se pidió** | `Docs/Entrega/DECISIONES_DE_IMPLEMENTACION.md` |
| Qué hace daño si lo tocas | `Docs/Entrega/RIESGOS_Y_DEUDA.md` |
| Lo no construido, con spec lista | `Docs/Entrega/PROPUESTAS_PENDIENTES.md` |
| **El razonamiento crudo detrás de cada decisión** | `Docs/Transcripts/` |

**Los transcripts son el único sitio donde queda por qué se descartó la alternativa.**
`Reuniones/` tiene la reunión con el cliente del 21-07 (de ahí salieron los 25 ítems de
feedback); `Sesiones de trabajo/` tiene las sesiones de desarrollo en markdown, con su
`INDICE.md`. Las más útiles: **28-07** (validación de 89 ítems contra el código) y **05-08**
(el cierre R6 y el despliegue).

Consúltalos **antes de "arreglar" algo raro** y **antes de cambiar copy**: suele haber una
frase textual del cliente detrás.
