VOCATIONAL_TESTS = [
    {
        "id": "holland",
        "slug": "holland",
        "name": "Test de Intereses Vocacionales Holland (RIASEC)",
        "shortName": "Holland RIASEC",
        "description": "Descubre tus intereses vocacionales a traves de las 6 categorias Holland: Realista, Investigador, Artistico, Social, Emprendedor y Convencional.",
        "academicBasis": "Desarrollado por John Holland en 1959, es el modelo mas utilizado en orientacion vocacional. Base del O*NET Interest Profiler del Departamento de Trabajo de EE.UU.",
        "estimatedMinutes": 15,
        "questionCount": 48,
        "icon": "hexagon",
        "questions": [
            {"id": "h-r-1", "text": "Me gusta trabajar con herramientas y maquinaria", "type": "likert", "category": "R"},
            {"id": "h-r-2", "text": "Prefiero actividades al aire libre", "type": "likert", "category": "R"},
            {"id": "h-r-3", "text": "Disfruto reparar cosas con mis manos", "type": "likert", "category": "R"},
            {"id": "h-r-4", "text": "Me gusta trabajar con plantas o animales", "type": "likert", "category": "R"},
            {"id": "h-r-5", "text": "Prefiero actividades físicas sobre trabajos de escritorio", "type": "likert", "category": "R"},
            {"id": "h-r-6", "text": "Me gusta construir o armar cosas", "type": "likert", "category": "R"},
            {"id": "h-r-7", "text": "Disfruto operar vehiculos o maquinaria pesada", "type": "likert", "category": "R"},
            {"id": "h-r-8", "text": "Me siento comodo trabajando con materiales como madera, metal o tela", "type": "likert", "category": "R"},
            {"id": "h-i-1", "text": "Me gusta analizar problemas complejos", "type": "likert", "category": "I"},
            {"id": "h-i-2", "text": "Disfruto leer sobre temas cientificos", "type": "likert", "category": "I"},
            {"id": "h-i-3", "text": "Prefiero entender el por que de las cosas", "type": "likert", "category": "I"},
            {"id": "h-i-4", "text": "Me gusta resolver rompecabezas y acertijos", "type": "likert", "category": "I"},
            {"id": "h-i-5", "text": "Disfruto investigar temas a profundidad", "type": "likert", "category": "I"},
            {"id": "h-i-6", "text": "Me interesan las matematicas y la logica", "type": "likert", "category": "I"},
            {"id": "h-i-7", "text": "Prefiero trabajar con datos y hechos", "type": "likert", "category": "I"},
            {"id": "h-i-8", "text": "Me gusta experimentar y probar hipotesis", "type": "likert", "category": "I"},
            {"id": "h-a-1", "text": "Tengo una imaginacion muy activa", "type": "likert", "category": "A"},
            {"id": "h-a-2", "text": "Me gusta expresarme a traves del arte o la musica", "type": "likert", "category": "A"},
            {"id": "h-a-3", "text": "Prefiero trabajar sin reglas estrictas", "type": "likert", "category": "A"},
            {"id": "h-a-4", "text": "Disfruto crear cosas nuevas y originales", "type": "likert", "category": "A"},
            {"id": "h-a-5", "text": "Me gusta la escritura creativa o la poesia", "type": "likert", "category": "A"},
            {"id": "h-a-6", "text": "Aprecio la belleza estetica en mi entorno", "type": "likert", "category": "A"},
            {"id": "h-a-7", "text": "Me gusta el diseno grafico o la fotografia", "type": "likert", "category": "A"},
            {"id": "h-a-8", "text": "Prefiero ambientes de trabajo creativos y no convencionales", "type": "likert", "category": "A"},
            {"id": "h-s-1", "text": "Me gusta ayudar a los demas", "type": "likert", "category": "S"},
            {"id": "h-s-2", "text": "Disfruto ensenar o explicar cosas a otros", "type": "likert", "category": "S"},
            {"id": "h-s-3", "text": "Prefiero trabajar en equipo", "type": "likert", "category": "S"},
            {"id": "h-s-4", "text": "Me interesa el bienestar de otras personas", "type": "likert", "category": "S"},
            {"id": "h-s-5", "text": "Disfruto escuchar los problemas de otros", "type": "likert", "category": "S"},
            {"id": "h-s-6", "text": "Me gusta participar en actividades comunitarias", "type": "likert", "category": "S"},
            {"id": "h-s-7", "text": "Prefiero profesiones donde pueda hacer una diferencia social", "type": "likert", "category": "S"},
            {"id": "h-s-8", "text": "Me siento satisfecho cuando ayudo a alguien a resolver un problema", "type": "likert", "category": "S"},
            {"id": "h-e-1", "text": "Me gusta liderar proyectos o grupos", "type": "likert", "category": "E"},
            {"id": "h-e-2", "text": "Disfruto persuadir a otros", "type": "likert", "category": "E"},
            {"id": "h-e-3", "text": "Prefiero tomar la iniciativa", "type": "likert", "category": "E"},
            {"id": "h-e-4", "text": "Me gusta negociar y hacer tratos", "type": "likert", "category": "E"},
            {"id": "h-e-5", "text": "Disfruto competir y ganar", "type": "likert", "category": "E"},
            {"id": "h-e-6", "text": "Me interesa el mundo de los negocios", "type": "likert", "category": "E"},
            {"id": "h-e-7", "text": "Prefiero tener influencia sobre otros", "type": "likert", "category": "E"},
            {"id": "h-e-8", "text": "Me gusta asumir riesgos calculados", "type": "likert", "category": "E"},
            {"id": "h-c-1", "text": "Soy muy organizado/a", "type": "likert", "category": "C"},
            {"id": "h-c-2", "text": "Me gustan las tareas con procedimientos claros", "type": "likert", "category": "C"},
            {"id": "h-c-3", "text": "Prefiero trabajar con numeros y datos", "type": "likert", "category": "C"},
            {"id": "h-c-4", "text": "Disfruto mantener registros y archivos ordenados", "type": "likert", "category": "C"},
            {"id": "h-c-5", "text": "Me gusta seguir instrucciones precisas", "type": "likert", "category": "C"},
            {"id": "h-c-6", "text": "Prefiero la estabilidad y la rutina", "type": "likert", "category": "C"},
            {"id": "h-c-7", "text": "Me siento comodo con tareas administrativas", "type": "likert", "category": "C"},
            {"id": "h-c-8", "text": "Disfruto verificar detalles y asegurar precision", "type": "likert", "category": "C"},
        ],
    },
    {
        "id": "bigfive",
        "slug": "bigfive",
        "name": "Test de Personalidad Big Five (OCEAN)",
        "shortName": "Big Five",
        "description": "Evalua las 5 dimensiones fundamentales de la personalidad: Apertura, Responsabilidad, Extraversion, Amabilidad y Neuroticismo.",
        "academicBasis": "El modelo de los Cinco Grandes es el mas aceptado en psicologia de la personalidad, validado en miles de estudios academicos y predictor comprobado de exito laboral.",
        "estimatedMinutes": 12,
        "questionCount": 50,
        "icon": "radar",
        "questions": [
            {"id": "bf-o-1", "text": "Tengo una imaginacion muy activa", "type": "likert", "category": "O"},
            {"id": "bf-o-2", "text": "Me interesan las ideas abstractas", "type": "likert", "category": "O"},
            {"id": "bf-o-3", "text": "Disfruto experimentar cosas nuevas", "type": "likert", "category": "O"},
            {"id": "bf-o-4", "text": "Me gusta reflexionar sobre temas filosoficos", "type": "likert", "category": "O"},
            {"id": "bf-o-5", "text": "Aprecio el arte y la belleza", "type": "likert", "category": "O"},
            {"id": "bf-o-6", "text": "Prefiero la variedad sobre la rutina", "type": "likert", "category": "O"},
            {"id": "bf-o-7", "text": "Tengo un vocabulario amplio", "type": "likert", "category": "O"},
            {"id": "bf-o-8", "text": "Me gusta aprender sobre diferentes culturas", "type": "likert", "category": "O"},
            {"id": "bf-o-9", "text": "Tengo dificultad entendiendo ideas abstractas", "type": "likert", "category": "O", "reversed": True},
            {"id": "bf-o-10", "text": "No me interesa el arte", "type": "likert", "category": "O", "reversed": True},
            {"id": "bf-c-1", "text": "Siempre estoy preparado/a", "type": "likert", "category": "C"},
            {"id": "bf-c-2", "text": "Presto atencion a los detalles", "type": "likert", "category": "C"},
            {"id": "bf-c-3", "text": "Hago mis tareas inmediatamente", "type": "likert", "category": "C"},
            {"id": "bf-c-4", "text": "Me gusta el orden", "type": "likert", "category": "C"},
            {"id": "bf-c-5", "text": "Sigo mis planes rigurosamente", "type": "likert", "category": "C"},
            {"id": "bf-c-6", "text": "Trabajo duro para lograr mis metas", "type": "likert", "category": "C"},
            {"id": "bf-c-7", "text": "Dejo mis cosas tiradas", "type": "likert", "category": "C", "reversed": True},
            {"id": "bf-c-8", "text": "A menudo olvido poner las cosas en su lugar", "type": "likert", "category": "C", "reversed": True},
            {"id": "bf-c-9", "text": "Postergo las tareas importantes", "type": "likert", "category": "C", "reversed": True},
            {"id": "bf-c-10", "text": "Me cuesta seguir horarios", "type": "likert", "category": "C", "reversed": True},
            {"id": "bf-e-1", "text": "Soy el alma de las fiestas", "type": "likert", "category": "E"},
            {"id": "bf-e-2", "text": "Me siento comodo con la gente", "type": "likert", "category": "E"},
            {"id": "bf-e-3", "text": "Inicio conversaciones facilmente", "type": "likert", "category": "E"},
            {"id": "bf-e-4", "text": "Hablo con muchas personas diferentes en fiestas", "type": "likert", "category": "E"},
            {"id": "bf-e-5", "text": "No me molesta ser el centro de atencion", "type": "likert", "category": "E"},
            {"id": "bf-e-6", "text": "Tengo poco que decir", "type": "likert", "category": "E", "reversed": True},
            {"id": "bf-e-7", "text": "Me mantengo en segundo plano", "type": "likert", "category": "E", "reversed": True},
            {"id": "bf-e-8", "text": "No hablo mucho", "type": "likert", "category": "E", "reversed": True},
            {"id": "bf-e-9", "text": "No me gusta llamar la atencion", "type": "likert", "category": "E", "reversed": True},
            {"id": "bf-e-10", "text": "Me siento incomodo en grupos grandes", "type": "likert", "category": "E", "reversed": True},
            {"id": "bf-a-1", "text": "Me intereso por los demas", "type": "likert", "category": "A"},
            {"id": "bf-a-2", "text": "Siento empatia por los sentimientos de otros", "type": "likert", "category": "A"},
            {"id": "bf-a-3", "text": "Tengo un corazon blando", "type": "likert", "category": "A"},
            {"id": "bf-a-4", "text": "Me tomo tiempo para los demas", "type": "likert", "category": "A"},
            {"id": "bf-a-5", "text": "Hago sentir bien a los demas", "type": "likert", "category": "A"},
            {"id": "bf-a-6", "text": "No me interesa mucho los problemas de otros", "type": "likert", "category": "A", "reversed": True},
            {"id": "bf-a-7", "text": "Insulto a la gente", "type": "likert", "category": "A", "reversed": True},
            {"id": "bf-a-8", "text": "No me interesan los sentimientos ajenos", "type": "likert", "category": "A", "reversed": True},
            {"id": "bf-a-9", "text": "Soy duro/a en mis opiniones sobre los demas", "type": "likert", "category": "A", "reversed": True},
            {"id": "bf-a-10", "text": "Critico frecuentemente a los demas", "type": "likert", "category": "A", "reversed": True},
            {"id": "bf-n-1", "text": "Me estreso facilmente", "type": "likert", "category": "N"},
            {"id": "bf-n-2", "text": "Me preocupo por las cosas", "type": "likert", "category": "N"},
            {"id": "bf-n-3", "text": "Me perturbo facilmente", "type": "likert", "category": "N"},
            {"id": "bf-n-4", "text": "Mis emociones cambian frecuentemente", "type": "likert", "category": "N"},
            {"id": "bf-n-5", "text": "Me siento ansioso/a a menudo", "type": "likert", "category": "N"},
            {"id": "bf-n-6", "text": "Estoy relajado/a la mayor parte del tiempo", "type": "likert", "category": "N", "reversed": True},
            {"id": "bf-n-7", "text": "Rara vez me siento triste", "type": "likert", "category": "N", "reversed": True},
            {"id": "bf-n-8", "text": "Manejo bien la presion", "type": "likert", "category": "N", "reversed": True},
            {"id": "bf-n-9", "text": "Mantengo la calma en situaciones dificiles", "type": "likert", "category": "N", "reversed": True},
            {"id": "bf-n-10", "text": "Me recupero rapidamente de las dificultades", "type": "likert", "category": "N", "reversed": True},
        ],
    },
    {
        "id": "values",
        "slug": "values",
        "name": "Test de Valores Laborales",
        "shortName": "Valores",
        "description": "Identifica los valores fundamentales que buscas en tu carrera: Logro, Independencia, Reconocimiento, Relaciones, Apoyo y Condiciones laborales.",
        "academicBasis": "Basado en el Work Values Inventory, complementa los intereses con motivaciones y es util para alinear valores personales con la cultura organizacional.",
        "estimatedMinutes": 8,
        "questionCount": 30,
        "icon": "heart",
        "questions": [
            {"id": "v-lo-1", "text": "Es importante para mi usar mis mejores habilidades en el trabajo", "type": "likert", "category": "logro"},
            {"id": "v-lo-2", "text": "Valoro las oportunidades de crecimiento profesional", "type": "likert", "category": "logro"},
            {"id": "v-lo-3", "text": "Quiero un trabajo que me de sentido de logro", "type": "likert", "category": "logro"},
            {"id": "v-lo-4", "text": "Busco trabajo donde pueda ver resultados tangibles", "type": "likert", "category": "logro"},
            {"id": "v-lo-5", "text": "Me motiva superar desafios dificiles", "type": "likert", "category": "logro"},
            {"id": "v-in-1", "text": "Valoro poder tomar mis propias decisiones en el trabajo", "type": "likert", "category": "independencia"},
            {"id": "v-in-2", "text": "Prefiero trabajar sin supervision constante", "type": "likert", "category": "independencia"},
            {"id": "v-in-3", "text": "Es importante para mi tener flexibilidad en como hago mi trabajo", "type": "likert", "category": "independencia"},
            {"id": "v-in-4", "text": "Valoro la creatividad y la innovacion en mi trabajo", "type": "likert", "category": "independencia"},
            {"id": "v-in-5", "text": "Prefiero definir mis propios objetivos laborales", "type": "likert", "category": "independencia"},
            {"id": "v-re-1", "text": "Es importante que mi trabajo sea reconocido", "type": "likert", "category": "reconocimiento"},
            {"id": "v-re-2", "text": "Valoro tener oportunidades de ascenso", "type": "likert", "category": "reconocimiento"},
            {"id": "v-re-3", "text": "Quiero un trabajo con prestigio social", "type": "likert", "category": "reconocimiento"},
            {"id": "v-re-4", "text": "Me importa tener un titulo o posicion respetada", "type": "likert", "category": "reconocimiento"},
            {"id": "v-re-5", "text": "Busco trabajo donde pueda ganar respeto de otros", "type": "likert", "category": "reconocimiento"},
            {"id": "v-rl-1", "text": "Valoro tener buenos companeros de trabajo", "type": "likert", "category": "relaciones"},
            {"id": "v-rl-2", "text": "Es importante para mi ayudar a otros en mi trabajo", "type": "likert", "category": "relaciones"},
            {"id": "v-rl-3", "text": "Prefiero trabajar en equipo que solo", "type": "likert", "category": "relaciones"},
            {"id": "v-rl-4", "text": "Valoro un ambiente de trabajo amigable", "type": "likert", "category": "relaciones"},
            {"id": "v-rl-5", "text": "Quiero un trabajo donde pueda hacer una diferencia en la vida de otros", "type": "likert", "category": "relaciones"},
            {"id": "v-ap-1", "text": "Valoro tener un jefe que me apoye", "type": "likert", "category": "apoyo"},
            {"id": "v-ap-2", "text": "Es importante tener politicas de empresa justas", "type": "likert", "category": "apoyo"},
            {"id": "v-ap-3", "text": "Prefiero empresas que capaciten a sus empleados", "type": "likert", "category": "apoyo"},
            {"id": "v-ap-4", "text": "Valoro recibir retroalimentacion constructiva", "type": "likert", "category": "apoyo"},
            {"id": "v-ap-5", "text": "Es importante para mi tener mentores o guias en el trabajo", "type": "likert", "category": "apoyo"},
            {"id": "v-co-1", "text": "La seguridad laboral es muy importante para mi", "type": "likert", "category": "condiciones"},
            {"id": "v-co-2", "text": "Valoro un buen salario y beneficios", "type": "likert", "category": "condiciones"},
            {"id": "v-co-3", "text": "Prefiero horarios de trabajo predecibles", "type": "likert", "category": "condiciones"},
            {"id": "v-co-4", "text": "Es importante tener un lugar de trabajo comodo", "type": "likert", "category": "condiciones"},
            {"id": "v-co-5", "text": "Valoro el balance entre trabajo y vida personal", "type": "likert", "category": "condiciones"},
        ],
    },
    {
        "id": "career-anchors",
        "slug": "career-anchors",
        "name": "Test de Anclas de Carrera",
        "shortName": "Anclas de Carrera",
        "description": "Descubre que te motiva profesionalmente segun las 8 anclas de carrera de Edgar Schein: Competencia Tecnica, Gerencia, Autonomia, Seguridad, Emprendimiento, Servicio, Desafio y Estilo de Vida.",
        "academicBasis": "Desarrollado por Edgar Schein en MIT Sloan School of Management con más de 40 años de investigación. Es uno de los frameworks más utilizados para entender motivaciones profesionales.",
        "estimatedMinutes": 10,
        "questionCount": 24,
        "icon": "anchor",
        "questions": [
            {"id": "ca-tf-1", "text": "Prefiero ser reconocido como experto en mi area antes que como lider", "type": "likert", "category": "TF"},
            {"id": "ca-tf-2", "text": "Me motiva dominar completamente las habilidades de mi profesion", "type": "likert", "category": "TF"},
            {"id": "ca-tf-3", "text": "El conocimiento tecnico profundo es lo que mas valoro en mi trabajo", "type": "likert", "category": "TF"},
            {"id": "ca-gm-1", "text": "Me veo dirigiendo equipos y tomando decisiones importantes", "type": "likert", "category": "GM"},
            {"id": "ca-gm-2", "text": "Disfruto coordinar personas hacia un objetivo comun", "type": "likert", "category": "GM"},
            {"id": "ca-gm-3", "text": "Mi meta es llegar a posiciones de liderazgo organizacional", "type": "likert", "category": "GM"},
            {"id": "ca-au-1", "text": "Necesito libertad para organizar mi trabajo a mi manera", "type": "likert", "category": "AU"},
            {"id": "ca-au-2", "text": "Prefiero trabajar de forma independiente sin supervision constante", "type": "likert", "category": "AU"},
            {"id": "ca-au-3", "text": "Valoro poder tomar mis propias decisiones profesionales", "type": "likert", "category": "AU"},
            {"id": "ca-se-1", "text": "La estabilidad laboral es muy importante para mi", "type": "likert", "category": "SE"},
            {"id": "ca-se-2", "text": "Prefiero un trabajo seguro aunque sea menos emocionante", "type": "likert", "category": "SE"},
            {"id": "ca-se-3", "text": "Me preocupa tener un futuro economico predecible", "type": "likert", "category": "SE"},
            {"id": "ca-ec-1", "text": "Sueno con crear mi propio negocio o proyecto", "type": "likert", "category": "EC"},
            {"id": "ca-ec-2", "text": "Me emociona la idea de construir algo desde cero", "type": "likert", "category": "EC"},
            {"id": "ca-ec-3", "text": "Prefiero el riesgo de emprender que la seguridad de un empleo", "type": "likert", "category": "EC"},
            {"id": "ca-sd-1", "text": "Lo mas importante es que mi trabajo ayude a otros", "type": "likert", "category": "SD"},
            {"id": "ca-sd-2", "text": "Elegiria menor sueldo si el trabajo tiene mayor impacto social", "type": "likert", "category": "SD"},
            {"id": "ca-sd-3", "text": "Me motiva contribuir a causas que considero importantes", "type": "likert", "category": "SD"},
            {"id": "ca-pc-1", "text": "Me aburro si mi trabajo no tiene desafios constantes", "type": "likert", "category": "PC"},
            {"id": "ca-pc-2", "text": "Busco situaciones donde pueda probar mis limites", "type": "likert", "category": "PC"},
            {"id": "ca-pc-3", "text": "Resolver problemas dificiles es lo que me hace sentir vivo/a", "type": "likert", "category": "PC"},
            {"id": "ca-ls-1", "text": "El balance entre trabajo y vida personal es fundamental", "type": "likert", "category": "LS"},
            {"id": "ca-ls-2", "text": "No sacrificaria mi tiempo personal por avanzar profesionalmente", "type": "likert", "category": "LS"},
            {"id": "ca-ls-3", "text": "Busco trabajos que se adapten a mi estilo de vida ideal", "type": "likert", "category": "LS"},
        ],
    },
    # =====================================================================
    # MBTI · Indicador de Tipos (Myers-Briggs style · banco propio · S4)
    # 60 preguntas balanceadas en 4 dimensiones (15 por dimension)
    # E/I: extraversion vs. introversion
    # S/N: sensorial vs. intuitivo
    # T/F: pensamiento vs. sentimiento
    # J/P: juicio vs. percepcion
    # Likert 1-5 · respuestas pares (id-impar) suman al primer polo · pares al segundo
    # =====================================================================
    {
        "id": "mbti",
        "slug": "mbti",
        "name": "Indicador de Tipos de Personalidad MBTI",
        "shortName": "MBTI",
        "description": "Descubre tu tipo de personalidad entre los 16 tipos del modelo MBTI a partir de 4 dimensiones: Extraversion/Introversion, Sensorial/Intuitivo, Pensamiento/Sentimiento, Juicio/Percepcion.",
        "academicBasis": "Inspirado en el modelo de tipos psicologicos desarrollado por Carl Jung (1921) y operacionalizado por Isabel Myers y Katharine Briggs. Banco de preguntas propio adaptado al contexto LATAM colegial. NO es el instrumento MBTI oficial de The Myers-Briggs Company.",
        "estimatedMinutes": 15,
        "questionCount": 60,
        "icon": "compass",
        "questions": [
            # E/I dimension (15 preguntas) · score alto -> E · reversed -> I
            {"id": "m-ei-1", "text": "Despues de un dia con muchas personas, me siento energizado/a", "type": "likert", "category": "EI"},
            {"id": "m-ei-2", "text": "Prefiero quedarme en casa solo/a a salir a una fiesta grande", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-3", "text": "Me gusta hablar en grupo y conocer gente nueva", "type": "likert", "category": "EI"},
            {"id": "m-ei-4", "text": "Necesito tiempo a solas para recargar energia", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-5", "text": "Pienso mejor cuando hablo con otros sobre mis ideas", "type": "likert", "category": "EI"},
            {"id": "m-ei-6", "text": "Prefiero pensar en silencio antes de compartir mi opinion", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-7", "text": "En clase me anima participar y comentar", "type": "likert", "category": "EI"},
            {"id": "m-ei-8", "text": "Me cuesta hablar en publico cuando hay muchas personas", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-9", "text": "Me gusta liderar conversaciones en grupo", "type": "likert", "category": "EI"},
            {"id": "m-ei-10", "text": "Tengo pocos amigos cercanos pero muy profundos", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-11", "text": "Cuando tengo un problema prefiero hablarlo con alguien", "type": "likert", "category": "EI"},
            {"id": "m-ei-12", "text": "Cuando tengo un problema prefiero pensarlo a solas primero", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-13", "text": "Me animo facilmente al estar rodeado/a de gente", "type": "likert", "category": "EI"},
            {"id": "m-ei-14", "text": "Las reuniones largas con mucha gente me agotan", "type": "likert", "category": "EI", "reversed": True},
            {"id": "m-ei-15", "text": "Disfruto las actividades grupales mas que las individuales", "type": "likert", "category": "EI"},
            # S/N dimension (15 preguntas) · score alto -> S · reversed -> N
            {"id": "m-sn-1", "text": "Prefiero hechos concretos antes que teorias abstractas", "type": "likert", "category": "SN"},
            {"id": "m-sn-2", "text": "Me fascinan las ideas y posibilidades futuras", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-3", "text": "Confio mas en lo que veo y oigo que en mi intuicion", "type": "likert", "category": "SN"},
            {"id": "m-sn-4", "text": "Suelo conectar ideas que parecen no relacionadas", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-5", "text": "Me siento comodo/a con instrucciones paso a paso", "type": "likert", "category": "SN"},
            {"id": "m-sn-6", "text": "Disfruto explorar metaforas y simbolos", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-7", "text": "Prefiero aprender con ejemplos practicos y reales", "type": "likert", "category": "SN"},
            {"id": "m-sn-8", "text": "Me intereso mas por el por que que por el como", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-9", "text": "Recuerdo bien fechas, nombres y detalles concretos", "type": "likert", "category": "SN"},
            {"id": "m-sn-10", "text": "Me gusta imaginar como podrian ser las cosas en el futuro", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-11", "text": "Soy realista y aterrizado/a en mis expectativas", "type": "likert", "category": "SN"},
            {"id": "m-sn-12", "text": "Disfruto resolver problemas creativos abiertos", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-13", "text": "Prefiero mejorar lo que ya existe antes que inventar algo nuevo", "type": "likert", "category": "SN"},
            {"id": "m-sn-14", "text": "Me atraen los temas filosoficos y conceptuales", "type": "likert", "category": "SN", "reversed": True},
            {"id": "m-sn-15", "text": "Confio en mi experiencia previa para tomar decisiones", "type": "likert", "category": "SN"},
            # T/F dimension (15 preguntas) · score alto -> T · reversed -> F
            {"id": "m-tf-1", "text": "Tomo decisiones basandome en logica antes que en emociones", "type": "likert", "category": "TF"},
            {"id": "m-tf-2", "text": "Me importa mas como se sienten las personas que la eficiencia", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-3", "text": "Me consideran objetivo/a y analitico/a", "type": "likert", "category": "TF"},
            {"id": "m-tf-4", "text": "Empatizo facilmente con los problemas de otros", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-5", "text": "Prefiero la verdad incomoda a una mentira amable", "type": "likert", "category": "TF"},
            {"id": "m-tf-6", "text": "Cuando alguien esta triste, mi prioridad es consolarlo/a", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-7", "text": "Critico ideas con facilidad si veo fallas logicas", "type": "likert", "category": "TF"},
            {"id": "m-tf-8", "text": "Evito conflictos cuando puedo y busco la armonia del grupo", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-9", "text": "Prefiero ser justo/a antes que compasivo/a", "type": "likert", "category": "TF"},
            {"id": "m-tf-10", "text": "Tomo decisiones pensando en el impacto humano sobre todo", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-11", "text": "Me siento comodo/a debatiendo ideas sin tomarmelo personal", "type": "likert", "category": "TF"},
            {"id": "m-tf-12", "text": "Me cuesta dar feedback negativo aunque sea util", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-13", "text": "Si algo es eficiente, lo prefiero aunque no sea calido", "type": "likert", "category": "TF"},
            {"id": "m-tf-14", "text": "Valoro mas la lealtad emocional que la coherencia logica", "type": "likert", "category": "TF", "reversed": True},
            {"id": "m-tf-15", "text": "Analizo pros y contras antes de comprometerme con algo", "type": "likert", "category": "TF"},
            # J/P dimension (15 preguntas) · score alto -> J · reversed -> P
            {"id": "m-jp-1", "text": "Me gusta tener planes claros y cerrados", "type": "likert", "category": "JP"},
            {"id": "m-jp-2", "text": "Disfruto improvisar y dejar opciones abiertas", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-3", "text": "Hago listas de tareas y las cumplo", "type": "likert", "category": "JP"},
            {"id": "m-jp-4", "text": "Postergo decisiones para tener mas informacion", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-5", "text": "Me siento mejor cuando termino lo que empece", "type": "likert", "category": "JP"},
            {"id": "m-jp-6", "text": "Empiezo varios proyectos a la vez sin terminar todos", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-7", "text": "Llego puntual o antes a mis compromisos", "type": "likert", "category": "JP"},
            {"id": "m-jp-8", "text": "Trabajo mejor con presion de ultimo minuto", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-9", "text": "Mantengo mi espacio organizado y limpio", "type": "likert", "category": "JP"},
            {"id": "m-jp-10", "text": "Me adapto bien a cambios inesperados de planes", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-11", "text": "Me incomoda no saber que va a pasar manana", "type": "likert", "category": "JP"},
            {"id": "m-jp-12", "text": "Disfruto la espontaneidad mas que la rutina", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-13", "text": "Sigo cronogramas y agendas cuando los tengo", "type": "likert", "category": "JP"},
            {"id": "m-jp-14", "text": "Me siento limitado/a si todo esta planeado de antemano", "type": "likert", "category": "JP", "reversed": True},
            {"id": "m-jp-15", "text": "Cierro decisiones rapido para avanzar", "type": "likert", "category": "JP"},
        ],
    },
    # =====================================================================
    # iStrong · Inventario de Intereses Profesionales (basado en Holland) · S4
    # Ver D-011: NO es Strong Interest Inventory original. Banco propio.
    # 60 preguntas en 6 General Occupational Themes (R-I-A-S-E-C)
    # cada GOT con 2 Basic Interest Scales (BIS) -> 12 BIS totales · 5 preguntas/BIS
    # Subcategoria coding: "<GOT>:<BIS>" ej. "R:mecanica" "I:ciencias"
    # =====================================================================
    {
        "id": "istrong",
        "slug": "istrong",
        "name": "iStrong - Inventario de Intereses Profesionales (basado en Holland)",
        "shortName": "iStrong",
        "description": "Profundiza en tus intereses profesionales mediante 12 escalas tematicas agrupadas en 6 areas vocacionales. Te ayuda a entender no solo en que area encajas sino que actividades especificas dentro de ella te motivan mas.",
        "academicBasis": "Inspirado en el modelo de J. Holland (RIASEC, 1959, dominio publico) con expansion propia de 12 Basic Interest Scales adaptadas al contexto LATAM colegial. NO es el Strong Interest Inventory de The Myers-Briggs Company. Construido como complemento granular al test Holland.",
        "estimatedMinutes": 18,
        "questionCount": 60,
        "icon": "target",
        "questions": [
            # R · Realista (10 preguntas · 2 BIS)
            # R:mecanica
            {"id": "is-r-mec-1", "text": "Me gustaria aprender a reparar autos o motos", "type": "likert", "category": "R:mecanica"},
            {"id": "is-r-mec-2", "text": "Disfrutaria armar muebles, robots o circuitos electronicos", "type": "likert", "category": "R:mecanica"},
            {"id": "is-r-mec-3", "text": "Me llaman la atencion las profesiones que trabajan con maquinaria pesada", "type": "likert", "category": "R:mecanica"},
            {"id": "is-r-mec-4", "text": "Me gustaria estudiar ingenieria mecanica o electrica", "type": "likert", "category": "R:mecanica"},
            {"id": "is-r-mec-5", "text": "Disfrutaria un trabajo donde construya cosas con mis manos", "type": "likert", "category": "R:mecanica"},
            # R:naturaleza
            {"id": "is-r-nat-1", "text": "Me interesa trabajar al aire libre con plantas o cultivos", "type": "likert", "category": "R:naturaleza"},
            {"id": "is-r-nat-2", "text": "Me llamaria la atencion ser veterinario/a o zootecnista", "type": "likert", "category": "R:naturaleza"},
            {"id": "is-r-nat-3", "text": "Disfrutaria trabajar en parques nacionales o reservas naturales", "type": "likert", "category": "R:naturaleza"},
            {"id": "is-r-nat-4", "text": "Me interesa la agricultura sostenible o la ganaderia", "type": "likert", "category": "R:naturaleza"},
            {"id": "is-r-nat-5", "text": "Me motiva una carrera relacionada con el medio ambiente", "type": "likert", "category": "R:naturaleza"},
            # I · Investigador (10 preguntas · 2 BIS)
            # I:ciencias
            {"id": "is-i-cie-1", "text": "Me apasiona la biologia, quimica o fisica", "type": "likert", "category": "I:ciencias"},
            {"id": "is-i-cie-2", "text": "Me veo trabajando en un laboratorio de investigacion", "type": "likert", "category": "I:ciencias"},
            {"id": "is-i-cie-3", "text": "Me interesaria estudiar medicina o ciencias de la salud", "type": "likert", "category": "I:ciencias"},
            {"id": "is-i-cie-4", "text": "Disfruto leer divulgacion cientifica", "type": "likert", "category": "I:ciencias"},
            {"id": "is-i-cie-5", "text": "Me gustaria descubrir como funciona algo que aun nadie entiende", "type": "likert", "category": "I:ciencias"},
            # I:tecnologia
            {"id": "is-i-tec-1", "text": "Me llama la atencion programar o desarrollar software", "type": "likert", "category": "I:tecnologia"},
            {"id": "is-i-tec-2", "text": "Me gustaria estudiar inteligencia artificial o ciencia de datos", "type": "likert", "category": "I:tecnologia"},
            {"id": "is-i-tec-3", "text": "Me interesa la ciberseguridad y la criptografia", "type": "likert", "category": "I:tecnologia"},
            {"id": "is-i-tec-4", "text": "Disfrutaria trabajar resolviendo problemas tecnicos complejos", "type": "likert", "category": "I:tecnologia"},
            {"id": "is-i-tec-5", "text": "Me veo creando productos digitales o aplicaciones", "type": "likert", "category": "I:tecnologia"},
            # A · Artistico (10 preguntas · 2 BIS)
            # A:visual
            {"id": "is-a-vis-1", "text": "Me apasiona el dibujo, la pintura o el diseno grafico", "type": "likert", "category": "A:visual"},
            {"id": "is-a-vis-2", "text": "Disfrutaria estudiar diseno, arquitectura o artes visuales", "type": "likert", "category": "A:visual"},
            {"id": "is-a-vis-3", "text": "Me veo trabajando en cine, fotografia o video", "type": "likert", "category": "A:visual"},
            {"id": "is-a-vis-4", "text": "Me interesa la animacion, el modelado 3D o los videojuegos", "type": "likert", "category": "A:visual"},
            {"id": "is-a-vis-5", "text": "Disfruto crear contenido visual original", "type": "likert", "category": "A:visual"},
            # A:performativa
            {"id": "is-a-per-1", "text": "Me gustaria estudiar musica, teatro o danza", "type": "likert", "category": "A:performativa"},
            {"id": "is-a-per-2", "text": "Disfruto componer, escribir letras o tocar un instrumento", "type": "likert", "category": "A:performativa"},
            {"id": "is-a-per-3", "text": "Me llama la actuacion, la direccion teatral o el doblaje", "type": "likert", "category": "A:performativa"},
            {"id": "is-a-per-4", "text": "Me apasiona la escritura creativa, los cuentos o la poesia", "type": "likert", "category": "A:performativa"},
            {"id": "is-a-per-5", "text": "Disfruto las artes escenicas mas que las visuales estaticas", "type": "likert", "category": "A:performativa"},
            # S · Social (10 preguntas · 2 BIS)
            # S:educacion
            {"id": "is-s-edu-1", "text": "Me veo siendo profesor/a o pedagogo/a", "type": "likert", "category": "S:educacion"},
            {"id": "is-s-edu-2", "text": "Disfrutaria disenar materiales educativos", "type": "likert", "category": "S:educacion"},
            {"id": "is-s-edu-3", "text": "Me interesa la educacion infantil o especial", "type": "likert", "category": "S:educacion"},
            {"id": "is-s-edu-4", "text": "Me motiva ensenar conceptos a quien no los entiende", "type": "likert", "category": "S:educacion"},
            {"id": "is-s-edu-5", "text": "Me gustaria trabajar en universidades o institutos academicos", "type": "likert", "category": "S:educacion"},
            # S:salud-mental
            {"id": "is-s-sal-1", "text": "Me llama la atencion ser psicologo/a o terapeuta", "type": "likert", "category": "S:salud-mental"},
            {"id": "is-s-sal-2", "text": "Disfrutaria trabajar acompanando a personas en momentos dificiles", "type": "likert", "category": "S:salud-mental"},
            {"id": "is-s-sal-3", "text": "Me interesa la psiquiatria, terapia ocupacional o trabajo social", "type": "likert", "category": "S:salud-mental"},
            {"id": "is-s-sal-4", "text": "Me veo asesorando o haciendo coaching a otros", "type": "likert", "category": "S:salud-mental"},
            {"id": "is-s-sal-5", "text": "Disfruto cuando alguien me cuenta sus problemas y puedo ayudar", "type": "likert", "category": "S:salud-mental"},
            # E · Emprendedor (10 preguntas · 2 BIS)
            # E:negocios
            {"id": "is-e-neg-1", "text": "Me apasiona el mundo de los negocios y las finanzas", "type": "likert", "category": "E:negocios"},
            {"id": "is-e-neg-2", "text": "Me veo emprendiendo un proyecto propio", "type": "likert", "category": "E:negocios"},
            {"id": "is-e-neg-3", "text": "Disfrutaria estudiar administracion, economia o finanzas", "type": "likert", "category": "E:negocios"},
            {"id": "is-e-neg-4", "text": "Me interesa el marketing y las ventas", "type": "likert", "category": "E:negocios"},
            {"id": "is-e-neg-5", "text": "Me motiva la idea de generar dinero con mi trabajo", "type": "likert", "category": "E:negocios"},
            # E:liderazgo
            {"id": "is-e-lid-1", "text": "Disfruto liderar equipos en proyectos grupales", "type": "likert", "category": "E:liderazgo"},
            {"id": "is-e-lid-2", "text": "Me veo en cargos directivos o politicos", "type": "likert", "category": "E:liderazgo"},
            {"id": "is-e-lid-3", "text": "Me llama la atencion la abogacia o la diplomacia", "type": "likert", "category": "E:liderazgo"},
            {"id": "is-e-lid-4", "text": "Disfruto convencer a otros con argumentos solidos", "type": "likert", "category": "E:liderazgo"},
            {"id": "is-e-lid-5", "text": "Me motiva tener responsabilidad sobre decisiones importantes", "type": "likert", "category": "E:liderazgo"},
            # C · Convencional (10 preguntas · 2 BIS)
            # C:datos
            {"id": "is-c-dat-1", "text": "Me gustaria trabajar con bases de datos y reportes", "type": "likert", "category": "C:datos"},
            {"id": "is-c-dat-2", "text": "Disfrutaria estudiar contabilidad o auditoria", "type": "likert", "category": "C:datos"},
            {"id": "is-c-dat-3", "text": "Me interesa la actuaria, estadistica o analisis financiero", "type": "likert", "category": "C:datos"},
            {"id": "is-c-dat-4", "text": "Me siento comodo/a manejando hojas de calculo y formulas", "type": "likert", "category": "C:datos"},
            {"id": "is-c-dat-5", "text": "Me motiva detectar errores o inconsistencias en informacion", "type": "likert", "category": "C:datos"},
            # C:logistica
            {"id": "is-c-log-1", "text": "Me llamaria una carrera en logistica, supply chain o operaciones", "type": "likert", "category": "C:logistica"},
            {"id": "is-c-log-2", "text": "Disfrutaria coordinar agendas, recursos y procesos", "type": "likert", "category": "C:logistica"},
            {"id": "is-c-log-3", "text": "Me interesa la gestion de proyectos con cronogramas claros", "type": "likert", "category": "C:logistica"},
            {"id": "is-c-log-4", "text": "Me motiva optimizar procesos para que sean mas eficientes", "type": "likert", "category": "C:logistica"},
            {"id": "is-c-log-5", "text": "Disfruto las profesiones administrativas con procedimientos claros", "type": "likert", "category": "C:logistica"},
        ],
    },
]


def get_test_by_id(test_id: str):
    for t in VOCATIONAL_TESTS:
        if t["id"] == test_id:
            return t
    return None


def get_all_tests_summary():
    return [
        {
            "id": t["id"],
            "slug": t["slug"],
            "name": t["name"],
            "shortName": t["shortName"],
            "description": t["description"],
            "academicBasis": t["academicBasis"],
            "estimatedMinutes": t["estimatedMinutes"],
            "questionCount": t["questionCount"],
            "icon": t["icon"],
        }
        for t in VOCATIONAL_TESTS
    ]


def calculate_vocational_scores(test_id: str, answers: dict) -> dict:
    test = get_test_by_id(test_id)
    if not test:
        return {}

    questions = test["questions"]
    categories = {}
    category_counts = {}

    for q in questions:
        cat = q["category"]
        if cat not in categories:
            categories[cat] = 0
            category_counts[cat] = 0
        category_counts[cat] += 1

        raw_value = answers.get(q["id"], 0)
        try:
            value = int(raw_value)
        except (ValueError, TypeError):
            value = 0

        if q.get("reversed"):
            value = 6 - value

        categories[cat] += value

    max_per_question = 5
    scores = {}
    for cat, total in categories.items():
        count = category_counts[cat]
        max_possible = count * max_per_question
        scores[cat] = round((total / max_possible) * 100) if max_possible > 0 else 0

    return scores
