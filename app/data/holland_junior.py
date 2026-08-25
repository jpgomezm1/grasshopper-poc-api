"""Holland RIASEC · versión con lenguaje de 13-14 años (grados 9° y 10°).

Por qué existe
--------------
Feedback literal de la clienta: *"el test que tenemos de Holland lo siento con
preguntas muy de adultos, es posible gamificar este test a un lenguaje más de
jóvenes de 13 o 14 años?"*. Tiene razón: enunciados como *"Prefiero ambientes de
trabajo creativos y no convencionales"* le piden a un chico de 9° que se imagine
una oficina que nunca ha pisado.

La línea que este archivo NO cruza
----------------------------------
RIASEC es un marco público y su REDACCIÓN se puede adaptar; su ESTRUCTURA no.
Si se cambia cuántos ítems mide cada dimensión o cómo puntúan, deja de ser
Holland y pasa a ser un cuestionario propio con nombre prestado — que es
exactamente el reclamo que ya recibimos por el test de inglés (20 preguntas
inventadas por nosotros presentadas como instrumento).

Por eso este banco conserva, ítem por ítem:
  * el MISMO ``id`` (``h-r-1`` … ``h-c-8``) → las respuestas que manda el front y
    el scoring de ``calculate_vocational_scores("holland", answers)`` son
    idénticos;
  * la MISMA ``category`` (R/I/A/S/E/C) y 8 ítems por dimensión (48 en total);
  * el MISMO ``type`` ("likert" 1-5, sin ítems invertidos).

Lo único que cambia es el ``text``. ``tests/test_holland_junior_grado_9_10.py``
verifica esa paridad y falla si alguien rompe la equivalencia.

Cada ítem lleva en comentario el enunciado ADULTO original que reemplaza, para
que la correspondencia 1-a-1 se pueda auditar sin abrir los dos archivos al
tiempo.

Quién lo recibe
---------------
Grados 9° y 10° (ver ``app/services/vocational_bank_selector.py``). Grados 11°,
12° y adultos siguen viendo el banco original de ``vocational_tests.py``.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.data.vocational_tests import get_test_by_id

# Marca que viaja en la respuesta del API para que el front (y QA, y soporte)
# sepan QUÉ redacción vio el estudiante. No se persiste: los puntajes son los
# mismos en las dos versiones, así que no hay nada nuevo que guardar — pero sin
# esta marca no habría forma de reproducir lo que el estudiante leyó.
VARIANT_JUNIOR = "junior"
VARIANT_ADULTO = "adulto"


# --- Banco adaptado · 48 ítems, 8 por dimensión ------------------------------
HOLLAND_JUNIOR_QUESTIONS: List[Dict[str, Any]] = [
    # ---------------- R · Realista (manos, cosas, movimiento) ----------------
    # orig: "Me gusta trabajar con herramientas y maquinaria"
    {"id": "h-r-1", "text": "Me gusta usar herramientas: un destornillador, un taladro, lo que sirva para armar algo", "type": "likert", "category": "R"},
    # orig: "Prefiero actividades al aire libre"
    {"id": "h-r-2", "text": "Prefiero estar afuera, al aire libre, que encerrado en un salón", "type": "likert", "category": "R"},
    # orig: "Disfruto reparar cosas con mis manos"
    {"id": "h-r-3", "text": "Cuando algo se daña en mi casa, me dan ganas de abrirlo y arreglarlo yo", "type": "likert", "category": "R"},
    # orig: "Me gusta trabajar con plantas o animales"
    {"id": "h-r-4", "text": "Me gusta cuidar animales o plantas", "type": "likert", "category": "R"},
    # orig: "Prefiero actividades físicas sobre trabajos de escritorio"
    {"id": "h-r-5", "text": "Prefiero moverme y hacer algo con el cuerpo antes que quedarme sentado en un escritorio", "type": "likert", "category": "R"},
    # orig: "Me gusta construir o armar cosas"
    {"id": "h-r-6", "text": "Me gusta armar cosas: Lego, un mueble, una bici, un computador", "type": "likert", "category": "R"},
    # orig: "Disfruto operar vehiculos o maquinaria pesada"
    {"id": "h-r-7", "text": "Me llama la atención manejar máquinas grandes: un carro, una moto, un tractor", "type": "likert", "category": "R"},
    # orig: "Me siento comodo trabajando con materiales como madera, metal o tela"
    {"id": "h-r-8", "text": "Me gusta trabajar con materiales de verdad: cortar madera, doblar metal, coser tela", "type": "likert", "category": "R"},

    # ---------------- I · Investigador (entender, resolver, probar) ----------
    # orig: "Me gusta analizar problemas complejos"
    {"id": "h-i-1", "text": "Cuando un problema está difícil, me dan más ganas de resolverlo que de dejarlo", "type": "likert", "category": "I"},
    # orig: "Disfruto leer sobre temas cientificos"
    {"id": "h-i-2", "text": "Me quedo enganchado viendo o leyendo cosas de ciencia, del espacio o de animales raros", "type": "likert", "category": "I"},
    # orig: "Prefiero entender el por que de las cosas"
    {"id": "h-i-3", "text": "Siempre pregunto por qué las cosas funcionan como funcionan", "type": "likert", "category": "I"},
    # orig: "Me gusta resolver rompecabezas y acertijos"
    {"id": "h-i-4", "text": "Me gustan los acertijos, los juegos de lógica y los niveles de videojuego que toca pensar", "type": "likert", "category": "I"},
    # orig: "Disfruto investigar temas a profundidad"
    {"id": "h-i-5", "text": "Cuando un tema me interesa, busco y busco hasta saberlo todo", "type": "likert", "category": "I"},
    # orig: "Me interesan las matematicas y la logica"
    {"id": "h-i-6", "text": "Las matemáticas y los retos de lógica me parecen entretenidos", "type": "likert", "category": "I"},
    # orig: "Prefiero trabajar con datos y hechos"
    {"id": "h-i-7", "text": "Antes de opinar me gusta mirar los números y los datos: las estadísticas del equipo, del juego", "type": "likert", "category": "I"},
    # orig: "Me gusta experimentar y probar hipotesis"
    {"id": "h-i-8", "text": "Me gusta hacer experimentos y probar qué pasa si cambio algo", "type": "likert", "category": "I"},

    # ---------------- A · Artístico (crear, imaginar, expresar) --------------
    # orig: "Tengo una imaginacion muy activa"
    {"id": "h-a-1", "text": "Me imagino historias, mundos o personajes todo el tiempo", "type": "likert", "category": "A"},
    # orig: "Me gusta expresarme a traves del arte o la musica"
    {"id": "h-a-2", "text": "Dibujo, canto, bailo o toco algo cuando quiero sacar lo que siento", "type": "likert", "category": "A"},
    # orig: "Prefiero trabajar sin reglas estrictas"
    {"id": "h-a-3", "text": "Me va mejor cuando me dejan hacer las cosas a mi manera y no con tantas reglas", "type": "likert", "category": "A"},
    # orig: "Disfruto crear cosas nuevas y originales"
    {"id": "h-a-4", "text": "Me gusta crear cosas que a nadie más se le habían ocurrido", "type": "likert", "category": "A"},
    # orig: "Me gusta la escritura creativa o la poesia"
    {"id": "h-a-5", "text": "Escribo cuentos, canciones o textos porque quiero, no porque me los pidan", "type": "likert", "category": "A"},
    # orig: "Aprecio la belleza estetica en mi entorno"
    {"id": "h-a-6", "text": "Me fijo en que las cosas se vean bien: mi cuarto, mis fotos, mis cuadernos", "type": "likert", "category": "A"},
    # orig: "Me gusta el diseno grafico o la fotografia"
    {"id": "h-a-7", "text": "Disfruto tomar fotos, editar videos o diseñar cosas en el celular", "type": "likert", "category": "A"},
    # orig: "Prefiero ambientes de trabajo creativos y no convencionales"
    {"id": "h-a-8", "text": "Me imagino en un lugar donde cada quien tiene su estilo, no en una oficina donde todos se ven iguales", "type": "likert", "category": "A"},

    # ---------------- S · Social (ayudar, enseñar, acompañar) ----------------
    # orig: "Me gusta ayudar a los demas"
    {"id": "h-s-1", "text": "Me gusta ayudar a los demás cuando lo necesitan", "type": "likert", "category": "S"},
    # orig: "Disfruto ensenar o explicar cosas a otros"
    {"id": "h-s-2", "text": "Mis amigos me piden que les explique cuando no entienden algo de clase", "type": "likert", "category": "S"},
    # orig: "Prefiero trabajar en equipo"
    {"id": "h-s-3", "text": "Prefiero los trabajos en grupo que hacerlo todo solo", "type": "likert", "category": "S"},
    # orig: "Me interesa el bienestar de otras personas"
    {"id": "h-s-4", "text": "Me importa cómo se están sintiendo las personas a mi alrededor", "type": "likert", "category": "S"},
    # orig: "Disfruto escuchar los problemas de otros"
    {"id": "h-s-5", "text": "Mis amigos me buscan para contarme sus problemas", "type": "likert", "category": "S"},
    # orig: "Me gusta participar en actividades comunitarias"
    {"id": "h-s-6", "text": "Me meto en actividades del colegio o del barrio para ayudar: campañas, recolectas, voluntariados", "type": "likert", "category": "S"},
    # orig: "Prefiero profesiones donde pueda hacer una diferencia social"
    {"id": "h-s-7", "text": "Me gustaría dedicarme de grande a algo que le sirva a mucha gente", "type": "likert", "category": "S"},
    # orig: "Me siento satisfecho cuando ayudo a alguien a resolver un problema"
    {"id": "h-s-8", "text": "Me siento bien cuando alguien sale de un problema gracias a mí", "type": "likert", "category": "S"},

    # ---------------- E · Emprendedor (liderar, convencer, competir) ---------
    # orig: "Me gusta liderar proyectos o grupos"
    {"id": "h-e-1", "text": "En los trabajos en grupo casi siempre termino organizando al equipo", "type": "likert", "category": "E"},
    # orig: "Disfruto persuadir a otros"
    {"id": "h-e-2", "text": "Se me da convencer a los demás de mi idea o de mi plan", "type": "likert", "category": "E"},
    # orig: "Prefiero tomar la iniciativa"
    {"id": "h-e-3", "text": "Prefiero ser el que propone el plan y no el que espera a ver qué proponen", "type": "likert", "category": "E"},
    # orig: "Me gusta negociar y hacer tratos"
    {"id": "h-e-4", "text": "Me gusta negociar: cambiar cosas, conseguir un mejor trato, llegar a un acuerdo", "type": "likert", "category": "E"},
    # orig: "Disfruto competir y ganar"
    {"id": "h-e-5", "text": "Me encanta competir y ganar, en deportes o en videojuegos", "type": "likert", "category": "E"},
    # orig: "Me interesa el mundo de los negocios"
    {"id": "h-e-6", "text": "Me da curiosidad cómo la gente monta un negocio y gana dinero con él", "type": "likert", "category": "E"},
    # orig: "Prefiero tener influencia sobre otros"
    {"id": "h-e-7", "text": "Me gusta que mis ideas sean las que el grupo termina haciendo", "type": "likert", "category": "E"},
    # orig: "Me gusta asumir riesgos calculados"
    {"id": "h-e-8", "text": "Me arriesgo cuando creo que vale la pena, aunque pueda salir mal", "type": "likert", "category": "E"},

    # ---------------- C · Convencional (orden, datos, instrucciones) ---------
    # orig: "Soy muy organizado/a"
    {"id": "h-c-1", "text": "Soy organizado con mis cosas: mi maleta, mis cuadernos, mi cuarto", "type": "likert", "category": "C"},
    # orig: "Me gustan las tareas con procedimientos claros"
    {"id": "h-c-2", "text": "Me gusta que me digan paso a paso qué hay que hacer", "type": "likert", "category": "C"},
    # orig: "Prefiero trabajar con numeros y datos"
    {"id": "h-c-3", "text": "Me gusta llevar cuentas y números: lo que gasto, mis puntos, mis estadísticas", "type": "likert", "category": "C"},
    # orig: "Disfruto mantener registros y archivos ordenados"
    {"id": "h-c-4", "text": "Tengo mis fotos, archivos y apuntes ordenados y con nombre", "type": "likert", "category": "C"},
    # orig: "Me gusta seguir instrucciones precisas"
    {"id": "h-c-5", "text": "Sigo las instrucciones tal cual cuando armo algo o hago una receta", "type": "likert", "category": "C"},
    # orig: "Prefiero la estabilidad y la rutina"
    {"id": "h-c-6", "text": "Me siento mejor cuando mis días son parecidos y sé qué va a pasar", "type": "likert", "category": "C"},
    # orig: "Me siento comodo con tareas administrativas"
    {"id": "h-c-7", "text": "No me molesta hacer tareas repetitivas, como llenar una lista o revisar una planilla", "type": "likert", "category": "C"},
    # orig: "Disfruto verificar detalles y asegurar precision"
    {"id": "h-c-8", "text": "Reviso mis trabajos varias veces para que no se me quede ningún error", "type": "likert", "category": "C"},
]


# La descripción también se adapta: es lo primero que el estudiante lee en la
# lista de tests. Se dice explícito que es el MISMO test para que ni él ni el
# colegio crean que le dieron una versión "de juguete".
HOLLAND_JUNIOR_DESCRIPTION = (
    "El mismo test de intereses Holland, con las preguntas escritas para tu edad. "
    "Descubre hacia dónde se van tus gustos entre las 6 categorías: Realista, "
    "Investigador, Artístico, Social, Emprendedor y Convencional."
)


def get_holland_junior() -> Dict[str, Any]:
    """Test Holland con la redacción de 9°/10°.

    Los metadatos (id, slug, name, academicBasis, questionCount, icon) se copian
    del banco canónico EN TIEMPO DE EJECUCIÓN, no se duplican a mano: si mañana
    cambia el nombre o el conteo del test adulto, esta versión lo hereda sola y
    no aparece una segunda fuente de verdad que se desincronice en silencio.

    El ``id`` sigue siendo "holland" a propósito: el resultado que se guarda, el
    scoring, el PDF y la interpretación son los del mismo instrumento. Un
    ``test_id`` nuevo obligaría a enseñarle "holland_junior" a media docena de
    consumidores (scoring_service, pdf_service, consolidación, Bitrix) sin ganar
    nada — y partiría en dos la data histórica del mismo test.
    """
    base = get_test_by_id("holland")
    if base is None:  # pragma: no cover - el banco canónico siempre está
        raise RuntimeError("El banco Holland canónico no está disponible")

    junior = dict(base)
    junior["questions"] = [dict(q) for q in HOLLAND_JUNIOR_QUESTIONS]
    junior["description"] = HOLLAND_JUNIOR_DESCRIPTION
    junior["variant"] = VARIANT_JUNIOR
    return junior
