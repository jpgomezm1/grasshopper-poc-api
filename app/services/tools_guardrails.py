"""Guardarraíles de texto compartidos por las tres mini apps de "Herramientas".

Las tres mini apps (Statement of Purpose · copy para postularse a un trabajo ·
hoja de vida por país) tienen el mismo riesgo: el modelo escribe **prosa larga**
en primera persona, y la prosa larga es donde se cuelan los datos inventados.
No es hipotético — ya hubo un reclamo del cliente por contenido inventado por
nosotros, y por eso `career_gap_service` nació con una red de seguridad.

Este módulo es esa red, extraída para que las tres la compartan. Tres piezas:

1. :func:`redactar_cifras` · escanea el texto y **sustituye** cualquier cifra
   con forma de dinero o de porcentaje por un marcador. No intenta distinguir
   una cifra real de una inventada: no hay forma de saberlo desde aquí, así que
   la postura es la más segura.
2. :func:`marcadores` · recoge todo lo que quedó entre ``[corchetes]`` en el
   texto final y lo devuelve como lista. Esto **cierra el circuito** con lo
   anterior: la cifra que se redactó no desaparece en silencio dentro de un
   párrafo, sale también en la lista de "esto lo tienes que completar tú", que
   es lo que la pantalla le muestra a la persona.
3. Los recortes de siempre (`texto`, `lista_texto`, `parrafos`) · el tool use
   garantiza la FORMA, nunca el TAMAÑO.

Las expresiones regulares se **importan** de `career_gap_service` en vez de
copiarse. Es a propósito: dos copias de la misma regex es garantía de que en
seis meses una se actualice y la otra no, y la que se quede vieja va a ser
justo la que deje pasar el "$8.500.000 al mes" a la pantalla de alguien.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

# Ver docstring · se reusan, no se duplican.
from app.services.career_gap_service import _RE_DINERO, _RE_PORCENTAJE

#: Lo que queda en lugar de una cifra que el modelo no tenía cómo saber. Va
#: entre corchetes a propósito: así :func:`marcadores` lo recoge y termina en
#: la lista de pendientes de la persona.
MARCADOR_CIFRA = "[completa aquí el dato exacto]"

# Un marcador es cualquier cosa entre corchetes que el modelo (o la redacción
# de cifras) haya dejado. Se acota el tamaño para no capturar un párrafo entero
# si el modelo abre un corchete y no lo cierra hasta tres líneas después.
_RE_MARCADOR = re.compile(r"\[([^\[\]]{2,160})\]")


def redactar_cifras(valor: Optional[str]) -> Optional[str]:
    """Sustituye cifras de dinero y porcentajes por :data:`MARCADOR_CIFRA`.

    A diferencia de `career_gap_service._redactar_cifras`, que deja un
    "[cifra no disponible]" —correcto para un informe—, aquí el reemplazo es
    una **instrucción para quien escribe**: estos textos los va a editar la
    persona antes de mandarlos, así que el hueco tiene que decirle qué hacer.
    """
    if not valor:
        return valor
    limpio = _RE_DINERO.sub(MARCADOR_CIFRA, valor)
    limpio = _RE_PORCENTAJE.sub(MARCADOR_CIFRA, limpio)
    return limpio


def marcadores(textos: Iterable[str]) -> List[str]:
    """Todo lo que quedó entre corchetes, sin repetir y en orden de aparición.

    Es la mitad que hace útil a :func:`redactar_cifras`: sin esto, la cifra
    redactada sería un hueco raro en medio de un párrafo que la persona podría
    no ver antes de enviarlo.
    """
    vistos: List[str] = []
    for bloque in textos:
        if not bloque:
            continue
        for encontrado in _RE_MARCADOR.findall(bloque):
            limpio = encontrado.strip()
            if limpio and limpio not in vistos:
                vistos.append(limpio)
    return vistos[:15]


def contar_palabras(texto_completo: Optional[str]) -> int:
    """Cuenta las palabras en Python, nunca preguntándoselo al modelo.

    Los límites de palabras de una convocatoria son duros ("máximo 500") y un
    modelo contando sus propias palabras se equivoca con soltura. Que el número
    lo calcule Python es la diferencia entre un dato y una estimación.
    """
    return len((texto_completo or "").split())


def texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio[:limite] if limpio else None


def lista_texto(valor: Any, max_items: int, limite: int) -> List[str]:
    if not isinstance(valor, list):
        return []
    salida: List[str] = []
    for item in valor:
        t = texto(item, limite)
        if t:
            salida.append(t)
    return salida[:max_items]


def parrafos(valor: Any, *, max_parrafos: int, max_chars: int) -> List[str]:
    """Normaliza la lista de párrafos que devolvió el modelo.

    Acepta que llegue un único string con saltos de línea: un modelo al que le
    pides una lista de párrafos a veces devuelve el ensayo entero en el primer
    elemento, y perder el texto por eso sería absurdo.
    """
    if isinstance(valor, str):
        crudos: List[Any] = [p for p in valor.split("\n\n")]
    elif isinstance(valor, list):
        crudos = []
        for item in valor:
            item_texto = texto(item, max_chars * 4) or ""
            crudos.extend(item_texto.split("\n\n"))
    else:
        return []

    salida: List[str] = []
    for bruto in crudos:
        limpio = texto(bruto, max_chars)
        if limpio:
            salida.append(limpio)
    return salida[:max_parrafos]
