"""Tres programas reales para cerrar la brecha · E-5, Sprint 4.

El demo de Verónica, en el paquete Profesional ("Reinvención y upskilling"):
"hoja de ruta (microcredencial, idioma, maestría, certificación) con 3 programas
específicos". El análisis de brecha (`career_gap_service`) ya arma el plan de
upskilling, pero **a propósito no nombra programas**: su prompt le prohíbe a la
IA inventar uno que no sepa que existe. Los programas concretos salen de aquí,
del catálogo real, con la misma búsqueda semántica que usa `/busqueda`.

## Uno por concepto

Se busca por separado:
  1. el puesto al que quiere llegar, y
  2. hasta dos brechas de impacto alto o medio,
y se toma el mejor programa de cada búsqueda que no se haya elegido ya. Así
cada programa dice para qué se sugiere ("Para: SQL avanzado"), que es lo que
convierte una lista en una hoja de ruta. Promediar los conceptos en un solo
vector no se parece bien a ninguno (medido en `buscar_con_texto`).

## Lo que no hace

- No llama a un modelo de lenguaje: solo vectores del proveedor de embeddings.
- No abre el filtro duro: la etapa de vida decide qué niveles son elegibles,
  igual que en la búsqueda normal.
- Si el proveedor de vectores falla, devuelve lista vacía y la pantalla lo
  dice. No rellena con programas al azar.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CUANTOS = 3
CLAVE_CACHE = "career_gap_programas"
# Cuántos candidatos se piden por concepto · margen para saltarse repetidos.
VENTANA = 8
_IMPACTOS = ("alto", "medio")


def conceptos(analisis: Dict[str, Any], puesto_ideal: Optional[str]) -> List[str]:
    """El puesto ideal y hasta dos brechas importantes, en ese orden."""
    salida: List[str] = []
    if isinstance(puesto_ideal, str) and puesto_ideal.strip():
        salida.append(puesto_ideal.strip())
    brechas = analisis.get("brechas") or []
    # Primero las de impacto alto, luego las de medio · el orden de la IA dentro
    # de cada nivel se respeta.
    for impacto in _IMPACTOS:
        for b in brechas:
            if len(salida) >= CUANTOS:
                break
            area = (b or {}).get("area")
            if (b or {}).get("impacto") == impacto and isinstance(area, str) and area.strip():
                if area.strip() not in salida:
                    salida.append(area.strip())
    return salida[:CUANTOS]


def _vector(texto: str) -> Optional[List[float]]:
    """El vector de un concepto, desde código síncrono · None si no se puede."""
    from app.services import embeddings as emb

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:  # pragma: no cover · mismo criterio que `vector_del_perfil_sync`
        return None
    try:
        return asyncio.run(emb.embeber_uno(texto))
    except Exception:
        logger.warning("no se pudo embeber el concepto de la brecha", exc_info=True)
        return None


def elegir(db: Any, user: Any) -> Optional[Dict[str, Any]]:
    """Los programas, o None si todavía no hay análisis de brecha."""
    from app.services import busqueda_programas as bp

    respuestas = user.onboarding_answers or {}
    analisis = respuestas.get("career_gap_analysis")
    if not analisis:
        return None

    # Recorridos Sprint 4 · en producción tardaba ~17 s (tres vectores y tres
    # búsquedas) cada vez que abría el inicio. Se guarda junto al análisis del
    # que salió: si el análisis cambia (otra fecha), se recalcula.
    generado = respuestas.get("career_gap_analysis_generated_at")
    guardado = respuestas.get(CLAVE_CACHE)
    if isinstance(guardado, dict) and generado and guardado.get("para_analisis") == generado:
        return guardado.get("datos")

    lista_conceptos = conceptos(analisis, respuestas.get("career_target_role"))
    perfil = bp.perfil_del_usuario(db, user)
    filtros = bp.Filtros(etapa_de_vida=perfil.etapa_de_vida)

    por_concepto: List[tuple] = []
    for concepto in lista_conceptos:
        vector = _vector(concepto)
        if vector is None:
            continue
        candidatos = bp.buscar(
            db, vector_perfil=vector, codigos_riasec=perfil.codigos_riasec,
            filtros=filtros, limite=VENTANA,
        )
        por_concepto.append((concepto, list(candidatos)))

    elegidos: List[Dict[str, Any]] = []
    vistos: set = set()

    def tomar(concepto: str, candidatos: List[Any]) -> None:
        for c in candidatos:
            if c.id in vistos:
                continue
            vistos.add(c.id)
            elegidos.append({
                "id": c.id,
                "nombre": c.nombre,
                "institucion": c.institucion,
                "pais": c.pais,
                "ciudad": c.ciudad,
                "nivel": c.nivel,
                "duracion": c.duracion,
                "url_fuente": c.url_fuente,
                "program_id": c.program_id,
                "oferta_slug": getattr(c, "oferta_slug", None),
                "confianza": c.confianza,
                "para": concepto,
            })
            return

    # Primera pasada: el mejor de cada concepto. Segunda: si hubo menos de tres
    # conceptos (o se repitieron programas), se completa en el mismo orden.
    for concepto, candidatos in por_concepto:
        tomar(concepto, candidatos)
    while len(elegidos) < CUANTOS:
        antes = len(elegidos)
        for concepto, candidatos in por_concepto:
            if len(elegidos) >= CUANTOS:
                break
            tomar(concepto, candidatos)
        if len(elegidos) == antes:
            break  # no quedan candidatos nuevos

    datos = {
        "target_role": respuestas.get("career_target_role"),
        "conceptos": lista_conceptos,
        "programas": elegidos,
    }
    # Solo se guarda un resultado con programas: una lista vacía puede ser un
    # proveedor caído, y guardarla dejaría a la persona sin programas para siempre.
    if elegidos and generado and db is not None and hasattr(user, "id"):
        user.onboarding_answers = {
            **respuestas, CLAVE_CACHE: {"para_analisis": generado, "datos": datos},
        }
        db.commit()
    return datos
