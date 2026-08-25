"""La ruta del adulto profesional · los hechos propios de ese perfil.

**Este módulo NO está enganchado a la conversación de onboarding.** El motor
conversacional (`onboarding_hechos.py`, `onboarding_conversacional.py`) es
propiedad de otro agente; este archivo es la pieza que le entrego para que él
la enganche, siguiendo el mismo patrón que ya usa para `budget`
(`onboarding_hechos.SOLO_PERFIL`).

## Qué hay aquí

Los 5 hechos que sólo le corresponden al perfil `profesional`
(`onboarding_hechos.PERFIL_PROFESIONAL`, derivado de `life_stage` en
`university | recent_grad | working | career_change`):

1. `career_linkedin_profile_text` · el perfil de LinkedIn pegado como texto.
   **Obligatorio** — sin esto no hay con qué comparar nada. Se reutiliza
   `linkedin_import_service` (YA EXISTE, no se reescribió) para estructurarlo;
   ver `app/services/career_gap_service.py` y el router
   `app/api/v1/career_gap.py`, que exponen esto también como flujo directo
   (`PUT /me/career-gap/linkedin`) para quien llega sin pasar por el chat.
2. `career_current_role` · su cargo actual, autoreportado.
3. `career_job_satisfaction_score` · 1 a 5, qué tan satisfecho está HOY.
   **Obligatorio** — es la mitad de la "auditoría de trayectoria" que se pidió.
4. `career_job_satisfaction_text` · por qué calificó así, en sus palabras.
5. `career_target_role` · su "puesto ideal" (ej. "Data Analyst remoto").
   **Obligatorio** — es el otro lado de la comparación del análisis de brecha.

## Cómo engancharlo (para quien mantiene `onboarding_hechos.py`)

Mismo patrón que ya usan ustedes con `budget` — no hace falta un mecanismo
nuevo, `aplica()` y `faltantes()` de `onboarding_hechos.py` ya saben ramificar
por perfil vía `SOLO_PERFIL`:

```python
from app.data.adult_track_hechos import HECHOS_ADULTO, SOLO_PERFIL_ADULTO, QUE_AVERIGUAR_ADULTO

HECHOS.extend(HECHOS_ADULTO)                  # se suman al catálogo
SOLO_PERFIL.update(SOLO_PERFIL_ADULTO)        # se ramifican por perfil
QUE_AVERIGUAR.update(QUE_AVERIGUAR_ADULTO)    # el modelo sabe qué preguntar
OBLIGATORIOS = OBLIGATORIOS + OBLIGATORIOS_ADULTO_IDS   # ver abajo
```

`OBLIGATORIOS_ADULTO_IDS` NO se suma a ciegas al `OBLIGATORIOS` de colegio: son
obligatorios sólo para quien es profesional, y `listo_para_cerrar()` /
`faltantes()` ya filtran con `aplica(hecho_id, recolectados)` antes de mirar si
algo es obligatorio — así que sumarlos es seguro (a un estudiante de colegio
`aplica()` les devuelve `False` y nunca se le piden). Igual que pasa hoy con
`budget`.

También conviene sumarlos a `ORDEN_CONVERSACION` (sugerido: después del bloque
`voice_*`, en el lugar donde hoy va la logística — son la logística del
profesional). Eso es una decisión de flujo que les toca a ustedes; aquí sólo
dejo `ORDEN_SUGERIDO_ADULTO` como referencia.

## Contrato de las claves de `onboarding_answers`

Las cinco `onboarding_key` de este módulo son EXACTAMENTE las que lee
`app/services/career_gap_service.py` y escribe `app/api/v1/career_gap.py`
(sus propios endpoints `PUT /me/career-gap/*`, para quien completa esto sin
pasar por el chat). Si el chat las escribe con estas mismas claves —vía
`a_onboarding_answers()`, que ya usa `onboarding_key` sin más lógica—, el
análisis de brecha funciona sin importar por cuál de los dos caminos llegó el
dato. Es la misma garantía que ya tiene `budget` con `user.budget_band`: una
sola fuente de verdad, dos formas de escribirla.

**No se guarda el perfil de LinkedIn ya estructurado bajo un `onboarding_key`**
(sólo el texto crudo, `career_linkedin_profile_text`). El texto puede llegar
por el chat sin que nadie lo haya procesado todavía; procesarlo es trabajo de
`career_gap_service`, que lo cachea bajo su propia clave interna
(`career_linkedin_profile`) la primera vez que hace falta — así el chat no
necesita saber nada de IA de estructuración, y no se gasta una llamada a Claude
por cada turno de la conversación mientras la persona sigue pegando texto.
"""
from __future__ import annotations

from typing import Dict, Tuple

