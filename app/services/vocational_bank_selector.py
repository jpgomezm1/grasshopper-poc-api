"""Qué banco de preguntas ve cada estudiante (adulto vs. 9°/10°).

Hoy sólo Holland tiene dos redacciones (ver ``app/data/holland_junior.py``).
Este módulo concentra la decisión de cuál se sirve, para que el endpoint no
tenga reglas de producto adentro y para que el día que otro test se adapte se
cambie en un solo lugar.

Regla de producto
-----------------
Grados **9° y 10° → banco junior**. Grados 11°, 12° y adultos (perfil
profesional) → banco adulto, que es el que ya existía. Ante la duda, adulto:
prefiero que un chico de 10° vea el test de siempre a que un adulto reciba
preguntas escritas para un niño de 13.

De dónde sale el grado (en este orden)
--------------------------------------
1. ``user.grade`` — la columna tipada de la migración 067 (Cimientos malla
   completa). Es la fuente de verdad.
2. ``user.onboarding_answers["grade"]`` — el espejo en JSON que escribe el chat
   de onboarding. Se lee también porque la columna se pobló después: usuarios
   que respondieron el grado antes de que existiera la columna sólo lo tienen
   aquí, y porque es el mismo campo que ya leen ``cv_pdf_service`` y
   ``dossier_service``.
3. ``life_stage`` — el código ``high_school_early`` es, por definición de la
   propia pregunta del onboarding, *"En el colegio (9° o 10°)"*. Sirve de red
   para los estudiantes que ya están en producción y nunca dijeron el grado
   exacto; sin este paso el banco junior no le llegaría a nadie hasta que todos
   rehagan el onboarding.

Nota deliberada: NO se deriva el grado de la edad. Un chico de 14 puede estar en
8° o en 10° y la fecha de nacimiento no distingue; el grado lo dice el
estudiante.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.data.holland_junior import (
    VARIANT_ADULTO,
    VARIANT_JUNIOR,
    get_holland_junior,
)
from app.data.onboarding_hechos import RUTA_GRADO_9, RUTA_GRADO_10, RUTA_POR_GRADO
from app.data.vocational_tests import get_all_tests_summary, get_test_by_id
from app.services import academic_level

# El único test que hoy tiene dos redacciones.
TEST_CON_VARIANTES = "holland"

# Los grados que reciben la redacción de 13-14 años · derivados de
# `onboarding_hechos.RUTA_POR_GRADO` (la tabla canónica de las 5 rutas de la
# malla, Cimientos migración 067) y NO de una tupla propia — antes este
# módulo tenía su propio `(9, 10)` hardcodeado, una segunda fuente de verdad
# para "qué grados son junior" que podía desincronizarse de la malla si
# alguna vez cambia (ver el error tipo A que este repo ya se cobró cuatro
# veces: dos sitios decidiendo lo mismo).
GRADOS_JUNIOR = tuple(
    int(grado) for grado, ruta in RUTA_POR_GRADO.items()
    if ruta in (RUTA_GRADO_9, RUTA_GRADO_10)
)

# El grado escrito con palabras aparece en respuestas libres del chat
# ("estoy en noveno"). Sólo se mapea lo que existe en el dominio de la malla.
_GRADO_EN_PALABRAS = {
    "noveno": 9,
    "decimo": 10,
    "once": 11,
    "onceavo": 11,
    "undecimo": 11,
    "doce": 12,
    "duodecimo": 12,
}


def _sin_tildes(texto: str) -> str:
    reemplazos = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
    return texto.translate(reemplazos)


def _a_grado(valor: Any) -> Optional[int]:
    """Normaliza a entero 9-12 lo que venga (int, "11", "11°", "noveno")."""
    if isinstance(valor, bool):  # bool es int en Python; no es un grado
        return None
    if isinstance(valor, int):
        return valor if valor in (9, 10, 11, 12) else None
    if not isinstance(valor, str):
        return None

    limpio = _sin_tildes(valor.strip().lower())
    if not limpio:
        return None

    numeros = re.findall(r"\d+", limpio)
    if numeros:
        try:
            n = int(numeros[0])
        except ValueError:
            return None
        return n if n in (9, 10, 11, 12) else None

    for palabra, grado in _GRADO_EN_PALABRAS.items():
        if palabra in limpio:
            return grado
    return None


def grado_del_estudiante(user: Any) -> Optional[int]:
    """Grado 9-12 del estudiante, o None si no está en colegio / no se sabe."""
    # getattr defensivo: por aquí pasan también objetos de prueba y usuarios
    # cargados con `load_only` que no traen la columna.
    directo = _a_grado(getattr(user, "grade", None))
    if directo is not None:
        return directo

    respuestas = getattr(user, "onboarding_answers", None) or {}
    if isinstance(respuestas, dict):
        for clave in ("grade", "grado", "currentGrade"):
            desde_json = _a_grado(respuestas.get(clave))
            if desde_json is not None:
                return desde_json
    return None


def _esta_en_colegio_temprano(user: Any) -> bool:
    """¿La etapa declarada dice 9°/10° aunque no haya grado exacto?"""
    respuestas = getattr(user, "onboarding_answers", None) or {}
    if not isinstance(respuestas, dict):
        return False
    etapa = respuestas.get("life_stage") or respuestas.get("lifeStage")
    # Se reusa la normalización de `academic_level` porque la etapa llega con
    # dos vocabularios (códigos del onboarding y textos del journey) y no vale
    # la pena tener una segunda traducción que se desincronice.
    return academic_level.normalizar_etapa(etapa) == academic_level.EN_COLEGIO


def variante_para(user: Any) -> str:
    """"junior" (9°/10°) o "adulto" (11°, 12°, profesional o desconocido)."""
    grado = grado_del_estudiante(user)
    if grado is not None:
        return VARIANT_JUNIOR if grado in GRADOS_JUNIOR else VARIANT_ADULTO
    # Sin grado exacto: `high_school_early` ya significa 9° o 10°.
    return VARIANT_JUNIOR if _esta_en_colegio_temprano(user) else VARIANT_ADULTO


def test_para_usuario(test_id: str, user: Any) -> Optional[Dict[str, Any]]:
    """El test completo con la redacción que le corresponde a ESTE estudiante.

    Devuelve None con el mismo criterio que ``get_test_by_id`` para que el
    endpoint siga respondiendo 404 igual que antes.
    """
    if test_id != TEST_CON_VARIANTES:
        return get_test_by_id(test_id)

    if variante_para(user) == VARIANT_JUNIOR:
        return get_holland_junior()

    # El banco adulto se marca explícito para que el front no tenga que
    # adivinar: `variant` siempre viene en Holland, nunca falta.
    adulto = get_test_by_id(TEST_CON_VARIANTES)
    if adulto is None:  # pragma: no cover - el banco canónico siempre está
        return None
    marcado = dict(adulto)
    marcado["variant"] = VARIANT_ADULTO
    return marcado


def resumen_tests_para_usuario(user: Any) -> List[Dict[str, Any]]:
    """Lista de tests con la descripción de Holland que le toca al estudiante.

    La descripción es lo primero que se lee en la pantalla de tests: si ahí
    quedara el texto adulto y adentro las preguntas fueran las de 9°, la
    incoherencia se vería antes de empezar.
    """
    variante = variante_para(user)
    junior = get_holland_junior() if variante == VARIANT_JUNIOR else None

    # Malla completa · además de la redacción, el catálogo depende del grado:
    # hay instrumentos que pertenecen a una sola ruta y declaran `gradeRoutes`
    # (hoy el Mapeo de Habilidades Blandas, sólo grado 10). `get_all_tests_summary`
    # los filtra. Ojo con la asimetría deliberada: aquí se usa el grado EXACTO,
    # no `variante_para`, porque un estudiante que sólo declaró la etapa
    # `high_school_early` puede estar en 9° o en 10° y no hay forma de saberlo —
    # en ese caso se prefiere no ofrecer el test de la ruta de 10° a ofrecérselo
    # a alguien de 9°.
    resumen = []
    for item in get_all_tests_summary(grade=grado_del_estudiante(user)):
        if item["id"] != TEST_CON_VARIANTES:
            resumen.append(item)
            continue
        entrada = dict(item)
        entrada["variant"] = variante
        if junior is not None:
            entrada["description"] = junior["description"]
        resumen.append(entrada)
    return resumen
