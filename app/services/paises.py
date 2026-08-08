"""Países del catálogo · el primer filtro que ve el estudiante.

El catálogo original escribe el país en dos idiomas mezclados —`UK`, `Spain` y
`Canada` conviven con `Suiza`, `Polonia` y `Chipre`— porque las fichas se
cargaron en momentos distintos. Para una pantalla de selección eso son dos
entradas para el mismo sitio.

Aquí se unifica a español, que es el idioma del producto (decisión del POC: sin
i18n, target Colombia).
"""
from __future__ import annotations

import re
import unicodedata

# Cuando una institución opera en varios países y el programa no dice en cuál,
# **no se le inventa uno**. Aparece marcado así y el filtro por país lo trata
# aparte: prometerle Canadá a alguien porque la red "también está en Canadá" es
# el mismo error que vender un campus que no existe.
VARIOS = "Varios destinos"

CANONICO = {
    "australia": "Australia",
    "uk": "Reino Unido",
    "united kingdom": "Reino Unido",
    "inglaterra": "Reino Unido",
    "reino unido": "Reino Unido",
    "canada": "Canadá",
    "usa": "Estados Unidos",
    "united states": "Estados Unidos",
    "estados unidos": "Estados Unidos",
    "spain": "España",
    "espana": "España",
    "italy": "Italia",
    "italia": "Italia",
    "france": "Francia",
    "francia": "Francia",
    "germany": "Alemania",
    "alemania": "Alemania",
    "new zealand": "Nueva Zelanda",
    "nueva zelanda": "Nueva Zelanda",
    "ireland": "Irlanda",
    "irlanda": "Irlanda",
    "malta": "Malta",
    "suiza": "Suiza",
    "switzerland": "Suiza",
    "polonia": "Polonia",
    "poland": "Polonia",
    "austria": "Austria",
    "republica checa": "República Checa",
    "czech republic": "República Checa",
    "uae": "Emiratos Árabes Unidos",
    "emiratos": "Emiratos Árabes Unidos",
    "emiratos arabes unidos": "Emiratos Árabes Unidos",
    "paises bajos": "Países Bajos",
    "netherlands": "Países Bajos",
    "holanda": "Países Bajos",
    # Cyprus West University está en la República Turca del Norte de Chipre, no
    # en la Chipre de la UE. El nombre se deja como lo dice la ficha y la
    # advertencia vive en FICHAS_A_CORREGIR.md · aquí no se disimula fusionándolo
    # con Chipre a secas.
    "chipre": "Chipre",
    "cyprus": "Chipre",
    # Cyprus West University está aquí, no en la Chipre de la UE · acreditación
    # turca YÖK/YÖDAK, sin reconocimiento automático europeo. Se distingue a
    # propósito: venderlo como "Chipre" es lo que revienta en el consulado.
    "republica turca del norte de chipre": "República Turca del Norte de Chipre",
    "northern cyprus": "República Turca del Norte de Chipre",
    "belgica": "Bélgica",
    "belgium": "Bélgica",
    "international": VARIOS,
    "varios": VARIOS,
    VARIOS.lower(): VARIOS,
}

PAISES = sorted({v for v in CANONICO.values() if v != VARIOS})


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def normalizar(pais: str) -> str | None:
    """Lleva un país del catálogo al nombre canónico, o None si no lo reconoce."""
    return CANONICO.get(_norm(pais)) or None
