"""Big Five (OCEAN) · versión con lenguaje de 14-16 años (grados 9° y 10°).

Por qué existe
--------------
En la malla de 10° (lineamiento de la clienta, Sprint 4) el Big Five va en
"lenguaje juvenil", igual que Holland en 9° (ver ``holland_junior.py``). El
banco canónico está escrito para adultos: *"Soy el alma de las fiestas"*,
*"Me interesan las ideas abstractas"*, *"Sigo mis planes rigurosamente"*. Un
chico de 10° los contesta adivinando qué le quisieron preguntar. JP decidió
(2026-11-02) que el criterio de lenguaje juvenil lo ponemos nosotros, sin
esperar a la clienta.

La línea que este archivo NO cruza
----------------------------------
La misma de Holland: se adapta la REDACCIÓN, nunca la ESTRUCTURA. Ítem por
ítem se conserva:
  * el MISMO ``id`` (``bf-o-1`` … ``bf-n-10``) → mismo scoring, mismo resultado
    guardado, misma lectura y mismo PDF;
  * la MISMA ``category`` (O/C/E/A/N) y 10 ítems por dimensión (50 en total);
  * el MISMO ``reversed``: un ítem invertido sigue diciendo lo contrario de su
    dimensión. Esto es lo delicado de este test (Holland no tiene invertidos):
    si "Dejo mis cosas tiradas" se reescribiera en positivo, la responsabilidad
    de un chico ordenado bajaría en vez de subir. El test
    ``tests/test_bigfive_junior_grado_9_10.py`` lo protege.

Cada ítem lleva en comentario el enunciado ADULTO que reemplaza. De paso, el
banco adulto tiene tildes que faltan ("comodo", "presion"); aquí van bien.

Quién lo recibe
---------------
Los mismos que Holland juvenil: grados 9° y 10° (``vocational_bank_selector``).
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.data.holland_junior import VARIANT_JUNIOR
from app.data.vocational_tests import get_test_by_id

BIGFIVE_JUNIOR_QUESTIONS: List[Dict[str, Any]] = [
    # ---------------- O · Apertura (curiosidad, imaginación) ----------------
    # orig: "Tengo una imaginación muy activa"
    {"id": "bf-o-1", "text": "Me imagino historias, mundos o inventos con facilidad, hasta en medio de una clase", "type": "likert", "category": "O"},
    # orig: "Me interesan las ideas abstractas"
    {"id": "bf-o-2", "text": "Me engancho pensando en preguntas raras, como qué es el tiempo o de dónde salió el universo", "type": "likert", "category": "O"},
    # orig: "Disfruto experimentar cosas nuevas"
    {"id": "bf-o-3", "text": "Me gusta probar cosas nuevas: comidas, planes o música que no conozco", "type": "likert", "category": "O"},
    # orig: "Me gusta reflexionar sobre temas filosóficos"
    {"id": "bf-o-4", "text": "Me pongo a pensar en preguntas grandes, como qué es lo justo o para qué estamos aquí", "type": "likert", "category": "O"},
    # orig: "Aprecio el arte y la belleza"
    {"id": "bf-o-5", "text": "Una canción, un dibujo o un paisaje bonito me pueden dejar mirándolos un buen rato", "type": "likert", "category": "O"},
    # orig: "Prefiero la variedad sobre la rutina"
    {"id": "bf-o-6", "text": "Prefiero que cada día sea un poco distinto a hacer siempre lo mismo", "type": "likert", "category": "O"},
    # orig: "Tengo un vocabulario amplio"
    {"id": "bf-o-7", "text": "Me gusta aprender palabras nuevas y usarlas cuando hablo o escribo", "type": "likert", "category": "O"},
    # orig: "Me gusta aprender sobre diferentes culturas"
    {"id": "bf-o-8", "text": "Me da curiosidad cómo viven, qué comen y qué celebran en otros países", "type": "likert", "category": "O"},
    # orig: "Tengo dificultad entendiendo ideas abstractas" (invertido)
    {"id": "bf-o-9", "text": "Me cuesta seguir una explicación muy teórica si no me dan un ejemplo", "type": "likert", "category": "O", "reversed": True},
    # orig: "No me interesa el arte" (invertido)
    {"id": "bf-o-10", "text": "El arte, como museos, pintura o teatro, no me dice mucho", "type": "likert", "category": "O", "reversed": True},

    # ---------------- C · Responsabilidad (orden, constancia) ----------------
    # orig: "Siempre estoy preparado/a"
    {"id": "bf-c-1", "text": "Llego a clase con lo que necesito: la tarea hecha y los materiales listos", "type": "likert", "category": "C"},
    # orig: "Presto atención a los detalles"
    {"id": "bf-c-2", "text": "Reviso mis trabajos antes de entregarlos para que no tengan errores", "type": "likert", "category": "C"},
    # orig: "Hago mis tareas inmediatamente"
    {"id": "bf-c-3", "text": "Hago las tareas apenas me las dejan, no las dejo para después", "type": "likert", "category": "C"},
    # orig: "Me gusta el orden"
    {"id": "bf-c-4", "text": "Me gusta tener mi cuarto y mis cosas en orden", "type": "likert", "category": "C"},
    # orig: "Sigo mis planes rigurosamente"
    {"id": "bf-c-5", "text": "Cuando me organizo para algo, cumplo lo que me propuse", "type": "likert", "category": "C"},
    # orig: "Trabajo duro para lograr mis metas"
    {"id": "bf-c-6", "text": "Le meto esfuerzo a lo que me propongo, aunque me cueste", "type": "likert", "category": "C"},
    # orig: "Dejo mis cosas tiradas" (invertido)
    {"id": "bf-c-7", "text": "Dejo mis cosas tiradas por cualquier lado", "type": "likert", "category": "C", "reversed": True},
    # orig: "A menudo olvido poner las cosas en su lugar" (invertido)
    {"id": "bf-c-8", "text": "Se me pierden las cosas: el cargador, los audífonos, el cuaderno", "type": "likert", "category": "C", "reversed": True},
    # orig: "Postergo las tareas importantes" (invertido)
    {"id": "bf-c-9", "text": "Dejo lo importante para el último momento", "type": "likert", "category": "C", "reversed": True},
    # orig: "Me cuesta seguir horarios" (invertido)
    {"id": "bf-c-10", "text": "Me cuesta cumplir horarios, como llegar a tiempo o estudiar a la hora que dije", "type": "likert", "category": "C", "reversed": True},

    # ---------------- E · Extraversión (energía con la gente) ----------------
    # orig: "Soy el alma de las fiestas"
    {"id": "bf-e-1", "text": "En un plan con amigos, suelo ser quien anima a todos", "type": "likert", "category": "E"},
    # orig: "Me siento cómodo con la gente"
    {"id": "bf-e-2", "text": "Me siento cómodo con la gente, aunque no la conozca mucho", "type": "likert", "category": "E"},
    # orig: "Inicio conversaciones fácilmente"
    {"id": "bf-e-3", "text": "Me es fácil empezar a hablar con alguien nuevo", "type": "likert", "category": "E"},
    # orig: "Hablo con muchas personas diferentes en fiestas"
    {"id": "bf-e-4", "text": "En una fiesta o un paseo termino hablando con muchas personas distintas", "type": "likert", "category": "E"},
    # orig: "No me molesta ser el centro de atención"
    {"id": "bf-e-5", "text": "No me molesta que todos me miren, por ejemplo al exponer en clase", "type": "likert", "category": "E"},
    # orig: "Tengo poco que decir" (invertido)
    {"id": "bf-e-6", "text": "En grupo casi nunca tengo mucho que decir", "type": "likert", "category": "E", "reversed": True},
    # orig: "Me mantengo en segundo plano" (invertido)
    {"id": "bf-e-7", "text": "Prefiero quedarme en segundo plano", "type": "likert", "category": "E", "reversed": True},
    # orig: "No hablo mucho" (invertido)
    {"id": "bf-e-8", "text": "Hablo poco, incluso con mis compañeros de clase", "type": "likert", "category": "E", "reversed": True},
    # orig: "No me gusta llamar la atención" (invertido)
    {"id": "bf-e-9", "text": "No me gusta llamar la atención", "type": "likert", "category": "E", "reversed": True},
    # orig: "Me siento incómodo en grupos grandes" (invertido)
    {"id": "bf-e-10", "text": "Me siento incómodo en grupos muy grandes", "type": "likert", "category": "E", "reversed": True},

    # ---------------- A · Amabilidad (cómo trato a los demás) ----------------
    # orig: "Me intereso por los demás"
    {"id": "bf-a-1", "text": "Me interesa saber cómo están mis amigos y mi familia", "type": "likert", "category": "A"},
    # orig: "Siento empatía por los sentimientos de otros"
    {"id": "bf-a-2", "text": "Si un amigo está triste, yo también lo siento", "type": "likert", "category": "A"},
    # orig: "Tengo un corazón blando"
    {"id": "bf-a-3", "text": "Me conmuevo fácil, por ejemplo con una película o una historia triste", "type": "likert", "category": "A"},
    # orig: "Me tomo tiempo para los demás"
    {"id": "bf-a-4", "text": "Saco tiempo para ayudar a otros, aunque esté ocupado", "type": "likert", "category": "A"},
    # orig: "Hago sentir bien a los demás"
    {"id": "bf-a-5", "text": "Me gusta hacer sentir bien a los demás", "type": "likert", "category": "A"},
    # orig: "No me interesan mucho los problemas de otros" (invertido)
    {"id": "bf-a-6", "text": "Los problemas de los demás no me interesan mucho", "type": "likert", "category": "A", "reversed": True},
    # orig: "Insulto a la gente" (invertido)
    {"id": "bf-a-7", "text": "Cuando me enojo, digo cosas que lastiman a otros", "type": "likert", "category": "A", "reversed": True},
    # orig: "No me interesan los sentimientos ajenos" (invertido)
    {"id": "bf-a-8", "text": "No me fijo mucho en cómo se sienten los demás", "type": "likert", "category": "A", "reversed": True},
    # orig: "Soy duro/a en mis opiniones sobre los demás" (invertido)
    {"id": "bf-a-9", "text": "Soy duro cuando opino sobre otras personas", "type": "likert", "category": "A", "reversed": True},
    # orig: "Critico frecuentemente a los demás" (invertido)
    {"id": "bf-a-10", "text": "Critico mucho a los demás", "type": "likert", "category": "A", "reversed": True},

    # ---------------- N · Estabilidad emocional (cómo me afectan las cosas) --
    # Ojo con el tono: son preguntas sobre cómo se siente un chico de 15. Van
    # concretas y sin dramatizar; ninguna nombra un trastorno.
    # orig: "Me estreso fácilmente"
    {"id": "bf-n-1", "text": "Me estreso fácil, por ejemplo antes de un examen", "type": "likert", "category": "N"},
    # orig: "Me preocupo por las cosas"
    {"id": "bf-n-2", "text": "Me quedo dándole vueltas a las cosas que me preocupan", "type": "likert", "category": "N"},
    # orig: "Me perturbo fácilmente"
    {"id": "bf-n-3", "text": "Las cosas me afectan mucho y me cuesta sacármelas de la cabeza", "type": "likert", "category": "N"},
    # orig: "Mis emociones cambian frecuentemente"
    {"id": "bf-n-4", "text": "Mi estado de ánimo cambia mucho en un mismo día", "type": "likert", "category": "N"},
    # orig: "Me siento ansioso/a a menudo"
    {"id": "bf-n-5", "text": "Seguido me siento nervioso o inquieto sin saber bien por qué", "type": "likert", "category": "N"},
    # orig: "Estoy relajado/a la mayor parte del tiempo" (invertido)
    {"id": "bf-n-6", "text": "La mayor parte del tiempo estoy tranquilo", "type": "likert", "category": "N", "reversed": True},
    # orig: "Rara vez me siento triste" (invertido)
    {"id": "bf-n-7", "text": "Casi nunca me siento triste", "type": "likert", "category": "N", "reversed": True},
    # orig: "Manejo bien la presión" (invertido)
    {"id": "bf-n-8", "text": "Manejo bien la presión, como un examen difícil o un partido importante", "type": "likert", "category": "N", "reversed": True},
    # orig: "Mantengo la calma en situaciones difíciles" (invertido)
    {"id": "bf-n-9", "text": "Mantengo la calma cuando algo sale mal", "type": "likert", "category": "N", "reversed": True},
    # orig: "Me recupero rápidamente de las dificultades" (invertido)
    {"id": "bf-n-10", "text": "Cuando algo no me sale bien, me recupero rápido", "type": "likert", "category": "N", "reversed": True},
]


BIGFIVE_JUNIOR_DESCRIPTION = (
    "El mismo test de personalidad Big Five, con las preguntas escritas para tu edad. "
    "Mide cinco rasgos: qué tan curioso eres, qué tan organizado, cuánta energía te da "
    "la gente, cómo tratas a los demás y cómo te afectan las cosas."
)


def get_bigfive_junior() -> Dict[str, Any]:
    """Big Five con la redacción de 9°/10°.

    Igual que ``get_holland_junior``: los metadatos se heredan del banco
    canónico en tiempo de ejecución y el ``id`` sigue siendo "bigfive", para que
    el resultado, el scoring, la lectura y el PDF sean los del mismo instrumento.
    """
    base = get_test_by_id("bigfive")
    if base is None:  # pragma: no cover - el banco canónico siempre está
        raise RuntimeError("El banco Big Five canónico no está disponible")

    junior = dict(base)
    junior["questions"] = [dict(q) for q in BIGFIVE_JUNIOR_QUESTIONS]
    junior["description"] = BIGFIVE_JUNIOR_DESCRIPTION
    junior["variant"] = VARIANT_JUNIOR
    return junior
