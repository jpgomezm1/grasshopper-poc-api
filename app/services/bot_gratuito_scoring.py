"""Puntaje y ruta del prospecto del bot gratuito · determinista, no IA (B-5, Sprint 4).

Son las reglas EXACTAS del demo de Verónica (`leadScore()` y `routeOf()` en
`Hopper · Bot gratuito y perfilamiento (demo v2).html`): cuatro factores de 0 a
2 puntos, total sobre 8.

| Factor      | 2                           | 1                    | 0                |
|-------------|-----------------------------|----------------------|------------------|
| Etapa       | 11°, 12° o profesional      | 10°                  | 9°               |
| Cuándo      | este mes o en 1-3 meses     | en 3-12 meses        | más adelante     |
| Presupuesto | 10-25k o más de 25k al año  | hasta 10k o beca     | no lo han hablado|
| Destino     | exterior o comparar         | país de origen       | no sabe          |

≥ 6 caliente → agenda de counsellors · 3-5 tibio → oferta de perfilamiento
pago · < 3 frío → telemarketing.

## A diferencia del bot conversacional (`bot_lead_scoring.py`)

Aquellos pesos eran nuestros y esperaban validación; estos son de ella. Los dos
escriben en las mismas columnas de `bot_conversations` para que la bandeja los
muestre juntos, así que el puntaje se guarda en la MISMA escala (0-100): el de
8 se convierte, y el valor original queda en el desglose. Las bandas usan las
mismas palabras (`hot` · `warm` · `cold`).

La ruta del tibio es nueva: `perfilamiento` (ofrecerle el perfilamiento pago),
que el conversacional no tiene.

## Nunca se le muestra al usuario

Es para el equipo. En el demo la etiqueta "LEAD CALIENTE" y el puntaje se veían
en pantalla, pero eso era una ayuda de la demo, no parte del producto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

MAXIMO = 8
UMBRAL_CALIENTE = 6
UMBRAL_TIBIO = 3

# El "tramo" se deriva igual que en el front (`tramoDe` en `src/lib/botGratuito.ts`):
# quien ya se graduó del colegio cuenta como 12°; universidad y trabajo, como profesional.
_ETAPA = {"9": 0, "10": 1, "11": 2, "12": 2, "grad": 2}
_CUANDO = {"now": 2, "soon": 2, "year": 1, "later": 0}
_PRESUPUESTO = {"b2": 2, "b3": 2, "b1": 1, "beca": 1, "nose": 0}
_DESTINO = {"ext": 2, "both": 2, "local": 1, "nose": 0}

_NOMBRE_ETAPA = {"9": "9°", "10": "10°", "11": "11°", "12": "12°", "grad": "ya se graduó del colegio"}
_NOMBRE_CUANDO = {"now": "este mes", "soon": "en 1 a 3 meses", "year": "en 3 a 12 meses", "later": "más adelante"}
_NOMBRE_PRESUPUESTO = {
    "b1": "hasta USD 10.000 al año",
    "b2": "entre USD 10.000 y 25.000 al año",
    "b3": "más de USD 25.000 al año",
    "beca": "depende de una beca o un crédito",
    "nose": "no lo han hablado",
}
_NOMBRE_DESTINO = {
    "ext": "en el exterior",
    "both": "quiere comparar país de origen y exterior",
    "local": "en el país de origen",
    "nose": "aún no sabe dónde",
}


@dataclass
class Veredicto:
    puntos: int                      # 0-8 · la escala del demo
    score: int                       # 0-100 · la escala de la bandeja
    banda: str                       # hot · warm · cold
    ruta: str                        # asesor · perfilamiento · telemercadeo
    motivos: List[str] = field(default_factory=list)


def _puntos_etapa(stage: str) -> int:
    if stage in _ETAPA:
        return _ETAPA[stage]
    # u1-u4 (universidad) y p1-p3 (experiencia laboral) = profesional.
    return 2


def _nombre_etapa(stage: str) -> str:
    if stage in _NOMBRE_ETAPA:
        return _NOMBRE_ETAPA[stage]
    return "universitario" if stage.startswith("u") else "profesional"


def puntuar(respuestas: Dict[str, str], cuando: str) -> Veredicto:
    stage = respuestas.get("stage", "")
    presupuesto = respuestas.get("budget", "")
    destino = respuestas.get("dest", "")

    factores = [
        (_puntos_etapa(stage), f"etapa: {_nombre_etapa(stage)}"),
        (_CUANDO.get(cuando, 0), f"quiere iniciar {_NOMBRE_CUANDO.get(cuando, '(sin dato)')}"),
        (_PRESUPUESTO.get(presupuesto, 0), f"presupuesto: {_NOMBRE_PRESUPUESTO.get(presupuesto, '(sin dato)')}"),
        (_DESTINO.get(destino, 0), f"destino: {_NOMBRE_DESTINO.get(destino, '(sin dato)')}"),
    ]
    puntos = sum(p for p, _ in factores)

    if puntos >= UMBRAL_CALIENTE:
        banda, ruta = "hot", "asesor"
    elif puntos >= UMBRAL_TIBIO:
        banda, ruta = "warm", "perfilamiento"
    else:
        banda, ruta = "cold", "telemercadeo"

    motivos = [f"+{p} {texto}" for p, texto in factores]
    motivos.append(f"total {puntos} de {MAXIMO} (reglas del demo de Verónica)")
    return Veredicto(
        puntos=puntos,
        score=round(puntos * 100 / MAXIMO),
        banda=banda,
        ruta=ruta,
        motivos=motivos,
    )
