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

    return [*lectura, *matematicas]
