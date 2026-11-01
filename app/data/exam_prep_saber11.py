"""Práctica Saber 11 · los ejercicios propios (Sprint 4, I-5).

Va aparte de `exam_prep.py` solo por tamaño; las reglas son las de ese módulo
(léelas en su docstring). Lo propio de este:

- **Ningún ejercicio viene de un cuadernillo del Icfes ni lo adapta.** Sus
  términos de uso prohíben el uso con fines de lucro y la "transformación"
  (ver I-4 en el checklist del Sprint 4). Se practica lo que cada prueba evalúa
  según la estructura pública del examen, con situaciones y textos escritos para
  este repo.
- Los enunciados van en **español**, salvo la prueba de inglés; las
  explicaciones, siempre en español, nombrando la trampa de cada distractor.
- Las cifras de los ejercicios son parte de cada problema inventado (precios de
  una tienda, reglas de una biblioteca), no datos del examen.

`construir(item, F, I, A)` recibe el validador `_item` y los niveles de
`exam_prep.py`: así este módulo no importa al otro (que lo importa a él).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

TEXTOS: Dict[str, str] = {
    "s11_trabajo_remoto": (
        "El trabajo remoto y las ciudades\n\n"
        "Durante décadas, las grandes ciudades crecieron porque allí estaba el "
        "trabajo: quien quería un buen empleo tenía que mudarse cerca de las "
        "oficinas. El trabajo remoto empezó a romper esa ecuación. Si una parte "
        "de las tareas puede hacerse desde cualquier lugar con conexión, ya no "
        "es indispensable vivir en la capital ni pagar sus arriendos. Algunos "
        "municipios intermedios han visto llegar nuevos habitantes y, con ellos, "
        "más demanda de cafés, colegios y servicios.\n\n"
        "Sin embargo, sería apresurado hablar del fin de las grandes ciudades. "
        "No todos los trabajos pueden hacerse a distancia: un enfermero, una "
        "cocinera o un operario de construcción necesitan estar presentes. "
        "Además, muchas empresas han pedido a sus equipos volver a la oficina "
        "algunos días por semana, porque consideran que ciertas conversaciones y "
        "aprendizajes ocurren mejor cara a cara. Lo más probable no es que las "
        "ciudades se vacíen, sino que cambie la manera de usarlas: menos "
        "desplazamientos diarios y más encuentros con un propósito."
    ),
    "s11_ultima_funcion": (
        "La última función\n\n"
        "El último domingo de funciones, don Aurelio barrió la sala del cine dos "
        "veces, aunque la primera ya la había dejado limpia. Ordenó las sillas "
        "que nadie iba a usar y revisó el proyector como quien acomoda la "
        "almohada de un enfermo. A las seis abrió la puerta. Entraron once "
        "personas: los mismos de siempre, más una niña que nunca había visto una "
        "película en pantalla grande. Cuando se apagaron las luces, la niña "
        "soltó un grito pequeño y luego se quedó quieta, con la boca abierta, "
        "durante toda la función. Al salir, le preguntó a don Aurelio si el cine "
        "abría el domingo siguiente. Él tardó en contestar.\n\n"
        "—Eso depende de ti —le dijo por fin—, de que traigas a tus amigos."
    ),
    "s11_celular_colegio": (
        "¿El celular en el salón?\n\n"
        "Varios colegios del país han decidido prohibir el celular durante la "
        "jornada. Sus defensores dicen que los estudiantes se distraen menos, "
        "conversan más en los descansos y sufren menos acoso por redes en horas "
        "de clase. Quienes se oponen responden que el celular también es una "
        "herramienta: sirve para investigar, para comunicarse con la familia en "
        "una emergencia y para aprender a usar la tecnología con "
        "responsabilidad, algo que una prohibición no enseña.\n\n"
        "En mi opinión, el debate está mal planteado. La pregunta no debería ser "
        "si el celular entra o no al salón, sino para qué entra. Un colegio que "
        "lo prohíbe todo el día y uno que lo permite sin reglas fallan por lo "
        "mismo: le dejan la decisión a la costumbre y no a un propósito. Lo "
        "razonable es acordar con los estudiantes momentos claros de uso, y "
        "explicar por qué."
    ),
    "s11_biblioteca": (
        "Biblioteca Municipal · Préstamo de libros\n\n"
        "• Préstamo: hasta 3 libros por persona, durante 15 días.\n"
        "• Renovación: una sola vez, por 15 días más, siempre que nadie haya "
        "reservado el libro.\n"
        "• Devolución tardía: un día sin préstamo por cada día de retraso.\n"
        "• Menores de 14 años: necesitan el carné firmado por un acudiente.\n"
        "• Libros de referencia (diccionarios, enciclopedias): solo se consultan "
        "en la sala."
    ),
    # Tanda 3 · el único texto en inglés: la prueba de inglés se presenta en inglés.
    "s11_coffee_trip": (
        "Hi Daniel,\n\n"
        "Thanks for your message! The school trip to the coffee farm was amazing. "
        "We left at six in the morning, so I was very sleepy on the bus. When we "
        "arrived, a farmer showed us how coffee grows, from the flower to the red "
        "fruit. We also picked some fruit ourselves, but it was harder than I "
        "expected because the plants grow on steep hills. In the afternoon it "
        "started to rain, so we couldn't visit the river. I'm a bit sad about "
        "that, but the teacher says we can go back next year. I bought a small bag "
        "of coffee for my parents.\n\n"
        "See you on Monday,\n"
        "Laura"
    ),
}


def construir(item: Callable[..., Dict[str, Any]], F: str, I: str, A: str) -> List[Dict[str, Any]]:
    lectura = [
        # --- El trabajo remoto y las ciudades ---------------------------------
        item(
            "s11-lc-1", habilidad="s11_lectura", nivel=F, passage="s11_trabajo_remoto",
            question="¿Cuál es la idea principal del texto?",
            options=[
                "El trabajo remoto está cambiando la relación entre empleo y ciudad, pero no acabará con las grandes ciudades.",
                "Las grandes ciudades van a desaparecer por culpa del trabajo remoto.",
                "Los municipios intermedios ya son más grandes que las capitales.",
                "Las empresas prohíben el trabajo remoto para que la gente vuelva a la oficina.",
            ],
            correct="El trabajo remoto está cambiando la relación entre empleo y ciudad, pero no acabará con las grandes ciudades.",
            explanation=(
                "La idea principal recoge los dos párrafos: el primero dice que el trabajo "
                "remoto rompió la relación entre empleo y ciudad, y el segundo, que sería "
                "apresurado hablar del fin de las ciudades. La segunda opción es justo lo "
                "que el texto rechaza; la tercera no aparece; la cuarta exagera (las "
                "empresas piden volver algunos días, no prohíben)."
            ),
        ),
        item(
            "s11-lc-2", habilidad="s11_lectura", nivel=I, passage="s11_trabajo_remoto",
            question="¿Qué función cumple la frase «Sin embargo, sería apresurado hablar del fin de las grandes ciudades»?",
            options=[
                "Matiza la idea del párrafo anterior para evitar una conclusión exagerada.",
                "Niega que el trabajo remoto exista.",
                "Da un ejemplo de lo dicho en el párrafo anterior.",
                "Resume todos los argumentos del texto.",
            ],
            correct="Matiza la idea del párrafo anterior para evitar una conclusión exagerada.",
            explanation=(
                "«Sin embargo» anuncia un contraste, y «apresurado» dice que el problema "
                "no es la idea anterior sino llevarla demasiado lejos. No la niega (el "
                "texto sí acepta que el trabajo remoto cambió las cosas) y no es un "
                "ejemplo ni un resumen: abre un argumento nuevo."
            ),
        ),
        item(
            "s11-lc-3", habilidad="s11_lectura", nivel=F, passage="s11_trabajo_remoto",
            question="Según el texto, ¿por qué algunas empresas han pedido volver a la oficina algunos días?",
            options=[
                "Porque consideran que ciertas conversaciones y aprendizajes ocurren mejor cara a cara.",
                "Porque el trabajo remoto es más costoso para ellas.",
                "Porque los arriendos en la capital bajaron.",
                "Porque la conexión a internet en los municipios es mala.",
            ],
            correct="Porque consideran que ciertas conversaciones y aprendizajes ocurren mejor cara a cara.",
            explanation=(
                "Está dicho casi literal en el segundo párrafo. Las otras tres son "
                "razones que suenan posibles, pero el texto no las menciona: en lectura "
                "crítica se responde con lo que dice el texto, no con lo que uno supone."
            ),
        ),
        item(
            "s11-lc-4", habilidad="s11_lectura", nivel=A, passage="s11_trabajo_remoto",
            question="La afirmación «ya no es indispensable vivir en la capital» supone que:",
            options=[
                "la razón principal para vivir en la capital era estar cerca del trabajo.",
                "en la capital no hay conexión a internet.",
                "todas las personas prefieren vivir en el campo.",
                "el trabajo remoto es obligatorio para todos.",
            ],
            correct="la razón principal para vivir en la capital era estar cerca del trabajo.",
            explanation=(
                "Un supuesto es lo que tiene que ser cierto para que la frase tenga "
                "sentido. Si deja de ser indispensable vivir allí cuando el trabajo se "
                "puede hacer a distancia, es porque el trabajo era lo que obligaba a "
                "vivir allí (el texto lo dice al comienzo). Las otras opciones no se "
                "necesitan para que la frase funcione, y la cuarta contradice que solo "
                "«una parte de las tareas» se puede hacer a distancia."
            ),
        ),
        item(
            "s11-lc-5", habilidad="s11_lectura", nivel=I, passage="s11_trabajo_remoto",
            question="¿Para qué menciona el autor al enfermero, la cocinera y el operario de construcción?",
            options=[
                "Para mostrar que no todos los trabajos pueden hacerse a distancia.",
                "Para demostrar que esos oficios están mal pagados.",
                "Para explicar por qué crecen los municipios intermedios.",
                "Para criticar a quienes trabajan desde la casa.",
            ],
            correct="Para mostrar que no todos los trabajos pueden hacerse a distancia.",
            explanation=(
                "Los ejemplos van justo después de «No todos los trabajos pueden hacerse a "
                "distancia»: la ilustran. El texto no habla de salarios ni critica a "
                "nadie, y el crecimiento de los municipios está en el otro párrafo."
            ),
        ),
        # --- La última función --------------------------------------------------
        item(
            "s11-lc-6", habilidad="s11_lectura", nivel=F, passage="s11_ultima_funcion",
            question="¿Qué se puede afirmar de don Aurelio a partir del texto?",
            options=[
                "Siente apego por el cine y por su oficio.",
                "Está feliz de que el cine vaya a cerrar.",
                "Es el dueño de una cadena de cines.",
                "No conoce a las personas que asisten.",
            ],
            correct="Siente apego por el cine y por su oficio.",
            explanation=(
                "Barre la sala dos veces aunque ya estaba limpia y cuida el proyector como "
                "a un enfermo: son acciones de alguien que quiere ese lugar. Nada indica "
                "alegría por el cierre, el texto no dice que tenga más cines, y los "
                "asistentes son «los mismos de siempre», así que sí los conoce."
            ),
        ),
        item(
            "s11-lc-7", habilidad="s11_lectura", nivel=I, passage="s11_ultima_funcion",
            question="La expresión «como quien acomoda la almohada de un enfermo» es:",
            options=[
                "una comparación que muestra el cuidado con el que trata el proyector.",
                "una exageración para mostrar que el proyector está dañado.",
                "un dato técnico sobre cómo se revisa un proyector.",
                "una ironía para burlarse de don Aurelio.",
            ],
            correct="una comparación que muestra el cuidado con el que trata el proyector.",
            explanation=(
                "«Como quien…» compara dos acciones: revisar el proyector y cuidar a un "
                "enfermo. Lo que comparten es la delicadeza, y de paso sugiere que el cine "
                "está en sus últimos días. No dice que el proyector esté dañado, no es "
                "información técnica y el tono del texto no es de burla."
            ),
        ),
        item(
            "s11-lc-8", habilidad="s11_lectura", nivel=A, passage="s11_ultima_funcion",
            question="¿Qué sugiere la respuesta final de don Aurelio a la niña?",
            options=[
                "Que el cine podría seguir si vuelve a tener público, y que la niña representa esa posibilidad.",
                "Que la niña es la nueva dueña del cine.",
                "Que don Aurelio no quiere que la niña vuelva.",
                "Que el cine ya tiene funciones aseguradas para el domingo siguiente.",
            ],
            correct="Que el cine podría seguir si vuelve a tener público, y que la niña representa esa posibilidad.",
            explanation=(
                "Era «el último domingo de funciones», pero don Aurelio no dice que no: "
                "dice que depende de que lleguen más personas. La respuesta deja el final "
                "abierto. La tercera opción contradice que la invite a traer amigos, y la "
                "cuarta, que fuera la última función."
            ),
        ),
        item(
            "s11-lc-9", habilidad="s11_lectura", nivel=F, passage="s11_ultima_funcion",
            question="¿Quién veía por primera vez una película en pantalla grande?",
            options=["Una niña", "Don Aurelio", "Los once asistentes", "Nadie: todos eran los mismos de siempre"],
            correct="Una niña",
            explanation=(
                "El texto dice que entraron «los mismos de siempre, más una niña que nunca "
                "había visto una película en pantalla grande». La trampa de la última "
                "opción es quedarse con la primera mitad de la frase y no leer el «más»."
            ),
        ),
        item(
            "s11-lc-10", habilidad="s11_lectura", nivel=I, passage="s11_ultima_funcion",
            question="¿Cómo podría describirse el ambiente del texto?",
            options=[
                "Nostálgico, con un final abierto a la esperanza.",
                "Alegre y festivo de principio a fin.",
                "De suspenso y miedo.",
                "Indiferente y frío.",
            ],
            correct="Nostálgico, con un final abierto a la esperanza.",
            explanation=(
                "Es la despedida de un lugar querido (nostalgia), pero cierra con una "
                "posibilidad de que siga (esperanza). El grito de la niña es de asombro, "
                "no de miedo, y los cuidados de don Aurelio desmienten la indiferencia."
            ),
        ),
        # --- ¿El celular en el salón? --------------------------------------------
        item(
            "s11-lc-11", habilidad="s11_lectura", nivel=F, passage="s11_celular_colegio",
            question="¿Cuál es la postura del autor?",
            options=[
                "Lo importante es definir para qué y cuándo se usa el celular, con acuerdos claros.",
                "Hay que prohibir el celular durante toda la jornada.",
                "Hay que permitir el celular sin ninguna regla.",
                "El celular no tiene ninguna utilidad educativa.",
            ],
            correct="Lo importante es definir para qué y cuándo se usa el celular, con acuerdos claros.",
            explanation=(
                "La postura aparece después de «En mi opinión»: la pregunta es «para qué "
                "entra», y lo razonable es acordar momentos de uso. Las dos opciones del "
                "medio son justo los extremos que el autor critica, y la última "
                "contradice que reconozca usos del celular."
            ),
        ),
        item(
            "s11-lc-12", habilidad="s11_lectura", nivel=I, passage="s11_celular_colegio",
            question="¿Cuál de estos es un argumento de quienes se OPONEN a la prohibición?",
            options=[
                "Una prohibición no enseña a usar la tecnología con responsabilidad.",
                "Sin celular, los estudiantes conversan más en los descansos.",
                "Sin celular hay menos acoso por redes en horas de clase.",
                "El debate está mal planteado.",
            ],
            correct="Una prohibición no enseña a usar la tecnología con responsabilidad.",
            explanation=(
                "Aquí la clave es quién dice cada cosa. La segunda y la tercera son "
                "argumentos de los defensores de la prohibición, y la cuarta es la "
                "opinión del autor, no de los que se oponen."
            ),
        ),
        item(
            "s11-lc-13", habilidad="s11_lectura", nivel=A, passage="s11_celular_colegio",
            question="Según el autor, el colegio que prohíbe el celular todo el día y el que lo permite sin reglas «fallan por lo mismo». ¿Qué tienen en común?",
            options=[
                "Ninguno decide el uso del celular a partir de un propósito.",
                "Los dos prohíben el celular.",
                "Los dos tienen estudiantes más distraídos.",
                "Los dos consultan a los estudiantes.",
            ],
            correct="Ninguno decide el uso del celular a partir de un propósito.",
            explanation=(
                "El texto lo explica después de los dos puntos: los dos «le dejan la "
                "decisión a la costumbre y no a un propósito». La segunda es falsa para "
                "uno de ellos, la tercera no aparece, y consultar a los estudiantes es lo "
                "que el autor propone, no lo que hacen."
            ),
        ),
        item(
            "s11-lc-14", habilidad="s11_lectura", nivel=I, passage="s11_celular_colegio",
            question="¿Qué tipo de texto es?",
            options=[
                "Una columna de opinión que presenta posturas y toma una propia.",
                "Una noticia que solo informa hechos.",
                "Un artículo científico con resultados de un experimento.",
                "Un reglamento escolar.",
            ],
            correct="Una columna de opinión que presenta posturas y toma una propia.",
            explanation=(
                "Expone dos posturas y luego dice «En mi opinión»: eso no lo hace una "
                "noticia, que no toma partido. No presenta datos de un experimento ni "
                "normas que haya que cumplir."
            ),
        ),
        item(
            "s11-lc-15", habilidad="s11_lectura", nivel=A, passage="s11_celular_colegio",
            question="¿Cuál de estos hallazgos DEBILITARÍA más la postura del autor?",
            options=[
                "Que los acuerdos de uso casi nunca se cumplen y solo la prohibición total reduce la distracción.",
                "Que los estudiantes usan el celular para investigar.",
                "Que muchos colegios del país permiten el celular.",
                "Que los estudiantes prefieren conversar en los descansos.",
            ],
            correct="Que los acuerdos de uso casi nunca se cumplen y solo la prohibición total reduce la distracción.",
            explanation=(
                "La propuesta del autor descansa en que los acuerdos funcionan. Si no se "
                "cumplen, su solución se cae. La segunda opción más bien apoya que el "
                "celular tiene usos; la tercera no dice nada sobre si los acuerdos sirven, "
                "y la cuarta es compatible con su propuesta."
            ),
        ),
        # --- Biblioteca Municipal (texto discontinuo) ----------------------------
        item(
            "s11-lc-16", habilidad="s11_lectura", nivel=F, passage="s11_biblioteca",
            question="¿Cuántos libros puede llevarse una persona al mismo tiempo?",
            options=["Hasta 3", "Hasta 15", "Solo 1", "Los que quiera"],
            correct="Hasta 3",
            explanation=(
                "Lo dice el primer punto. El 15 es la trampa: son los días del préstamo, "
                "no la cantidad de libros. En un texto con listas, ubica primero qué "
                "número responde a qué."
            ),
        ),
        item(
            "s11-lc-17", habilidad="s11_lectura", nivel=A, passage="s11_biblioteca",
            question="Sofía ya renovó una vez un libro y ahora quiere renovarlo otra vez. Nadie lo ha reservado. ¿Puede hacerlo?",
            options=[
                "No, porque la renovación se permite una sola vez.",
                "Sí, porque nadie lo ha reservado.",
                "Sí, pero solo por 15 días más.",
                "Sí, si paga una multa.",
            ],
            correct="No, porque la renovación se permite una sola vez.",
            explanation=(
                "La renovación tiene dos condiciones y hay que cumplir ambas: que nadie lo "
                "haya reservado Y que sea la primera renovación. Sofía cumple la primera "
                "pero no la segunda. La trampa es mirar solo una condición. El reglamento "
                "no habla de multas en dinero."
            ),
        ),
        item(
            "s11-lc-18", habilidad="s11_lectura", nivel=I, passage="s11_biblioteca",
            question="Un estudiante devuelve un libro 4 días después de la fecha. ¿Qué le pasa?",
            options=[
                "Queda 4 días sin poder pedir libros prestados.",
                "Paga una multa por cada día de retraso.",
                "No puede volver a la biblioteca.",
                "Nada, si devuelve el libro en buen estado.",
            ],
            correct="Queda 4 días sin poder pedir libros prestados.",
            explanation=(
                "«Un día sin préstamo por cada día de retraso»: 4 días tarde, 4 días sin "
                "préstamo. La multa en dinero es la sanción que uno espera por costumbre, "
                "pero este reglamento no la menciona."
            ),
        ),
        item(
            "s11-lc-19", habilidad="s11_lectura", nivel=F, passage="s11_biblioteca",
            question="Tomás tiene 12 años y quiere llevarse un libro. ¿Qué necesita?",
            options=[
                "Su carné firmado por un acudiente.",
                "Esperar a cumplir 14 años.",
                "Una carta de su colegio.",
                "Nada especial.",
            ],
            correct="Su carné firmado por un acudiente.",
            explanation=(
                "Es menor de 14, así que aplica el cuarto punto. El reglamento no le "
                "prohíbe pedir libros (no tiene que esperar) ni pide cartas del colegio."
            ),
        ),
        item(
            "s11-lc-20", habilidad="s11_lectura", nivel=A, passage="s11_biblioteca",
            question="El reglamento no explica por qué los diccionarios y las enciclopedias solo se consultan en la sala. ¿Cuál es la explicación más razonable?",
            options=[
                "Se consultan para búsquedas cortas, y si alguien se los lleva 15 días los demás se quedan sin ellos.",
                "Son los libros más baratos de la biblioteca.",
                "Los menores de 14 años no los pueden leer.",
                "La biblioteca no permite leer en la sala.",
            ],
            correct="Se consultan para búsquedas cortas, y si alguien se los lleva 15 días los demás se quedan sin ellos.",
            explanation=(
                "Aquí se pide inferir el propósito de una norma. La primera opción encaja "
                "con cómo se usa un diccionario y con la duración del préstamo. La "
                "segunda no tiene relación con la regla, la tercera no aparece y la "
                "cuarta contradice el texto, que dice que sí se consultan en la sala."
            ),
        ),
    ]

    matematicas = [
        item(
            "s11-mat-1", habilidad="s11_matematicas", nivel=F,
            question="Una camiseta cuesta $40.000 y tiene un descuento del 25 %. ¿Cuánto se paga por ella?",
            options=["$30.000", "$10.000", "$32.000", "$15.000"],
            correct="$30.000",
            explanation=(
                "El 25 % de 40.000 es 10.000, y se paga lo que queda: 40.000 − 10.000 = "
                "30.000. La trampa más común es responder $10.000, que es el descuento y "
                "no lo que se paga. $32.000 sería un descuento del 20 %."
            ),
        ),
        item(
            "s11-mat-2", habilidad="s11_matematicas", nivel=F,
            question="Las notas de Ana en cuatro quices fueron 2,0; 3,5; 4,0 y 4,5. ¿Cuál es su promedio?",
            options=["3,5", "3,75", "4,0", "14,0"],
            correct="3,5",
            explanation=(
                "Promedio = suma ÷ cantidad = 14,0 ÷ 4 = 3,5. 14,0 es la suma sin "
                "dividir, y 3,75 es la mediana (el punto medio entre 3,5 y 4,0): "
                "promedio y mediana no siempre coinciden."
            ),
        ),
        item(
            "s11-mat-3", habilidad="s11_matematicas", nivel=F,
            question="Una receta para 4 personas lleva 300 g de arroz. ¿Cuánto arroz se necesita para 10 personas?",
            options=["750 g", "600 g", "1.200 g", "3.000 g"],
            correct="750 g",
            explanation=(
                "Por persona son 300 ÷ 4 = 75 g, y para 10 personas, 75 × 10 = 750 g. "
                "600 g sería para 8 personas, 1.200 g es multiplicar por 4 en vez de "
                "dividir, y 3.000 g es multiplicar 300 por 10 sin pasar por una persona."
            ),
        ),
        item(
            "s11-mat-4", habilidad="s11_matematicas", nivel=F,
            question="En una encuesta a 200 estudiantes, el 30 % dijo que su deporte favorito es el fútbol. ¿Cuántos estudiantes son?",
            options=["60", "30", "70", "140"],
            correct="60",
            explanation=(
                "30 % de 200 = 0,30 × 200 = 60. El 30 es el porcentaje, no la cantidad, "
                "y 140 son los que NO eligieron fútbol (el 70 %)."
            ),
        ),
        item(
            "s11-mat-5", habilidad="s11_matematicas", nivel=F,
            question="Un jardín rectangular mide 8 m de largo y 5 m de ancho. Se va a cercar todo su borde. ¿Cuántos metros de cerca se necesitan?",
            options=["26 m", "40 m", "13 m", "21 m"],
            correct="26 m",
            explanation=(
                "El borde es el perímetro: 8 + 5 + 8 + 5 = 26 m. 40 es el área (8 × 5, y "
                "además en metros cuadrados), y 13 es sumar solo dos lados."
            ),
        ),
        item(
            "s11-mat-6", habilidad="s11_matematicas", nivel=F,
            question="Si 3x + 5 = 20, ¿cuánto vale x?",
            options=["5", "15", "25/3", "8"],
            correct="5",
            explanation=(
                "Se resta 5 a los dos lados (3x = 15) y luego se divide entre 3 (x = 5). "
                "15 es olvidar dividir; 25/3 sale de sumar 5 en vez de restarlo."
            ),
        ),
        item(
            "s11-mat-7", habilidad="s11_matematicas", nivel=F,
            question="Una bolsa tiene 3 balotas rojas, 5 azules y 2 verdes. Si se saca una sin mirar, ¿cuál es la probabilidad de que sea roja?",
            options=["3/10", "3/7", "1/3", "3/5"],
            correct="3/10",
            explanation=(
                "Probabilidad = casos favorables ÷ casos posibles = 3 ÷ 10 (hay 10 "
                "balotas en total). 3/7 compara las rojas solo con las que no son rojas, "
                "y 1/3 supone que los tres colores son igual de probables, pero hay más "
                "azules."
            ),
        ),
        item(
            "s11-mat-8", habilidad="s11_matematicas", nivel=I,
            question="Un taxi cobra $5.000 por arrancar y $1.200 por cada kilómetro. ¿Qué expresión da el costo C de un viaje de k kilómetros?",
            options=["C = 5.000 + 1.200k", "C = 6.200k", "C = 1.200 + 5.000k", "C = 5.000k + 1.200k"],
            correct="C = 5.000 + 1.200k",
            explanation=(
                "El arranque se cobra una vez (fijo) y los kilómetros se multiplican por "
                "1.200. C = 6.200k cobraría el arranque en cada kilómetro, y la tercera "
                "opción intercambia lo fijo con lo que depende de k."
            ),
        ),
        item(
            "s11-mat-9", habilidad="s11_matematicas", nivel=I,
            question="El precio de un producto sube un 10 % y, un mes después, baja un 10 %. Comparado con el precio inicial, el precio final es:",
            options=["un 1 % menor", "igual", "un 1 % mayor", "un 20 % menor"],
            correct="un 1 % menor",
            explanation=(
                "Si costaba 100, sube a 110; el 10 % de 110 es 11, así que baja a 99: un "
                "1 % menos que al inicio. La intuición dice «igual», pero el segundo 10 % "
                "se calcula sobre un precio más alto. Probar con 100 resuelve casi todos "
                "los problemas de porcentajes encadenados."
            ),
        ),
        item(
            "s11-mat-10", habilidad="s11_matematicas", nivel=I,
            question="Una tienda vendió 120 unidades en enero y 150 en febrero. ¿En qué porcentaje aumentaron las ventas?",
            options=["25 %", "30 %", "20 %", "150 %"],
            correct="25 %",
            explanation=(
                "Aumento = 150 − 120 = 30, y se compara con el valor INICIAL: 30 ÷ 120 = "
                "0,25 = 25 %. El 20 % sale de dividir entre 150 (el valor final), y el 30 % "
                "confunde el aumento en unidades con el porcentaje."
            ),
        ),
        item(
            "s11-mat-11", habilidad="s11_matematicas", nivel=I,
            question="En un mapa a escala 1:50.000, dos pueblos están a 4 cm. ¿Cuál es la distancia real?",
            options=["2 km", "20 km", "200 m", "0,2 km"],
            correct="2 km",
            explanation=(
                "1 cm del mapa son 50.000 cm reales, así que 4 cm son 200.000 cm = 2.000 m "
                "= 2 km. Las otras opciones son errores al pasar de centímetros a metros y "
                "a kilómetros: 100 cm son un metro y 1.000 m son un kilómetro."
            ),
        ),
        item(
            "s11-mat-12", habilidad="s11_matematicas", nivel=I,
            question="Dos ángulos de un triángulo miden 50° y 60°. ¿Cuánto mide el tercero?",
            options=["70°", "110°", "90°", "80°"],
            correct="70°",
            explanation=(
                "Los ángulos internos de un triángulo suman 180°: 180 − 50 − 60 = 70°. "
                "110° es la suma de los dos que se dan (la trampa es quedarse ahí), y "
                "90° supone que el triángulo es rectángulo, lo que nadie dijo."
            ),
        ),
        item(
            "s11-mat-13", habilidad="s11_matematicas", nivel=I,
            question="¿Cuál es la mediana de estos datos: 7, 2, 9, 4, 5?",
            options=["5", "9", "5,4", "7"],
            correct="5",
            explanation=(
                "Primero se ordenan: 2, 4, 5, 7, 9. La mediana es el del medio: 5. El 9 es "
                "el que queda en el medio SIN ordenar (la trampa más común), y 5,4 es el "
                "promedio."
            ),
        ),
        item(
            "s11-mat-14", habilidad="s11_matematicas", nivel=I,
            question="Con 2 llaves iguales, un tanque se llena en 6 horas. ¿En cuánto tiempo se llenaría con 3 llaves iguales a esas?",
            options=["4 horas", "9 horas", "3 horas", "5 horas"],
            correct="4 horas",
            explanation=(
                "Más llaves, menos tiempo: es una proporción inversa. El trabajo total es "
                "2 × 6 = 12 «horas-llave», y con 3 llaves son 12 ÷ 3 = 4 horas. 9 horas sale "
                "de tratarla como directa, que es el error que este tipo de pregunta busca."
            ),
        ),
        item(
            "s11-mat-15", habilidad="s11_matematicas", nivel=A,
            question="Una rampa sube 5 m de altura en una distancia horizontal de 12 m. ¿Cuánto mide la rampa?",
            options=["13 m", "17 m", "7 m", "169 m"],
            correct="13 m",
            explanation=(
                "La rampa es la hipotenusa de un triángulo rectángulo: √(5² + 12²) = "
                "√169 = 13 m. 17 m es sumar los catetos, y 169 es olvidar la raíz."
            ),
        ),
        item(
            "s11-mat-16", habilidad="s11_matematicas", nivel=A,
            question="Un cultivo empieza con 500 bacterias y su número se duplica cada hora. ¿Cuántas hay después de 4 horas?",
            options=["8.000", "2.500", "4.000", "2.000"],
            correct="8.000",
            explanation=(
                "Duplicar cuatro veces: 500 → 1.000 → 2.000 → 4.000 → 8.000 (500 × 2⁴). "
                "2.500 y 2.000 tratan el crecimiento como si sumara lo mismo cada hora, y "
                "4.000 se queda una hora corto."
            ),
        ),
        item(
            "s11-mat-17", habilidad="s11_matematicas", nivel=A,
            question="De 40 estudiantes, 25 hacen deporte, 15 tocan un instrumento y 8 hacen las dos cosas. ¿Cuántos no hacen ninguna?",
            options=["8", "0", "16", "32"],
            correct="8",
            explanation=(
                "Los 8 que hacen las dos cosas están contados en el 25 y en el 15. Hacen "
                "al menos una: 25 + 15 − 8 = 32, así que no hacen ninguna 40 − 32 = 8. El "
                "0 sale de sumar 25 + 15 sin restar a los repetidos, y 32 es la cantidad "
                "que sí hace algo."
            ),
        ),
        item(
            "s11-mat-18", habilidad="s11_matematicas", nivel=A,
            question="El plan A de celular cuesta $30.000 al mes con datos ilimitados. El plan B cuesta $10.000 más $500 por cada GB. ¿A partir de cuántos GB al mes es más barato el plan A?",
            options=["Más de 40 GB", "Más de 20 GB", "Más de 60 GB", "Nunca es más barato"],
            correct="Más de 40 GB",
            explanation=(
                "Se igualan los costos: 10.000 + 500g = 30.000, de donde g = 40. Con más "
                "de 40 GB el plan B pasa de $30.000 y conviene el A. 60 GB sale de dividir "
                "30.000 entre 500 olvidando el cargo fijo del plan B."
            ),
        ),
        item(
            "s11-mat-19", habilidad="s11_matematicas", nivel=A,
            question="En un colegio, los estudiantes con mejores notas duermen, en promedio, más horas. ¿Qué conclusión es válida?",
            options=[
                "En ese colegio hay una relación entre dormir más y tener mejores notas, pero los datos no prueban que una cause la otra.",
                "Dormir más causa mejores notas en cualquier colegio.",
                "Las notas no tienen ninguna relación con el sueño.",
                "Todos los que duermen poco sacan malas notas.",
            ],
            correct="En ese colegio hay una relación entre dormir más y tener mejores notas, pero los datos no prueban que una cause la otra.",
            explanation=(
                "Los datos muestran una relación (correlación) en ese colegio. No prueban "
                "causa ni se pueden extender a todos los colegios. Un promedio tampoco "
                "dice nada de «todos»: puede haber quien duerma poco y saque buenas notas."
            ),
        ),
        item(
            "s11-mat-20", habilidad="s11_matematicas", nivel=A,
            question="Un terreno rectangular de 20 m por 10 m tiene en el centro un jardín circular de 3 m de radio. ¿Qué área del terreno NO es jardín? (Usa π ≈ 3,14.)",
            options=["171,74 m²", "181,16 m²", "28,26 m²", "200 m²"],
            correct="171,74 m²",
            explanation=(
                "Área del terreno: 20 × 10 = 200 m². Área del jardín: π × 3² = 28,26 m². "
                "Lo que no es jardín: 200 − 28,26 = 171,74 m². 181,16 sale de usar 2πr "
                "(el perímetro del círculo) en vez del área, y 28,26 es el jardín."
            ),
        ),
    ]

    # --- Sociales y ciudadanas (tanda 2) --------------------------------------
    # Los datos de la Constitución que se usan son los que no admiten duda
    # (tutela, ramas del poder, mecanismos de participación, organismos de
    # control). El peso está en lo que la prueba más evalúa: analizar una
    # situación desde varias perspectivas y argumentar.
    sociales = [
        item(
            "s11-soc-1", habilidad="s11_sociales", nivel=F,
            question="¿Qué protege la acción de tutela?",
            options=[
                "Los derechos fundamentales, cuando son vulnerados o están amenazados.",
                "Los contratos entre empresas privadas.",
                "Las leyes que aprueba el Congreso.",
                "El cobro de los impuestos municipales.",
            ],
            correct="Los derechos fundamentales, cuando son vulnerados o están amenazados.",
            explanation=(
                "La tutela es el mecanismo para pedirle a un juez que proteja de forma "
                "rápida un derecho fundamental. Revisar si una ley se ajusta a la "
                "Constitución es otra cosa (lo hace la Corte Constitucional), y los "
                "contratos o los impuestos tienen sus propios trámites."
            ),
        ),
        item(
            "s11-soc-2", habilidad="s11_sociales", nivel=F,
            question="¿Qué rama del poder público se encarga principalmente de hacer las leyes?",
            options=["La legislativa (el Congreso)", "La ejecutiva", "La judicial", "La organización electoral"],
            correct="La legislativa (el Congreso)",
            explanation=(
                "El Congreso, formado por el Senado y la Cámara de Representantes, hace "
                "las leyes. La rama ejecutiva las ejecuta y la judicial resuelve los "
                "conflictos aplicándolas. La organización electoral organiza las "
                "elecciones."
            ),
        ),
        item(
            "s11-soc-3", habilidad="s11_sociales", nivel=F,
            question="Los habitantes de un municipio consideran que su alcalde no está cumpliendo el programa por el que lo eligieron. ¿Qué mecanismo de participación les permite quitarle el cargo?",
            options=["La revocatoria del mandato", "La acción de tutela", "El derecho de petición", "El cabildo abierto"],
            correct="La revocatoria del mandato",
            explanation=(
                "La revocatoria del mandato existe justamente para que los ciudadanos "
                "puedan retirar del cargo a un gobernante elegido que incumple su "
                "programa. La tutela protege derechos, la petición sirve para pedir "
                "información o actuaciones, y el cabildo abierto es una reunión pública "
                "del concejo para discutir asuntos de la comunidad."
            ),
        ),
        item(
            "s11-soc-4", habilidad="s11_sociales", nivel=F,
            question="Un ciudadano quiere que una entidad pública le entregue información sobre un contrato. ¿Qué mecanismo debe usar primero?",
            options=["El derecho de petición", "La acción de tutela", "La revocatoria del mandato", "El referendo"],
            correct="El derecho de petición",
            explanation=(
                "El derecho de petición permite solicitar información o actuaciones a "
                "las autoridades, que deben responder. La tutela llegaría después, si no "
                "le responden y se le vulnera ese derecho. La trampa es saltar "
                "directamente al mecanismo más conocido."
            ),
        ),
        item(
            "s11-soc-5", habilidad="s11_sociales", nivel=F,
            question="En el gobierno escolar, ¿cuál es la función principal del personero estudiantil?",
            options=[
                "Promover y defender los derechos y deberes de los estudiantes.",
                "Poner las sanciones disciplinarias.",
                "Definir las notas de cada materia.",
                "Administrar el presupuesto del colegio.",
            ],
            correct="Promover y defender los derechos y deberes de los estudiantes.",
            explanation=(
                "El personero es un estudiante elegido por sus compañeros para "
                "representarlos y velar por sus derechos y deberes. No sanciona, no "
                "califica y no maneja el dinero del colegio: esas son funciones de "
                "otras instancias."
            ),
        ),
        item(
            "s11-soc-6", habilidad="s11_sociales", nivel=F,
            question="La Constitución dice que Colombia es un Estado social de derecho. ¿Qué significa esa idea?",
            options=[
                "Que las autoridades están sometidas a la ley y deben buscar condiciones de vida digna para las personas.",
                "Que el presidente puede cambiar la Constitución por su cuenta.",
                "Que el Estado no interviene en ningún asunto económico ni social.",
                "Que solo votan las personas que tienen propiedades.",
            ],
            correct="Que las autoridades están sometidas a la ley y deben buscar condiciones de vida digna para las personas.",
            explanation=(
                "«De derecho»: nadie, ni siquiera el gobierno, está por encima de la ley. "
                "«Social»: el Estado tiene el deber de procurar condiciones dignas para "
                "todos. Las otras opciones van en contra de una de esas dos partes."
            ),
        ),
        item(
            "s11-soc-7", habilidad="s11_sociales", nivel=F,
            question="¿Para qué sirve que el poder público esté dividido en ramas independientes?",
            options=[
                "Para que ninguna persona o institución concentre todo el poder.",
                "Para que haya más empleados públicos.",
                "Para que las leyes se aprueben más rápido.",
                "Para que cada región tenga su propio presidente.",
            ],
            correct="Para que ninguna persona o institución concentre todo el poder.",
            explanation=(
                "Si quien hace las leyes, quien las ejecuta y quien juzga son "
                "independientes, cada uno puede controlar a los otros. La división no "
                "busca rapidez (de hecho, a veces la hace más lenta) ni crear empleo."
            ),
        ),
        item(
            "s11-soc-8", habilidad="s11_sociales", nivel=I,
            question="En una vereda se discute construir una vía que atravesaría un humedal. Los comerciantes la apoyan porque venderían más; un grupo ambiental se opone. ¿Qué interés defiende el grupo ambiental?",
            options=[
                "Conservar el ecosistema y el agua del humedal.",
                "Que los comerciantes vendan menos.",
                "Que la vereda siga incomunicada para siempre.",
                "Que la obra la haga una empresa de otra ciudad.",
            ],
            correct="Conservar el ecosistema y el agua del humedal.",
            explanation=(
                "Analizar una situación es entender qué busca cada actor. El grupo "
                "ambiental se opone por lo que le pasaría al humedal, no por perjudicar "
                "a los comerciantes ni por dejar a nadie incomunicado: atribuirle esas "
                "intenciones es caricaturizar su postura."
            ),
        ),
        item(
            "s11-soc-9", habilidad="s11_sociales", nivel=I,
            question="En la misma situación de la vía y el humedal, ¿qué propuesta tiene en cuenta los intereses de los dos grupos?",
            options=[
                "Estudiar un trazado que conecte la vereda sin atravesar el humedal.",
                "Construir la vía de inmediato, sin consultar a nadie.",
                "Prohibir para siempre cualquier vía en la vereda.",
                "Que decida el grupo que tenga más recursos económicos.",
            ],
            correct="Estudiar un trazado que conecte la vereda sin atravesar el humedal.",
            explanation=(
                "La primera opción busca la conexión que quieren los comerciantes y la "
                "protección que quiere el grupo ambiental. Las dos siguientes le dan la "
                "razón a un solo grupo, y la última reemplaza el diálogo por el poder "
                "económico."
            ),
        ),
        item(
            "s11-soc-10", habilidad="s11_sociales", nivel=I,
            question="El derecho a gozar de un ambiente sano, según la Constitución, es:",
            options=[
                "un derecho colectivo, que pertenece a la comunidad.",
                "un derecho que solo tienen los dueños de tierras.",
                "un deber que solo tiene el presidente.",
                "un derecho que solo existe en las zonas rurales.",
            ],
            correct="un derecho colectivo, que pertenece a la comunidad.",
            explanation=(
                "La Constitución lo ubica entre los derechos colectivos y del ambiente: "
                "es de todos, no de un propietario. Cuidarlo es tarea del Estado y "
                "también de las personas, en la ciudad y en el campo."
            ),
        ),
        item(
            "s11-soc-11", habilidad="s11_sociales", nivel=I,
            question="Un vecino pone música a todo volumen a las 3 de la madrugada y dice que está ejerciendo su libre desarrollo de la personalidad. Los demás vecinos reclaman su derecho al descanso. ¿Qué principio ayuda a resolver el conflicto?",
            options=[
                "El libre desarrollo de la personalidad tiene como límite los derechos de los demás.",
                "El libre desarrollo de la personalidad no tiene ningún límite.",
                "El derecho al descanso solo aplica entre semana.",
                "Gana quien primero se haya quejado.",
            ],
            correct="El libre desarrollo de la personalidad tiene como límite los derechos de los demás.",
            explanation=(
                "Los derechos conviven: uno se ejerce sin anular el de los otros. El "
                "vecino puede escuchar su música, pero no a esa hora y a ese volumen, "
                "porque afecta el descanso de los demás. Ningún derecho es absoluto."
            ),
        ),
        item(
            "s11-soc-12", habilidad="s11_sociales", nivel=I,
            question="Un periódico titula «El 80 % de los jóvenes del país no lee» a partir de una encuesta a 50 estudiantes de un solo colegio. ¿Cuál es el principal problema de esa afirmación?",
            options=[
                "La muestra es pequeña y de un solo colegio, así que no representa a los jóvenes del país.",
                "El porcentaje está mal calculado.",
                "Los jóvenes no deberían responder encuestas.",
                "No hay ningún problema: una encuesta siempre dice la verdad.",
            ],
            correct="La muestra es pequeña y de un solo colegio, así que no representa a los jóvenes del país.",
            explanation=(
                "El dato podría ser cierto para ese grupo, pero el titular lo extiende a "
                "todo el país. Evaluar una fuente es preguntarse de dónde salen los datos "
                "y hasta dónde permiten concluir. Nada indica que la cuenta esté mal."
            ),
        ),
        item(
            "s11-soc-13", habilidad="s11_sociales", nivel=I,
            question="Si en pocos años muchas familias se van del campo a las ciudades, ¿qué efecto es más probable en las ciudades?",
            options=[
                "Más demanda de vivienda, transporte y servicios públicos.",
                "Menos tráfico y menos necesidad de colegios.",
                "Que los alimentos se produzcan dentro de las ciudades.",
                "Ningún cambio, porque las ciudades ya están preparadas.",
            ],
            correct="Más demanda de vivienda, transporte y servicios públicos.",
            explanation=(
                "Más habitantes necesitan dónde vivir, cómo moverse y servicios como agua "
                "y salud. La segunda opción dice lo contrario, y la cuarta supone sin "
                "razón que no pasa nada."
            ),
        ),
        item(
            "s11-soc-14", habilidad="s11_sociales", nivel=I,
            question="¿Qué entidad vigila la conducta de los servidores públicos y puede sancionarlos disciplinariamente?",
            options=[
                "La Procuraduría General de la Nación",
                "La Contraloría General de la República",
                "La Registraduría Nacional del Estado Civil",
                "La Corte Constitucional",
            ],
            correct="La Procuraduría General de la Nación",
            explanation=(
                "La Procuraduría vigila la conducta de los servidores públicos. La "
                "Contraloría vigila el manejo de los recursos públicos (lo fiscal), la "
                "Registraduría organiza las elecciones y la identificación, y la Corte "
                "Constitucional protege la Constitución. Se confunden mucho la "
                "Procuraduría y la Contraloría: conducta frente a dinero."
            ),
        ),
        item(
            "s11-soc-15", habilidad="s11_sociales", nivel=A,
            question="El consejo de un colegio prohíbe usar gorra dentro del salón. Un estudiante debe usarla por una condición médica en la piel, y tiene la orden de su médico. ¿Qué es lo más justo?",
            options=[
                "Hacerle una excepción justificada, porque una norma general no debe vulnerar su derecho a la salud.",
                "Obligarlo a quitársela, porque la norma es igual para todos.",
                "Eliminar la norma para todos los estudiantes.",
                "Pedirle que estudie desde la casa.",
            ],
            correct="Hacerle una excepción justificada, porque una norma general no debe vulnerar su derecho a la salud.",
            explanation=(
                "Tratar igual a quien está en una situación distinta puede ser injusto. "
                "La excepción protege su salud sin quitarle sentido a la norma para los "
                "demás. Eliminar la norma es más de lo necesario, y mandarlo a la casa "
                "afecta su derecho a la educación."
            ),
        ),
        item(
            "s11-soc-16", habilidad="s11_sociales", nivel=A,
            question="En un debate sobre si los jóvenes de 16 años deberían poder votar, ¿cuál de estas intervenciones es un argumento y no solo una opinión?",
            options=[
                "Votar a los 16 podría crear el hábito de votar, porque la primera elección llegaría cuando todavía están en el colegio, donde se discuten estos temas.",
                "Los jóvenes de 16 años son inmaduros y no saben nada.",
                "A mí me parece bien, y punto.",
                "Eso nunca va a funcionar en este país.",
            ],
            correct="Votar a los 16 podría crear el hábito de votar, porque la primera elección llegaría cuando todavía están en el colegio, donde se discuten estos temas.",
            explanation=(
                "Un argumento da una razón que se puede discutir («porque…»). Las otras "
                "intervenciones afirman sin sustentar, y la segunda además generaliza "
                "sobre todo un grupo. No se trata de estar de acuerdo o no: el argumento "
                "podría ser a favor o en contra."
            ),
        ),
        item(
            "s11-soc-17", habilidad="s11_sociales", nivel=A,
            question="Una empresa minera financia un estudio que concluye que su mina no contamina el río. ¿Qué debería tener en cuenta un ciudadano al leerlo?",
            options=[
                "Que quien lo pagó tiene interés en el resultado, y conviene contrastarlo con estudios independientes.",
                "Que el estudio es falso, porque lo pagó la empresa.",
                "Que el estudio es verdadero, porque es un estudio.",
                "Que los ríos no se pueden contaminar.",
            ],
            correct="Que quien lo pagó tiene interés en el resultado, y conviene contrastarlo con estudios independientes.",
            explanation=(
                "Un posible conflicto de intereses no prueba que el estudio esté mal, "
                "pero sí obliga a contrastarlo. Descartarlo de entrada y creerlo sin más "
                "son los dos errores opuestos."
            ),
        ),
        item(
            "s11-soc-18", habilidad="s11_sociales", nivel=A,
            question="Un municipio prohíbe las ventas ambulantes en el centro para descongestionar las calles. ¿Qué efecto no buscado podría tener la medida?",
            options=[
                "Que muchas familias que viven de esas ventas se queden sin ingresos.",
                "Que las calles del centro queden más despejadas.",
                "Que los peatones caminen con más facilidad.",
                "Que el centro tenga menos congestión.",
            ],
            correct="Que muchas familias que viven de esas ventas se queden sin ingresos.",
            explanation=(
                "Las otras tres opciones son el efecto que la medida SÍ busca. La "
                "pregunta pide prever lo que no se buscaba: por eso hay que pensar en "
                "todos los afectados, no solo en el objetivo."
            ),
        ),
        item(
            "s11-soc-19", habilidad="s11_sociales", nivel=A,
            question="Si una ley contradice lo que dice la Constitución, ¿qué debe pasar?",
            options=[
                "Prevalece la Constitución, y la Corte Constitucional puede declarar que la ley no se ajusta a ella.",
                "Prevalece la ley, porque es más reciente.",
                "El presidente decide cuál de las dos se aplica.",
                "Se aplican las dos al mismo tiempo.",
            ],
            correct="Prevalece la Constitución, y la Corte Constitucional puede declarar que la ley no se ajusta a ella.",
            explanation=(
                "La Constitución es la norma de normas: ninguna ley puede ir en su "
                "contra, y la Corte Constitucional es quien revisa esos casos. Que una "
                "ley sea más reciente no la pone por encima de la Constitución."
            ),
        ),
        item(
            "s11-soc-20", habilidad="s11_sociales", nivel=A,
            question="Un grupo de ciudadanos quiere presentarle al Congreso un proyecto de ley escrito por ellos mismos. ¿Qué mecanismo de participación les corresponde?",
            options=[
                "La iniciativa popular legislativa",
                "El cabildo abierto",
                "La revocatoria del mandato",
                "La acción de tutela",
            ],
            correct="La iniciativa popular legislativa",
            explanation=(
                "La iniciativa popular permite que los ciudadanos presenten proyectos de "
                "ley. El cabildo abierto es una reunión del concejo para discutir "
                "asuntos de la comunidad, la revocatoria retira a un gobernante y la "
                "tutela protege derechos fundamentales: los cuatro son participación, "
                "pero sirven para cosas distintas."
            ),
        ),
    ]

    # --- Ciencias naturales (tanda 2) -----------------------------------------
    # Énfasis en indagación: variables, controles, hipótesis y leer datos, con
    # conceptos básicos de biología, química y física.
    ciencias = [
        item(
            "s11-cie-1", habilidad="s11_ciencias", nivel=F,
            question="Para saber cómo afecta la luz al crecimiento, Pedro pone tres plantas iguales, con el mismo suelo y la misma agua: una al sol, una en sombra y una en un cuarto oscuro. Mide su altura durante dos semanas. ¿Qué es lo que Pedro cambia a propósito?",
            options=["La cantidad de luz", "La altura de las plantas", "La cantidad de agua", "El tipo de suelo"],
            correct="La cantidad de luz",
            explanation=(
                "Lo que se cambia a propósito es la variable independiente: la luz. La "
                "altura es lo que se mide (la variable dependiente), y el agua y el "
                "suelo se mantienen iguales a propósito (variables controladas)."
            ),
        ),
        item(
            "s11-cie-2", habilidad="s11_ciencias", nivel=F,
            question="En el experimento de Pedro, ¿por qué usa la misma cantidad de agua para las tres plantas?",
            options=[
                "Para que la diferencia en el crecimiento se pueda atribuir solo a la luz.",
                "Porque las plantas no necesitan agua.",
                "Para ahorrar agua.",
                "Porque así crecen más rápido.",
            ],
            correct="Para que la diferencia en el crecimiento se pueda atribuir solo a la luz.",
            explanation=(
                "Si también cambiara el agua, no se sabría si la diferencia se debe a la "
                "luz o al agua. Controlar las demás variables es lo que hace confiable "
                "un experimento."
            ),
        ),
        item(
            "s11-cie-3", habilidad="s11_ciencias", nivel=F,
            question="Un cubo de hielo se deja al sol y se convierte en agua líquida. ¿Cómo se llama ese cambio de estado?",
            options=["Fusión", "Solidificación", "Condensación", "Sublimación"],
            correct="Fusión",
            explanation=(
                "De sólido a líquido es fusión. Solidificación es lo contrario (de "
                "líquido a sólido), condensación es de gas a líquido, y sublimación es de "
                "sólido a gas sin pasar por líquido."
            ),
        ),
        item(
            "s11-cie-4", habilidad="s11_ciencias", nivel=F,
            question="En una cadena alimentaria, el pasto es comido por los conejos y los conejos por los zorros. Si desaparecen los zorros, ¿qué es lo más probable que pase primero?",
            options=[
                "Aumenta la población de conejos.",
                "Disminuye la población de conejos.",
                "Aumenta la cantidad de pasto.",
                "No pasa nada en el ecosistema.",
            ],
            correct="Aumenta la población de conejos.",
            explanation=(
                "Sin su depredador, los conejos sobreviven más y aumentan. Con el "
                "tiempo, más conejos comerán más pasto, así que el pasto tendería a "
                "disminuir, no a aumentar. Un ecosistema casi nunca queda igual cuando "
                "falta una especie."
            ),
        ),
        item(
            "s11-cie-5", habilidad="s11_ciencias", nivel=F,
            question="En la fotosíntesis, las plantas usan luz, agua y dióxido de carbono. ¿Qué producen?",
            options=[
                "Glucosa y oxígeno",
                "Dióxido de carbono y agua",
                "Solo agua",
                "Nitrógeno y sal",
            ],
            correct="Glucosa y oxígeno",
            explanation=(
                "La planta fabrica su alimento (glucosa) y libera oxígeno. Dióxido de "
                "carbono y agua son justo lo que usa, no lo que produce: es la trampa de "
                "invertir el proceso."
            ),
        ),
        item(
            "s11-cie-6", habilidad="s11_ciencias", nivel=F,
            question="Se mezclaron por error arena y limaduras de hierro. ¿Cuál es la forma más sencilla de separarlas?",
            options=["Con un imán", "Filtrando", "Evaporando", "Destilando"],
            correct="Con un imán",
            explanation=(
                "El hierro es atraído por el imán y la arena no. Filtrar sirve para "
                "separar un sólido de un líquido, pero aquí los dos son sólidos; evaporar "
                "y destilar sirven para mezclas con líquidos."
            ),
        ),
        item(
            "s11-cie-7", habilidad="s11_ciencias", nivel=F,
            question="Una ciclista recorre 30 km en 2 horas a ritmo constante. ¿Cuál es su velocidad?",
            options=["15 km/h", "60 km/h", "32 km/h", "28 km/h"],
            correct="15 km/h",
            explanation=(
                "Velocidad = distancia ÷ tiempo = 30 ÷ 2 = 15 km/h. 60 sale de "
                "multiplicar en vez de dividir, y 32 y 28 de sumar o restar."
            ),
        ),
        item(
            "s11-cie-8", habilidad="s11_ciencias", nivel=I,
            question="Un estudiante mide cuánto tarda en disolverse una cucharada de azúcar en agua a distintas temperaturas: a 20 °C tarda 60 s; a 40 °C, 35 s; a 60 °C, 20 s. ¿Qué conclusión apoyan los datos?",
            options=[
                "A mayor temperatura del agua, el azúcar se disuelve más rápido.",
                "El azúcar no se disuelve en agua fría.",
                "La temperatura no influye en cómo se disuelve el azúcar.",
                "A mayor temperatura, el azúcar se disuelve más lento.",
            ],
            correct="A mayor temperatura del agua, el azúcar se disuelve más rápido.",
            explanation=(
                "Cuando la temperatura sube, el tiempo baja: se disuelve más rápido. A "
                "20 °C sí se disuelve, solo que tarda más, así que la segunda opción "
                "exagera. La cuarta lee la tabla al revés."
            ),
        ),
        item(
            "s11-cie-9", habilidad="s11_ciencias", nivel=I,
            question="Con los mismos datos del azúcar (60 s a 20 °C, 35 s a 40 °C y 20 s a 60 °C), ¿cuánto esperarías que tarde a 50 °C?",
            options=["Entre 20 y 35 segundos", "Más de 60 segundos", "Menos de 20 segundos", "Exactamente 50 segundos"],
            correct="Entre 20 y 35 segundos",
            explanation=(
                "50 °C está entre 40 °C y 60 °C, así que lo razonable es un tiempo entre "
                "35 y 20 segundos. Es interpolar: estimar dentro del rango que ya se "
                "midió. «50 segundos» confunde la temperatura con el tiempo."
            ),
        ),
        item(
            "s11-cie-10", habilidad="s11_ciencias", nivel=I,
            question="Una hoja de papel extendida y otra igual, arrugada en forma de bola, se sueltan desde la misma altura. La arrugada llega primero al suelo. ¿Por qué?",
            options=[
                "Porque el aire opone más resistencia a la hoja extendida.",
                "Porque la hoja extendida pesa menos.",
                "Porque la gravedad no actúa sobre la hoja extendida.",
                "Porque la bola de papel tiene más masa.",
            ],
            correct="Porque el aire opone más resistencia a la hoja extendida.",
            explanation=(
                "Las dos hojas tienen la misma masa (son iguales) y la gravedad actúa "
                "igual sobre ambas. Lo que cambia es la forma: extendida, choca con más "
                "aire y se frena más."
            ),
        ),
        item(
            "s11-cie-11", habilidad="s11_ciencias", nivel=I,
            question="Un indicador se pone rojo con los ácidos y azul con las bases. En jugo de limón se pone rojo y en agua con jabón se pone azul. ¿Qué se puede concluir?",
            options=[
                "El jugo de limón es ácido y el agua con jabón es básica.",
                "Los dos son ácidos.",
                "El jugo de limón es básico y el agua con jabón es ácida.",
                "El indicador no sirve para nada.",
            ],
            correct="El jugo de limón es ácido y el agua con jabón es básica.",
            explanation=(
                "Se aplica la regla que da el enunciado: rojo es ácido, azul es básico. "
                "La tercera opción invierte la regla, que es el error típico cuando se "
                "lee rápido."
            ),
        ),
        item(
            "s11-cie-12", habilidad="s11_ciencias", nivel=I,
            question="¿Cómo protege una vacuna contra una enfermedad?",
            options=[
                "Prepara al sistema inmunológico para reconocer al microorganismo sin causar la enfermedad.",
                "Mata directamente todos los virus que hay en el cuerpo.",
                "Funciona como un antibiótico.",
                "Reemplaza a los glóbulos blancos.",
            ],
            correct="Prepara al sistema inmunológico para reconocer al microorganismo sin causar la enfermedad.",
            explanation=(
                "La vacuna «entrena» las defensas: si después llega el microorganismo, el "
                "cuerpo lo reconoce y responde más rápido. No mata virus por sí misma, y "
                "los antibióticos actúan contra bacterias, no son vacunas."
            ),
        ),
        item(
            "s11-cie-13", habilidad="s11_ciencias", nivel=I,
            question="Un panel solar transforma:",
            options=[
                "energía luminosa en energía eléctrica.",
                "energía eléctrica en energía luminosa.",
                "energía química en calor.",
                "energía del viento en electricidad.",
            ],
            correct="energía luminosa en energía eléctrica.",
            explanation=(
                "Recibe la luz del sol y produce electricidad. Un bombillo hace lo "
                "contrario (la segunda opción), y la energía del viento la aprovecha un "
                "aerogenerador, no un panel solar."
            ),
        ),
        item(
            "s11-cie-14", habilidad="s11_ciencias", nivel=I,
            question="Camila nota que el pan se llena de moho más rápido en la cocina que en la nevera. ¿Qué hipótesis podría poner a prueba?",
            options=[
                "El frío hace más lento el crecimiento del moho.",
                "El moho es malo para la salud.",
                "La nevera gasta mucha energía.",
                "El pan de la tienda es mejor que el de la casa.",
            ],
            correct="El frío hace más lento el crecimiento del moho.",
            explanation=(
                "Una hipótesis propone una explicación de lo observado que se puede "
                "comprobar con un experimento. Las otras opciones pueden ser ciertas o "
                "no, pero no explican por qué el moho crece distinto en los dos lugares."
            ),
        ),
        item(
            "s11-cie-15", habilidad="s11_ciencias", nivel=A,
            question="Para poner a prueba que el frío frena el moho, ¿qué experimento sirve mejor?",
            options=[
                "Dejar trozos del mismo pan, del mismo día, unos en la nevera y otros en la cocina, y anotar cuándo aparece el moho en cada uno.",
                "Dejar un pan blanco en la nevera y uno integral en la cocina.",
                "Preguntarles a los vecinos dónde guardan el pan.",
                "Dejar un solo trozo de pan en la nevera y ver qué pasa.",
            ],
            correct="Dejar trozos del mismo pan, del mismo día, unos en la nevera y otros en la cocina, y anotar cuándo aparece el moho en cada uno.",
            explanation=(
                "Solo cambia la temperatura; el pan es el mismo. En la segunda opción "
                "cambian dos cosas a la vez (lugar y tipo de pan), así que no se sabría "
                "cuál causó la diferencia. La cuarta no tiene con qué comparar."
            ),
        ),
        item(
            "s11-cie-16", habilidad="s11_ciencias", nivel=A,
            question="Se quema un trozo de papel dentro de un recipiente completamente cerrado. Al final, la masa del recipiente con todo lo que tiene adentro es:",
            options=[
                "igual a la del comienzo.",
                "menor, porque la ceniza pesa menos que el papel.",
                "mayor, porque el fuego agrega materia.",
                "cero, porque el papel desapareció.",
            ],
            correct="igual a la del comienzo.",
            explanation=(
                "En un recipiente cerrado la materia no sale ni entra: el papel se "
                "transforma en ceniza y gases, pero todo queda adentro. La ceniza sí pesa "
                "menos que el papel (esa es la trampa), pero la diferencia está en los "
                "gases, que siguen en el recipiente."
            ),
        ),
        item(
            "s11-cie-17", habilidad="s11_ciencias", nivel=A,
            question="En una planta, el color morado (M) es dominante sobre el blanco (m). Si se cruzan dos plantas Mm, ¿qué proporción de las plantas hijas se espera que sea blanca?",
            options=["1 de cada 4", "1 de cada 2", "3 de cada 4", "Ninguna"],
            correct="1 de cada 4",
            explanation=(
                "Las combinaciones posibles son MM, Mm, mM y mm. Solo mm es blanca: 1 de "
                "cada 4. «Ninguna» es la trampa de pensar que, como los padres son "
                "morados, los hijos también lo serán; los dos llevan el alelo m."
            ),
        ),
        item(
            "s11-cie-18", habilidad="s11_ciencias", nivel=A,
            question="Un objeto tiene una masa de 200 g y ocupa 250 cm³. La densidad del agua es 1 g/cm³. ¿Flota en el agua?",
            options=[
                "Sí, porque su densidad (0,8 g/cm³) es menor que la del agua.",
                "No, porque pesa 200 g.",
                "No, porque su densidad es 1,25 g/cm³.",
                "Sí, porque ocupa mucho espacio.",
            ],
            correct="Sí, porque su densidad (0,8 g/cm³) es menor que la del agua.",
            explanation=(
                "Densidad = masa ÷ volumen = 200 ÷ 250 = 0,8 g/cm³, menor que la del "
                "agua, así que flota. 1,25 sale de dividir al revés. Que flote no depende "
                "solo de la masa ni solo del volumen, sino de la relación entre los dos."
            ),
        ),
        item(
            "s11-cie-19", habilidad="s11_ciencias", nivel=A,
            question="Un estudio encuentra que en los meses en que se venden más helados también hay más accidentes en piscinas. ¿Qué explicación es más razonable?",
            options=[
                "Las dos cosas aumentan con el calor: hace más calor, se venden más helados y más gente va a las piscinas.",
                "Comer helado causa accidentes en las piscinas.",
                "Los accidentes en piscinas hacen que la gente compre helado.",
                "Los datos tienen que estar equivocados.",
            ],
            correct="Las dos cosas aumentan con el calor: hace más calor, se venden más helados y más gente va a las piscinas.",
            explanation=(
                "Que dos cosas aumenten juntas no significa que una cause la otra: aquí "
                "hay un tercer factor, el calor, que explica las dos. Concluir causa a "
                "partir de una coincidencia es uno de los errores más comunes al leer "
                "datos."
            ),
        ),
        item(
            "s11-cie-20", habilidad="s11_ciencias", nivel=A,
            question="Un agricultor usa un insecticida que también mata a las abejas de la zona. ¿Qué efecto es más probable en sus cultivos de fruta?",
            options=[
                "Menos frutos, porque habrá menos polinización.",
                "Más frutos, porque habrá menos insectos.",
                "Ningún efecto, porque las abejas no tienen relación con las plantas.",
                "Plantas más altas.",
            ],
            correct="Menos frutos, porque habrá menos polinización.",
            explanation=(
                "Muchas plantas necesitan a las abejas para polinizar sus flores, y sin "
                "polinización no hay fruto. La segunda opción ve solo el objetivo del "
                "insecticida y olvida que las abejas también son insectos."
            ),
        ),
    ]

    # --- Inglés (tanda 3) ---------------------------------------------------
    # Enunciados en inglés (la prueba se presenta en inglés) y explicaciones en
    # español, como el resto del banco. Distintos de los del Pre IELTS: aquí el
    # nivel es el de un bachiller, con avisos, vocabulario cotidiano, gramática
    # en contexto y un texto corto.
    ingles = [
        item(
            "s11-ing-1", habilidad="s11_ingles", nivel=F,
            question="What does this sign mean?\n\nNO FOOD OR DRINKS IN THE LAB",
            options=[
                "You can't eat or drink in the lab.",
                "You can buy food in the lab.",
                "The lab sells drinks.",
                "You must bring food to the lab.",
            ],
            correct="You can't eat or drink in the lab.",
            explanation=(
                "«NO FOOD OR DRINKS» es una prohibición: no se puede comer ni beber. "
                "Las otras opciones reconocen las palabras «food» y «drinks», pero "
                "ignoran el «NO», que es lo que cambia todo el sentido."
            ),
        ),
        item(
            "s11-ing-2", habilidad="s11_ingles", nivel=F,
            question="What does this sign mean?\n\nPLEASE KEEP THE DOOR CLOSED",
            options=[
                "Don't leave the door open.",
                "The door is broken.",
                "Knock before you open the door.",
                "The door is always open.",
            ],
            correct="Don't leave the door open.",
            explanation=(
                "«Keep the door closed» es «mantén la puerta cerrada», o sea, no la dejes "
                "abierta. El aviso no dice que esté dañada ni pide tocar antes de entrar."
            ),
        ),
        item(
            "s11-ing-3", habilidad="s11_ingles", nivel=F,
            question="Where would you see this sign?\n\nCAUTION: WET FLOOR",
            options=[
                "In a place where the floor was just cleaned.",
                "At a swimming competition, to announce the winner.",
                "In a shop that sells floors.",
                "At the entrance of a library, to ask for silence.",
            ],
            correct="In a place where the floor was just cleaned.",
            explanation=(
                "«Wet floor» es «piso mojado», y «caution», «cuidado»: avisa que te puedes "
                "resbalar, por ejemplo después de trapear. «Wet» se asocia con agua y por "
                "eso la competencia de natación es la trampa, pero el aviso habla del "
                "piso."
            ),
        ),
        item(
            "s11-ing-4", habilidad="s11_ingles", nivel=F,
            question="Where can you borrow books for free?",
            options=["In a library", "In a bookshop", "In a bakery", "In a pharmacy"],
            correct="In a library",
            explanation=(
                "«Library» es biblioteca, donde se prestan libros. «Bookshop» es librería, "
                "donde se compran: es un falso amigo clásico, porque «library» se parece "
                "a «librería» y no significa lo mismo."
            ),
        ),
        item(
            "s11-ing-5", habilidad="s11_ingles", nivel=F,
            question="Choose the correct option.\n\nMy sister ______ to school by bike every day.",
            options=["goes", "go", "going", "gone"],
            correct="goes",
            explanation=(
                "Con «my sister» (she) en presente simple, el verbo lleva -s: «goes». "
                "«Every day» confirma que es una rutina, así que es presente simple. "
                "«Going» y «gone» necesitarían un auxiliar."
            ),
        ),
        item(
            "s11-ing-6", habilidad="s11_ingles", nivel=F,
            question="Choose the correct option.\n\nThere ______ two apples on the table.",
            options=["are", "is", "be", "am"],
            correct="are",
            explanation=(
                "«There are» va con plural (two apples); «there is», con singular (an "
                "apple). En español se dice «hay» en los dos casos, y por eso se "
                "confunden."
            ),
        ),
        item(
            "s11-ing-7", habilidad="s11_ingles", nivel=F,
            question="Choose the best word.\n\nMy uncle is a ______. He works in a hospital and takes care of sick people.",
            options=["nurse", "pilot", "farmer", "chef"],
            correct="nurse",
            explanation=(
                "La segunda frase da la pista: trabaja en un hospital y cuida enfermos. "
                "«Nurse» es enfermero o enfermera. Los demás son piloto, agricultor y "
                "cocinero."
            ),
        ),
        item(
            "s11-ing-8", habilidad="s11_ingles", nivel=I,
            question="Choose the correct option.\n\nYesterday we ______ a movie at home.",
            options=["watched", "watch", "watching", "will watch"],
            correct="watched",
            explanation=(
                "«Yesterday» marca el pasado: «watched». «Will watch» es futuro y "
                "choca con «yesterday». Las palabras de tiempo (yesterday, tomorrow, "
                "every day) casi siempre deciden la respuesta."
            ),
        ),
        item(
            "s11-ing-9", habilidad="s11_ingles", nivel=I,
            question="Choose the correct option.\n\nThis exercise is ______ than the last one.",
            options=["easier", "more easy", "easiest", "easy"],
            correct="easier",
            explanation=(
                "Con «than» va comparativo. «Easy» es corto, así que se forma con -er "
                "(y la y cambia a i): «easier». «More easy» mezcla las dos formas, y "
                "«easiest» es superlativo, que no va con «than»."
            ),
        ),
        item(
            "s11-ing-10", habilidad="s11_ingles", nivel=I,
            question="Choose the correct option.\n\nOur English class starts ______ seven o'clock.",
            options=["at", "in", "on", "for"],
            correct="at",
            explanation=(
                "Para una hora exacta se usa «at» (at seven o'clock). «In» va con meses y "
                "años (in May), y «on» con días (on Monday). En español todo es «a» o "
                "«en», por eso cuesta."
            ),
        ),
        item(
            "s11-ing-11", habilidad="s11_ingles", nivel=I,
            question="Choose the correct option.\n\nI ______ never been to the beach.",
            options=["have", "has", "am", "did"],
            correct="have",
            explanation=(
                "«Been» pide el auxiliar «have» o «has» (present perfect). Con «I» es «have»; «has» "
                "es para he, she o it. «Am» y «did» no forman este tiempo."
            ),
        ),
        item(
            "s11-ing-12", habilidad="s11_ingles", nivel=I,
            question="Choose the best word.\n\nI'm really tired, so I'm going to bed ______ tonight.",
            options=["early", "late", "slowly", "loudly"],
            correct="early",
            explanation=(
                "«So» indica consecuencia: si estoy cansado, me acuesto temprano "
                "(«early»). «Late» dice lo contrario de lo que el cansancio sugiere, y "
                "«slowly» y «loudly» no tienen relación con la idea."
            ),
        ),
        item(
            "s11-ing-13", habilidad="s11_ingles", nivel=I, passage="s11_coffee_trip",
            question="What was difficult about picking the coffee fruit?",
            options=[
                "The plants grow on steep hills.",
                "The fruit was green.",
                "It was raining all morning.",
                "The farmer didn't help them.",
            ],
            correct="The plants grow on steep hills.",
            explanation=(
                "Laura dice que fue más difícil de lo que esperaba «because the plants "
                "grow on steep hills» (en lomas empinadas). La lluvia llegó en la tarde, "
                "no en la mañana, y el texto dice que el fruto es rojo."
            ),
        ),
        item(
            "s11-ing-14", habilidad="s11_ingles", nivel=I, passage="s11_coffee_trip",
            question="Why didn't the class visit the river?",
            options=[
                "Because it started to rain.",
                "Because they were too tired.",
                "Because the bus left early.",
                "Because the teacher was sick.",
            ],
            correct="Because it started to rain.",
            explanation=(
                "«In the afternoon it started to rain, so we couldn't visit the river»: "
                "«so» une la causa (la lluvia) con la consecuencia (no ir al río). El "
                "cansancio aparece en el texto, pero en el bus, por la mañana."
            ),
        ),
        item(
            "s11-ing-15", habilidad="s11_ingles", nivel=A, passage="s11_coffee_trip",
            question="In «I'm a bit sad about that», what does «that» refer to?",
            options=[
                "Not visiting the river",
                "Picking the coffee fruit",
                "Buying coffee for her parents",
                "Leaving at six in the morning",
            ],
            correct="Not visiting the river",
            explanation=(
                "«That» retoma lo que se acaba de decir: que no pudieron ir al río. "
                "Después Laura dice que pueden volver el próximo año, lo que confirma "
                "que le dio tristeza perderse esa parte. Las palabras como «that» o «it» "
                "casi siempre se refieren a la idea inmediatamente anterior."
            ),
        ),
        item(
            "s11-ing-16", habilidad="s11_ingles", nivel=A, passage="s11_coffee_trip",
            question="What can we infer about the trip?",
            options=[
                "Laura enjoyed it, even though not everything went as planned.",
                "Laura didn't like the trip at all.",
                "The class visited the river in the afternoon.",
                "Laura's parents went on the trip too.",
            ],
            correct="Laura enjoyed it, even though not everything went as planned.",
            explanation=(
                "Dice que fue «amazing», pero que no pudieron ir al río: le gustó, aunque "
                "no todo salió como se esperaba. La segunda opción contradice «amazing», "
                "la tercera contradice lo de la lluvia, y los papás no fueron (les llevó "
                "café)."
            ),
        ),
        item(
            "s11-ing-17", habilidad="s11_ingles", nivel=A, passage="s11_coffee_trip",
            question="Which statement is TRUE according to the email?",
            options=[
                "A farmer explained how coffee grows.",
                "Laura bought coffee for her teacher.",
                "The class left at six in the evening.",
                "The teacher said they can never go back.",
            ],
            correct="A farmer explained how coffee grows.",
            explanation=(
                "«A farmer showed us how coffee grows». Cada una de las otras cambia un "
                "detalle del texto: el café era para sus papás, salieron a las seis de la "
                "mañana y la profesora dijo que sí pueden volver. Esta pregunta premia "
                "leer los detalles."
            ),
        ),
        item(
            "s11-ing-18", habilidad="s11_ingles", nivel=A,
            question="Choose the correct option.\n\nIf it rains tomorrow, we ______ the trip.",
            options=["will cancel", "would cancel", "cancelled", "cancelling"],
            correct="will cancel",
            explanation=(
                "Es una condición posible en el futuro («if it rains tomorrow»): «if» + "
                "presente, y en la otra parte «will». «Would cancel» es para algo "
                "hipotético («if it rained…»), y las otras dos no completan la oración."
            ),
        ),
        item(
            "s11-ing-19", habilidad="s11_ingles", nivel=A,
            question="Choose the correct option.\n\nThis bridge ______ in 1950.",
            options=["was built", "built", "is build", "has build"],
            correct="was built",
            explanation=(
                "El puente no construyó nada: lo construyeron. Eso es voz pasiva: «was» + "
                "participio («built»). «Built» solo diría que el puente construyó algo, y "
                "«is build» y «has build» usan el verbo sin participio."
            ),
        ),
        item(
            "s11-ing-20", habilidad="s11_ingles", nivel=A,
            question="Choose the correct option.\n\nThe girl ______ won the science prize is my cousin.",
            options=["who", "which", "where", "whose"],
            correct="who",
            explanation=(
                "Para una persona que hace la acción (ella ganó el premio) se usa «who». "
                "«Which» es para cosas, «where» para lugares, y «whose» indica posesión "
                "(«the girl whose brother…»)."
            ),
        ),
    ]

    return [*lectura, *matematicas, *sociales, *ciencias, *ingles]
