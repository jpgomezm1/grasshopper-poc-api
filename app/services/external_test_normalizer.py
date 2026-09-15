"""Normalizador de tests externos · payload del parser → `scores` canónico.

Por qué existe
--------------
Un test resuelto DENTRO de la plataforma guarda en `VocationalTestResult.scores`
un diccionario de dimensión → número 0-100, con las claves cortas que usa el
frontend: ``{"R": 80, "I": 65, ...}`` para iStrong/Holland, ``{"EI": 72, ...}``
para MBTI, ``{"O": 64, ...}`` para Big Five.

Un test SUBIDO en PDF guardaba, hasta ahora, el payload crudo del parser tal
cual: ``{"holland_code": "EC", "realistic": null, "top_basic_interests": [...]}``.
Otro vocabulario, y con valores que no son números: strings y listas.

Todo el frontend fue escrito contra la primera forma. Al recibir la segunda hacía
``Math.round("ISTP")`` y pintaba ``type_code — NaN%`` en el snapshot, en el PDF que
el asesor le entrega a la familia y en el panel lateral del journey; y
``holland_top_codes()`` devolvía lista vacía, así que el test subido no contaba ni
para el perfil consolidado ni para las recomendaciones ni para la fila de videos.

Este módulo traduce en UN solo punto —al confirmar la subida— y establece el
contrato: en la raíz de `scores` van los valores que la UI puede graficar (números,
más el código/tipo que es el titular del test); todo lo demás vive bajo `_meta`.

Sobre inventar números
----------------------
Los reportes oficiales del cliente (iStartStrong, MBTI Career Report) **no publican
puntajes numéricos**: publican un orden de preferencia y un índice de claridad. No
los convertimos en porcentajes. Un 90% inventado a partir de un ranking termina
impreso como si fuera un puntaje real del Strong del estudiante.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Claves canónicas que ya entiende el frontend (`profileUtils.getVocationalDimensionLabel`).
_GOT_A_LETRA = {
    "realistic": "R",
    "investigative": "I",
    "artistic": "A",
    "social": "S",
    "enterprising": "E",
    "conventional": "C",
}

_MBTI_SCORE_A_PAR = {
    "e_score": "EI",
    "s_score": "SN",
    "t_score": "TF",
    "j_score": "JP",
}

_MBTI_PCI_A_PAR = {
    "pci_ei": "EI",
    "pci_sn": "SN",
    "pci_tf": "TF",
    "pci_jp": "JP",
}

_BIG5_A_LETRA = {
    "openness": "O",
    "conscientiousness": "C",
    "extraversion": "E",
    "agreeableness": "A",
    "neuroticism": "N",
}


def _num(v: Any) -> Optional[float]:
    """El valor como float, o None si no es un número utilizable."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if f == f else None  # descarta NaN


def _lista(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if x is not None and str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def normalizar_scores(test_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce el payload del parser a la forma canónica de `scores`.

    Idempotente: un payload que ya pasó por aquí (trae `_meta`) se devuelve igual,
    porque el usuario puede editar y reconfirmar la misma subida.
    """
    if not isinstance(payload, dict):
        return {}
    if "_meta" in payload:
        return payload

    consumidas: set[str] = set()
    scores: Dict[str, Any] = {}

    if test_type in ("istrong", "riasec"):
        for campo, letra in _GOT_A_LETRA.items():
            consumidas.add(campo)
            n = _num(payload.get(campo))
            if n is not None:
                scores[letra] = n
        codigo = payload.get("holland_code")
        consumidas.add("holland_code")
        if isinstance(codigo, str) and codigo.strip():
            scores["holland_code"] = codigo.strip().upper()

    elif test_type == "mbti":
        for campo, par in _MBTI_SCORE_A_PAR.items():
            consumidas.add(campo)
            n = _num(payload.get(campo))
            if n is not None:
                scores[par] = n
        tipo = payload.get("type_code")
        consumidas.add("type_code")
        if isinstance(tipo, str) and tipo.strip():
            scores["type_code"] = tipo.strip().upper()

    elif test_type == "big5":
        for campo, letra in _BIG5_A_LETRA.items():
            consumidas.add(campo)
            n = _num(payload.get(campo))
            if n is not None:
                scores[letra] = n

    tiene_numeros = any(isinstance(v, (int, float)) for v in scores.values())

    meta: Dict[str, Any] = {
        "source": "external_upload",
        "test_type": test_type,
        "has_numeric_scores": tiene_numeros,
    }

    if test_type in ("istrong", "riasec"):
        ranking = payload.get("theme_ranking")
        consumidas.add("theme_ranking")
        if isinstance(ranking, list) and ranking:
            meta["theme_ranking"] = [str(x).strip().upper()[:1] for x in ranking]
        for campo in ("top_basic_interests", "suggested_careers"):
            consumidas.add(campo)
            items = _lista(payload.get(campo))
            if items:
                meta[campo] = items

    elif test_type == "mbti":
        pci = {}
        for campo, par in _MBTI_PCI_A_PAR.items():
            consumidas.add(campo)
            n = _num(payload.get(campo))
            if n is not None:
                pci[par] = n
        if pci:
            meta["pci"] = pci
        consumidas.add("identity")
        identidad = payload.get("identity")
        if isinstance(identidad, str) and identidad.strip():
            meta["identity"] = identidad.strip().upper()
        for campo in ("strengths", "suggested_careers"):
            consumidas.add(campo)
            items = _lista(payload.get(campo))
            if items:
                meta[campo] = items

    elif test_type == "big5":
        consumidas.add("interpretation_summary")
        resumen = payload.get("interpretation_summary")
        if isinstance(resumen, str) and resumen.strip():
            meta["interpretation_summary"] = resumen.strip()

    # Nada se pierde: lo que el parser haya traído y aquí no se reconozca queda
    # guardado en vez de descartado en silencio · pero fuera de la raíz, donde la
    # UI lo intentaría graficar.
    extras = {k: v for k, v in payload.items() if k not in consumidas}
    if extras:
        meta["extras"] = extras

    scores["_meta"] = meta
    return scores
