"""El simulador de entrevista de admisión · E-4 (entregable de 12° del demo), Sprint 4.

El demo de Verónica pide para 12° un simulador de admisiones con "entrevista
con IA". Aquí Hopper hace de entrevistador: cinco preguntas, una a la vez, y al
final una devolución concreta de cada respuesta.

## Qué hace la IA y qué no

- **Las preguntas NO las escribe la IA.** Salen del banco de abajo: son las que
  casi cualquier comité de admisiones hace, y así no hay preguntas raras ni
  costo por empezar. Tres son fijas (presentarse, por qué ese programa, por qué
  esa universidad), una rota entre siete, para que practicar dos veces no sea
  lo mismo, y la última es el cierre ("¿tienes alguna pregunta?"). El texto
  lo arma siempre el servidor desde el id: el front solo devuelve ids y
  respuestas.
- **La IA solo da la devolución**, con el perfil que ya tenemos de la persona
  (la misma `describir_cv` de la hoja de vida y la carta): puede decirle "esto
  que hiciste no lo contaste y te sirve". No inventa nada sobre la
  universidad.
- **Nunca pone nota ni puntaje.** Una calificación inventada por un modelo
  parecería un veredicto del comité, y no lo es. La devolución es lo que
  funcionó y lo que puede mejorar.
- **Si una respuesta deja ver malestar emocional**, la IA lo marca
  (`requiere_acompanamiento`) y responde con calidez, sin diagnosticar; la
  pantalla sugiere hablar con una persona. Mismo criterio que el chat de
  Hopper (`app/prompts/hop_chat.txt`, regla 4). El detector clínico no se toca
  desde aquí (ver el CLAUDE.md del backend).

## Qué NO hace

No persiste nada, por la misma razón que la carta de motivación
(`sop_service`): respuestas libres de un menor sin política de retención.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from app.services import tools_guardrails as guard


class EntrevistaError(RuntimeError):
    """No se pudo dar la devolución."""


IDIOMAS = ("es", "en")
IDIOMA_POR_DEFECTO = "es"
MAX_UNIVERSIDAD = 160
MAX_PROGRAMA = 160
MAX_RESPUESTA = 2000
PREGUNTAS_POR_ENTREVISTA = 5

AVISO = (
    "Es una práctica, no una evaluación del comité. Cada universidad entrevista "
    "a su manera; lo que más ayuda es practicar en voz alta, con tus palabras."
)

# (id, español, inglés). {programa} y {universidad} se rellenan si los dio.
_FIJAS = (
    ("presentacion", "Cuéntame un poco de ti.", "Tell me a little about yourself."),
    (
        "programa",
        "¿Por qué quieres estudiar {programa}?",
        "Why do you want to study {programa}?",
    ),
    (
        "universidad",
        "¿Por qué elegiste {universidad}?",
        "Why did you choose {universidad}?",
    ),
)
_SIN_PROGRAMA = ("¿Qué quieres estudiar y por qué?", "What do you want to study, and why?")
_SIN_UNIVERSIDAD = (
    "¿Qué buscas en la universidad donde vas a estudiar?",
    "What are you looking for in a university?",
)
_ROTAN = (
    (
        "reto",
        "Háblame de un reto que hayas enfrentado y de cómo lo resolviste.",
        "Tell me about a challenge you faced and how you dealt with it.",
    ),
    (
        "fortaleza",
        "¿Cuál dirías que es tu mayor fortaleza? Dame un ejemplo.",
        "What would you say is your greatest strength? Give me an example.",
    ),
    (
        "mejorar",
        "¿Qué es algo que estás tratando de mejorar de ti?",
        "What is something about yourself you are trying to improve?",
    ),
    (
        "equipo",
        "Cuéntame de una vez en que trabajaste en equipo. ¿Qué papel tuviste?",
        "Tell me about a time you worked in a team. What was your role?",
    ),
    (
        "aporte",
        "¿Qué aportarías a tus compañeros de clase?",
        "What would you bring to your classmates?",
    ),
    (
        "futuro",
        "¿Dónde te ves cuando termines la carrera?",
        "Where do you see yourself when you finish your degree?",
    ),
    (
        "curiosidad",
        "¿Qué tema te ha dado curiosidad últimamente, fuera del colegio?",
        "What topic has caught your curiosity recently, outside of school?",
    ),
)
_CIERRE = (
    "cierre",
    "Para terminar: ¿tienes alguna pregunta para nosotros?",
    "To finish: do you have any questions for us?",
)

TODAS = {p[0] for p in (*_FIJAS, *_ROTAN, _CIERRE)}


def normalizar_idioma(idioma: Optional[str]) -> str:
    return idioma if idioma in IDIOMAS else IDIOMA_POR_DEFECTO


def preguntas(
    *,
    idioma: str = IDIOMA_POR_DEFECTO,
    universidad: Optional[str] = None,
    programa: Optional[str] = None,
    azar: Optional[random.Random] = None,
) -> List[Dict[str, str]]:
    """Las cinco preguntas: tres fijas, una que rota y el cierre."""
    idioma = normalizar_idioma(idioma)
    universidad = (universidad or "").strip()[:MAX_UNIVERSIDAD]
    programa = (programa or "").strip()[:MAX_PROGRAMA]
    azar = azar or random.Random()

    rota = azar.choice(_ROTAN)[0]
    ids = [f[0] for f in _FIJAS] + [rota, _CIERRE[0]]
    fuera = [{"id": pid, "texto": _texto_de(pid, idioma, universidad, programa)} for pid in ids]
    assert len(fuera) == PREGUNTAS_POR_ENTREVISTA
    return fuera


ESQUEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "respuestas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pregunta_id": {"type": "string"},
                    "lo_que_funciono": {"type": "string"},
                    "que_mejorar": {"type": "string"},
                    "idea_para_mejorarla": {"type": "string"},
                },
                "required": ["pregunta_id", "lo_que_funciono", "que_mejorar"],
            },
        },
        "fortalezas": {"type": "array", "items": {"type": "string"}},
        "a_trabajar": {"type": "array", "items": {"type": "string"}},
        "siguiente_paso": {"type": "string"},
        "requiere_acompanamiento": {"type": "boolean"},
    },
    "required": ["respuestas", "fortalezas", "a_trabajar", "siguiente_paso", "requiere_acompanamiento"],
}

SIN_RESPUESTA = (
    "No respondiste esta pregunta. En una entrevista real conviene decir algo, "
    "aunque sea corto: piensa qué contarías y practícalo en voz alta."
)


def _texto_de(pid: str, idioma: str, universidad: str, programa: str) -> str:
    """El texto de una pregunta por su id · lo arma el servidor, no lo manda el front."""
    i = 1 if idioma == "es" else 2
    if pid == "programa":
        return _FIJAS[1][i].format(programa=programa) if programa else _SIN_PROGRAMA[i - 1]
    if pid == "universidad":
        return _FIJAS[2][i].format(universidad=universidad) if universidad else _SIN_UNIVERSIDAD[i - 1]
    for p in (*_FIJAS, *_ROTAN, _CIERRE):
        if p[0] == pid:
            return p[i]
    raise KeyError(pid)


def _limpias(
    respuestas: List[Dict[str, str]], idioma: str, universidad: str, programa: str,
) -> List[Dict[str, str]]:
    fuera = []
    vistos = set()
    for r in respuestas:
        pid = r.get("pregunta_id")
        if pid not in TODAS or pid in vistos:
            continue
        vistos.add(pid)
        fuera.append({
            "pregunta_id": pid,
            "pregunta": _texto_de(pid, idioma, universidad, programa),
            "respuesta": (r.get("respuesta") or "").strip()[:MAX_RESPUESTA],
        })
    return fuera


def normalizar(bruto: Dict[str, Any], respondidas: List[Dict[str, str]]) -> Dict[str, Any]:
    """Una devolución por pregunta, en el orden en que se hicieron.

    Lo que el modelo devuelva para una pregunta que no se hizo se descarta; a
    una que no respondió se le pone el texto fijo, sin pasar por el modelo.
    """
    por_id = {}
    for r in bruto.get("respuestas") or []:
        if isinstance(r, dict) and r.get("pregunta_id") not in por_id:
            por_id[r.get("pregunta_id")] = r
    devoluciones = []
    for r in respondidas:
        if not r["respuesta"]:
            devoluciones.append({
                "pregunta_id": r["pregunta_id"], "pregunta": r["pregunta"], "respondida": False,
                "lo_que_funciono": None, "que_mejorar": SIN_RESPUESTA, "idea_para_mejorarla": None,
            })
            continue
        d = por_id.get(r["pregunta_id"]) or {}
        devoluciones.append({
            "pregunta_id": r["pregunta_id"],
            "pregunta": r["pregunta"],
            "respondida": True,
            "lo_que_funciono": guard.texto(d.get("lo_que_funciono"), 700),
            "que_mejorar": guard.texto(d.get("que_mejorar"), 700),
            "idea_para_mejorarla": guard.texto(d.get("idea_para_mejorarla"), 700),
        })
    return {
        "devoluciones": devoluciones,
        "fortalezas": guard.lista_texto(bruto.get("fortalezas"), 4, 300),
        "a_trabajar": guard.lista_texto(bruto.get("a_trabajar"), 4, 300),
        "siguiente_paso": guard.texto(bruto.get("siguiente_paso"), 400),
        "requiere_acompanamiento": bool(bruto.get("requiere_acompanamiento")),
        "aviso": AVISO,
    }


def devolucion(
    *,
    respuestas: List[Dict[str, str]],
    idioma: str,
    universidad: Optional[str],
    programa: Optional[str],
    perfil: str,
    session_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """La devolución de la entrevista. Devuelve ``(devolucion, metadata_de_ia)``.

    Valida ANTES de gastar la llamada: si no respondió nada, no hay qué revisar.
    """
    idioma = normalizar_idioma(idioma)
    universidad = (universidad or "").strip()[:MAX_UNIVERSIDAD]
    programa = (programa or "").strip()[:MAX_PROGRAMA]
    respondidas = _limpias(respuestas, idioma, universidad, programa)
    con_texto = [r for r in respondidas if r["respuesta"]]
    if not con_texto:
        raise EntrevistaError("Responde al menos una pregunta para que Hopper te dé su devolución.")

    from app.core.ai_client import call_claude_tool, load_prompt

    transcripcion = "\n\n".join(
        f"[{r['pregunta_id']}] Pregunta: {r['pregunta']}\nRespuesta: {r['respuesta']}" for r in con_texto
    )
    prompt = load_prompt("entrevista_admision").format(
        idioma="inglés" if idioma == "en" else "español",
        destino=f"{programa or '(programa sin definir)'} en {universidad or '(universidad sin definir)'}",
        perfil=perfil,
        transcripcion=transcripcion,
    )
    datos, meta = call_claude_tool(
        prompt,
        tool_name="dar_devolucion_de_entrevista",
        tool_description=(
            "Da una devolución concreta y amable de cada respuesta de una "
            "entrevista de admisión de práctica, sin calificar."
        ),
        input_schema=ESQUEMA,
        session_id=session_id,
        feature="entrevista_admision",
        max_tokens=3000,
        temperature=0.3,
    )
    if not datos:
        raise EntrevistaError("Hopper no pudo revisar tu entrevista en este momento. Intenta de nuevo en un rato.")
    return normalizar(datos, respondidas), meta