from app.data.perfilador_typeform import Hecho

# Import perezoso a propósito: `onboarding_hechos` es de otro agente y este
# módulo debe poder importarse (para tests, para el router de career_gap) aun
# si esas dos constantes cambian de nombre allá. Sólo se usan como VALOR del
# diccionario que se le entrega a quien enganche esto.
PERFIL_PROFESIONAL = "profesional"


HECHOS_ADULTO: list[Hecho] = [
    Hecho(
        id="career_linkedin_profile_text",
        pregunta_typeform="Pega el texto de tu perfil de LinkedIn (o cópialo del "
                           "PDF que exporta LinkedIn desde 'Recursos → Guardar como PDF').",
        bloque="profesional",
        tipo="texto",
        onboarding_key="career_linkedin_profile_text",
        obligatorio=True,
        nota="Sin esto no hay perfil con qué comparar el puesto ideal. Se "
             "estructura con `linkedin_import_service` (ya existente) desde "
             "`career_gap_service`, no en el momento de la conversación.",
    ),
    Hecho(
        id="career_current_role",
        pregunta_typeform="¿Cuál es tu cargo o rol actual?",
        bloque="profesional",
        tipo="texto",
        onboarding_key="career_current_role",
    ),
    Hecho(
        id="career_job_satisfaction_score",
        pregunta_typeform="En una escala de 1 a 5, ¿qué tan satisfecho estás "
                           "con tu trabajo actual?",
        bloque="profesional",
        tipo="entero",
        onboarding_key="career_job_satisfaction_score",
        obligatorio=True,
        nota="Rango 1-5. Es la mitad de la auditoría de trayectoria pedida "
             "('historial laboral y satisfacción actual').",
    ),
    Hecho(
        id="career_job_satisfaction_text",
        pregunta_typeform="Cuéntame por qué calificaste así tu satisfacción actual.",
        bloque="profesional",
        tipo="texto",
        onboarding_key="career_job_satisfaction_text",
    ),
    Hecho(
        id="career_target_role",
        pregunta_typeform="¿Cuál es tu puesto ideal? Por ejemplo: "
                           "'Data Analyst remoto en una fintech'.",
        bloque="profesional",
        tipo="texto",
        onboarding_key="career_target_role",
        obligatorio=True,
        nota="El otro lado de la comparación del análisis de brecha: sin esto "
             "`career_gap_service` no tiene contra qué comparar el perfil.",
    ),
]

_POR_ID = {h.id: h for h in HECHOS_ADULTO}

# Los tres que el análisis de brecha necesita sí o sí. Se entregan como tupla
# de ids (no como el `OBLIGATORIOS` global) para que quien engancha decida
# cómo combinarlos — ver docstring del módulo.
OBLIGATORIOS_ADULTO_IDS: Tuple[str, ...] = (
    "career_linkedin_profile_text",
    "career_job_satisfaction_score",
    "career_target_role",
)

# Listo para `SOLO_PERFIL.update(...)` en onboarding_hechos.py.
SOLO_PERFIL_ADULTO: Dict[str, tuple] = {
    h.id: (PERFIL_PROFESIONAL,) for h in HECHOS_ADULTO
}

# Listo para `QUE_AVERIGUAR.update(...)` — mismo estilo que el resto del
# catálogo: qué hay que saber, no cómo preguntarlo literalmente.
QUE_AVERIGUAR_ADULTO: Dict[str, str] = {
    "career_linkedin_profile_text": "que pegue el texto de su perfil de "
        "LinkedIn (o lo copie del PDF que exporta LinkedIn) · es la base de "
        "todo el análisis de brecha, no se puede avanzar sin esto",
    "career_current_role": "cuál es su cargo o rol actual",
    "career_job_satisfaction_score": "qué tan satisfecho está HOY con su "
        "trabajo, en una escala de 1 (nada) a 5 (totalmente)",
    "career_job_satisfaction_text": "por qué se siente así con su trabajo "
        "actual, en sus palabras",
    "career_target_role": "cuál es su 'puesto ideal' — el cargo al que le "
        "gustaría llegar, con el detalle que él mismo le dé (ej. remoto, "
        "sector, seniority)",
}

# Sugerencia de orden · NO se aplica sola, es referencia para quien mantiene
# `ORDEN_CONVERSACION`. Va después de lo vocacional (voice_*) y antes de la
# logística del colegio, que a un profesional no le aplica.
ORDEN_SUGERIDO_ADULTO = [
    "career_current_role",
    "career_job_satisfaction_score",
    "career_job_satisfaction_text",
    "career_target_role",
    "career_linkedin_profile_text",
]


def get_hecho(hecho_id: str):
    return _POR_ID.get(hecho_id)
