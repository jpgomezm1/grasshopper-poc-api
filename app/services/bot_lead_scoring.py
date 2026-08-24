"""Scoring y enrutamiento del lead del perfilador · determinista, no IA.

El Typeform que este bot reemplaza ya trae `score`, `variable_abc` y `ending`:
la agencia **ya enruta hoy**. Esto reproduce esa decisión con pesos explícitos.

**Por qué determinista.** Un score comercial tiene que ser auditable y estable —
el equipo va a discutir por qué un lead cayó en telemercadeo, y "lo dijo el
modelo" no es una respuesta. El proyecto ya tiene el patrón en
`student_lead_scoring.py` (pesos explícitos + rationale por plantilla) y de ahí
se reusa el bandeo, para que "hot" signifique lo mismo en los dos sitios.

Las alarmas salen de las palabras textuales de Verónica en la reunión del 21-07:

    "le pregunto qué presupuesto piensas invertir en tu proyecto, no, mil
     dólares → de una que ha muerto"  ·  "si me negaron visa de EEUU e
     Inglaterra, eso me prende una alarma"                          (12:03)

⚠️ **Los pesos son nuestros, no suyos.** El export del Typeform trae los nombres
de las columnas (`score`, `variable_abc`) pero no la fórmula. Esto es una
primera versión para llevarle a validar — no se conecta a Bitrix antes de que
ella la vea.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.services.student_lead_scoring import _band as banda_por_score

# --- Pesos · suman 100 en el caso ideal --------------------------------------
PESO_PRESUPUESTO = 30      # el filtro comercial más fuerte
PESO_FECHA = 20            # qué tan cerca está de viajar
PESO_DESTINO = 15          # si quiere un destino que la agencia representa
PESO_PASAPORTE = 15        # sin pasaporte el proceso no arranca
PESO_INTENCION = 10        # sabe qué tipo de programa quiere
PESO_IDIOMA = 10           # nivel declarado suficiente

# --- Penalizaciones ----------------------------------------------------------
# La visa negada no descarta sola: la agencia igual quiere hablar con esa
# persona, pero el asesor tiene que saberlo antes de la llamada.
PENALIZACION_VISA_NEGADA = 25

UMBRAL_ASESOR = 70         # mismo corte que `hot` en student_lead_scoring
UMBRAL_TELEMERCADEO = 40   # mismo corte que `warm`

PRESUPUESTOS_VIABLES = {"5k_15k", "15k_30k", "over_30k"}
FECHAS_CERCANAS = {"asap", "6_months"}

# Los destinos que la agencia representa, en el vocabulario del catálogo.
DESTINOS_REPRESENTADOS = {"usa", "canada", "spain", "uk", "germany", "australia"}


@dataclass
class Veredicto:
    score: int
    banda: str            # hot · warm · cold
    ruta: str             # asesor · telemercadeo · descartar
    alarmas: List[str] = field(default_factory=list)
    motivos: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "banda": self.banda,
            "ruta": self.ruta,
            "alarmas": self.alarmas,
            "motivos": self.motivos,
        }


def evaluar(recolectados: Dict[str, Any]) -> Veredicto:
    """Puntúa el lead y decide a quién va.

    Cada punto que suma o resta deja su motivo en `motivos`, para que el equipo
    comercial pueda discutir el criterio en vez de discutir el número.
    """
    score = 0
    alarmas: List[str] = []
    motivos: List[str] = []

    # --- Presupuesto · la alarma que ella nombró primero ----------------------
    inversion = recolectados.get("inversion")
    if inversion in PRESUPUESTOS_VIABLES:
        score += PESO_PRESUPUESTO
        motivos.append(f"+{PESO_PRESUPUESTO} presupuesto en rango vendible")
    elif inversion == "under_5k":
        alarmas.append("Presupuesto por debajo de lo que cuesta cualquier programa")
        motivos.append("+0 presupuesto no alcanza")
    elif inversion == "unknown":
        motivos.append("+0 todavía no sabe cuánto puede invertir")

    # --- Cuándo quiere viajar ------------------------------------------------
    cuando = recolectados.get("cuando_viajar")
    if cuando in FECHAS_CERCANAS:
        score += PESO_FECHA
        motivos.append(f"+{PESO_FECHA} quiere viajar pronto")
    elif cuando == "1_year":
        score += PESO_FECHA // 2
        motivos.append(f"+{PESO_FECHA // 2} viaja dentro de un año")
    elif cuando == "exploring":
        motivos.append("+0 solo está explorando")

    # --- Destino -------------------------------------------------------------
    destinos = recolectados.get("destino_interes") or []
    if isinstance(destinos, list) and set(destinos) & DESTINOS_REPRESENTADOS:
        score += PESO_DESTINO
        motivos.append(f"+{PESO_DESTINO} quiere un destino que representamos")
    elif destinos:
        motivos.append("+0 su destino no está entre los que representamos")

    # --- Pasaporte -----------------------------------------------------------
    pasaporte = recolectados.get("pasaporte")
    if pasaporte == "yes":
        score += PESO_PASAPORTE
        motivos.append(f"+{PESO_PASAPORTE} pasaporte vigente")
    elif pasaporte == "in_progress":
        score += PESO_PASAPORTE // 2
        motivos.append(f"+{PESO_PASAPORTE // 2} pasaporte en trámite")
    elif pasaporte == "no":
        alarmas.append("No tiene pasaporte · el proceso no puede arrancar")
        motivos.append("+0 sin pasaporte")

    # --- Intención -----------------------------------------------------------
    if recolectados.get("tipo_experiencia"):
        score += PESO_INTENCION
        motivos.append(f"+{PESO_INTENCION} sabe qué tipo de programa busca")

    # --- Idioma --------------------------------------------------------------
    nivel = recolectados.get("nivel_ingles")
    if nivel in {"intermedio", "avanzado", "nativo"}:
        score += PESO_IDIOMA
        motivos.append(f"+{PESO_IDIOMA} nivel de inglés declarado suficiente")
    elif nivel in {"basico", "ninguno"}:
        motivos.append("+0 necesitaría curso de idioma primero")

    # --- Visa negada · penalización, no descarte -----------------------------
    if recolectados.get("visa_usa_negada") is True:
        score -= PENALIZACION_VISA_NEGADA
        alarmas.append("Le negaron la visa americana · el asesor debe saberlo antes de llamar")
        motivos.append(f"-{PENALIZACION_VISA_NEGADA} visa americana negada")
    elif recolectados.get("visa_usa_vigente") is True:
        motivos.append("nota: tiene visa americana vigente")

    score = max(0, min(100, score))
    banda = banda_por_score(score)

    # --- Ruta ----------------------------------------------------------------
    # El presupuesto inviable manda por encima del score: es la frase textual de
    # Verónica ("de una que ha muerto"), no un promedio ponderado.
    if inversion == "under_5k":
        ruta = "descartar"
    elif score >= UMBRAL_ASESOR:
        ruta = "asesor"
    elif score >= UMBRAL_TELEMERCADEO:
        ruta = "telemercadeo"
    else:
        ruta = "descartar"

    return Veredicto(score=score, banda=banda, ruta=ruta, alarmas=alarmas, motivos=motivos)


def quiere_orientacion(recolectados: Dict[str, Any]) -> bool:
    """True si esta persona es de Mentoring, no de la agencia.

    Es la bifurcación del negocio que Verónica explicó en la reunión (18:34):
    quien busca "orientación vocacional o comprender mis habilidades" no es un
    lead de estudios en el exterior — es la "miga de pan" hacia la plataforma
    pagada. El bot no lo resuelve; lo deriva.
    """
    return recolectados.get("tipo_experiencia") == "orientacion"
