"""Áreas de estudio · el vocabulario que cruza el catálogo con el test vocacional.

La extracción del catálogo dejó `area` como texto libre y salieron **280 valores
distintos** para 15.483 programas, donde 66 cubren el 90%. El resto son la misma
cosa escrita de otra forma ("Ciencia de Alimentos" / "Ciencias de los Alimentos",
con tilde y sin tilde) o subdivisiones demasiado finas para elegir en pantalla
("Diseño de Transporte", 2 programas).

Eso importa porque `area` es el campo que se cruza con el resultado del test: un
perfil Holland **I**nvestigativo tiene que encontrar *Ciencias*, no repartirse
entre doce grafías. Aquí vive el vocabulario cerrado, el mapa desde el texto
libre, y la correspondencia con los códigos RIASEC.

**Por qué el mapa es una tabla explícita y no reglas por palabra clave.** Una
regla del tipo *"si dice diseño → Diseño"* manda "Diseño de Videojuegos" a Diseño
cuando pertenece a Tecnología, y *"si dice ciencias → Ciencias"* se traga
"Ciencias Sociales", "Ciencias del Deporte" y "Ciencias de la Salud", que son
tres áreas distintas. Con 280 valores, escribirlos cuesta una tarde y se puede
auditar línea por línea; una regla que acierta el 90% deja 28 áreas mal que nadie
va a revisar y que terminan recomendándole ingeniería a quien quería arte.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# El vocabulario cerrado
# ---------------------------------------------------------------------------
# Veintiuna áreas. El número no es arbitrario: es lo que cabe en una pantalla de
# selección sin que el estudiante tenga que leer una lista interminable, y sigue
# siendo suficientemente fino para que "Enfermería" y "Derecho" no caigan juntas.

NEGOCIOS = "Negocios y Administración"
TECNOLOGIA = "Tecnología e Informática"
INGENIERIA = "Ingeniería"
SALUD = "Salud y Medicina"
PSICOLOGIA = "Psicología y Trabajo Social"
EDUCACION = "Educación"
DERECHO = "Derecho y Justicia"
CIENCIAS = "Ciencias"
SOCIALES = "Ciencias Sociales y Humanidades"
COMUNICACION = "Comunicación y Medios"
ARTES = "Artes"
DISENO = "Diseño y Moda"
ARQUITECTURA = "Arquitectura y Construcción"
HOSPITALIDAD = "Hospitalidad, Turismo y Gastronomía"
DEPORTE = "Deporte"
AGRO = "Agricultura y Veterinaria"
AMBIENTE = "Medio Ambiente y Sostenibilidad"
OFICIOS = "Oficios y Técnica"
BELLEZA = "Belleza y Estética"
IDIOMAS = "Idiomas"
PREPARACION = "Preparación Académica"

AREAS = [
    NEGOCIOS, TECNOLOGIA, INGENIERIA, SALUD, PSICOLOGIA, EDUCACION, DERECHO,
    CIENCIAS, SOCIALES, COMUNICACION, ARTES, DISENO, ARQUITECTURA,
    HOSPITALIDAD, DEPORTE, AGRO, AMBIENTE, OFICIOS, BELLEZA, IDIOMAS,
    PREPARACION,
]

# ---------------------------------------------------------------------------
# RIASEC · qué áreas le hablan a cada código de Holland
# ---------------------------------------------------------------------------
# Un área puede servir a varios códigos, y debe: la medicina es Investigativa
# (diagnóstico) y Social (paciente) a la vez, y quedarse con una sola de las dos
# empobrece la recomendación.
#
# Esto sustituye al mapeo que había en `recommendation_service`, que cruzaba
# RIASEC contra el **tipo** de programa (`carrera_completa`, `curso_idiomas`…) en
# vez del campo de estudio. Un "curso_idiomas" no es más Social que Artístico:
# el tipo dice cuánto dura y qué titulación da, no de qué trata.
# Cada lista va **ordenada por centralidad**, de más a menos propia del código.
# El orden es parte del dato, no decoración: a un perfil puramente Artístico hay
# que ofrecerle Artes antes que Comunicación, y con un conjunto sin orden el
# desempate caía en el orden alfabético del vocabulario —que no significa nada.
RIASEC_AREAS = {
    # Realista · trabajo manual, físico, con máquinas y al aire libre.
    "R": [OFICIOS, AGRO, INGENIERIA, ARQUITECTURA, DEPORTE, AMBIENTE],
    # Investigativo · analizar, entender, resolver.
    "I": [CIENCIAS, SALUD, TECNOLOGIA, INGENIERIA, AMBIENTE, PSICOLOGIA],
    # Artístico · crear, expresar, diseñar.
    "A": [ARTES, DISENO, COMUNICACION, ARQUITECTURA, IDIOMAS],
    # Social · enseñar, cuidar, acompañar.
    "S": [EDUCACION, PSICOLOGIA, SALUD, SOCIALES, DEPORTE, HOSPITALIDAD],
    # Emprendedor · persuadir, liderar, vender.
    "E": [NEGOCIOS, DERECHO, HOSPITALIDAD, COMUNICACION],
    # Convencional · organizar, ordenar, seguir procedimientos.
    "C": [NEGOCIOS, DERECHO, TECNOLOGIA, OFICIOS],
}


def afinidad(area: str, codigos) -> float:
    """Qué tan afín es un área a los códigos RIASEC de una persona · 0.0 a 1.0+.

    Cada código aporta según **qué tan central** sea el área para él, con una
    caída suave: 1.0 la primera de su lista, 0.9 la segunda, 0.8 la tercera…

    La suavidad es deliberada. Con una caída brusca (1, ½, ⅓) un área respaldada
    por un solo código le ganaba a una respaldada por los dos, y a un perfil I-S
    le salía Educación —que es sólo Social— antes que Salud y Medicina, que es el
    arquetipo de esa combinación. Un código Holland de dos letras significa
    precisamente que interesa el cruce, no cada letra por separado.
    """
    total = 0.0
    for c in codigos or []:
        lista = RIASEC_AREAS.get((c or "").strip().upper(), ())
        if area in lista:
            total += 1.0 - 0.1 * lista.index(area)
    return total


def areas_para_riasec(codigos) -> list:
    """Áreas afines a unos códigos RIASEC, la más afín primero.

    A un perfil I-S la medicina le sale antes que la física: la respaldan sus dos
    códigos, y en ambos está cerca de la cabeza.
    """
    puntos = {a: afinidad(a, codigos) for a in AREAS}
    return [a for a, p in sorted(puntos.items(), key=lambda kv: -kv[1]) if p > 0]


# ---------------------------------------------------------------------------
# Del texto libre al vocabulario
# ---------------------------------------------------------------------------
# La clave de cada entrada va normalizada (minúsculas, sin tildes), así que una
# sola línea absorbe "Tecnología", "Tecnologia" y "TECNOLOGÍA".

_MAPA_CRUDO = {
    NEGOCIOS: [
        "negocios", "marketing", "mercadeo", "finanzas", "contabilidad",
        "contaduria", "economia", "administracion", "logistica",
        "recursos humanos", "comercio internacional", "emprendimiento",
        "publicidad", "inmobiliario", "finanzas y contabilidad",
        "contabilidad y finanzas", "marketing digital", "marketing de moda",
        "negocios de la moda", "negocios de la musica", "administracion publica",
        "administracion en salud", "gestion de informacion",
        "informacion y bibliotecologia", "bibliotecologia", "liderazgo",
        "innovacion", "gestion cultural", "gestion creativa", "servicios",
        "negocios (marketing)", "negocios y diseno", "marketing y comunicacion",
        "desarrollo profesional", "empleabilidad", "gestion del diseno",
        "servicios publicos", "eventos", "gestion de eventos",
    ],
    TECNOLOGIA: [
        "tecnologia", "videojuegos", "diseno de videojuegos",
        "analitica de datos", "matematicas y datos", "medios digitales",
        "artes digitales", "animacion y vfx", "tecnologia musical",
        "diseno de interaccion",
    ],
    INGENIERIA: [
        "ingenieria", "manufactura", "ingenieria y ciencias", "maritimo",
        "aviacion", "energia y sostenibilidad",
    ],
    SALUD: [
        "salud", "medicina", "enfermeria", "odontologia", "farmacia",
        "nutricion", "optometria", "salud publica", "ciencias biomedicas",
        "ciencias de la salud", "medicina y odontologia", "quimica y farmacia",
        "enfermeria y parteria", "nutricion y alimentos", "salud mental",
        "salud animal", "seguridad y salud ocupacional", "servicios funerarios",
    ],
    PSICOLOGIA: [
        "psicologia", "trabajo social", "servicios sociales",
        "servicios comunitarios", "psicologia y trabajo social",
        "salud y servicios sociales", "desarrollo personal",
    ],
    EDUCACION: [
        "educacion", "formacion docente", "educacion general",
        "educacion escolar", "educacion y diseno",
    ],
    DERECHO: [
        "derecho", "criminologia", "seguridad y justicia", "justicia",
        "ciencias forenses", "derecho y justicia", "justicia y seguridad",
        "seguridad", "seguridad publica", "seguridad y defensa",
        "ciencias militares",
    ],
    CIENCIAS: [
        "ciencias", "matematicas", "quimica", "fisica", "ciencias biologicas",
        "investigacion", "ciencias del mar", "artes y ciencias",
    ],
    SOCIALES: [
        "ciencias sociales", "humanidades", "historia y arte", "sociologia",
        "teologia", "relaciones internacionales", "ciencias politicas",
        "ciencias politicas y filosofia", "humanidades y ciencias sociales",
        "estudios culturales", "desarrollo internacional",
        "literatura y escritura creativa", "escritura creativa", "letras",
        "letras e idiomas", "letras y escritura", "artes y humanidades",
        "negocios y ciencias sociales", "interdisciplinar", "multidisciplinar",
        "estudios interdisciplinarios",
    ],
    COMUNICACION: [
        "comunicacion", "comunicacion y medios", "comunicacion y artes",
        "medios", "medios y comunicacion", "medios/comunicacion", "periodismo",
        "comunicacion y branding", "comunicacion (fotoperiodismo)",
        "industrias creativas",
    ],
    ARTES: [
        "artes", "musica", "artes escenicas", "fotografia", "cine",
        "cine y audiovisuales", "cine y audiovisual",
        "cine y medios audiovisuales", "artes audiovisuales",
        "produccion audiovisual", "animacion", "danza", "artes visuales",
        "artes (fotografia)", "ilustracion",
    ],
    DISENO: [
        "diseno", "moda", "diseno grafico", "diseno de interiores",
        "diseno industrial", "diseno de producto", "diseno textil",
        "diseno de servicios", "diseno de transporte", "diseno y medios",
        "diseno y sostenibilidad", "artes y diseno", "gastronomia y diseno",
    ],
    ARQUITECTURA: [
        "arquitectura", "construccion", "urbanismo", "paisajismo",
        "arquitectura y diseno", "arquitectura y construccion",
        "construccion e inmobiliario", "planeacion urbana",
    ],
    HOSPITALIDAD: [
        "hospitalidad", "turismo", "gastronomia", "hoteleria",
        "turismo y eventos", "turismo y hospitalidad", "hospitalidad y turismo",
        "turismo y deportes", "alimentos", "enologia", "enologia y bebidas",
        "ciencias de los alimentos", "ciencia de alimentos",
    ],
    DEPORTE: [
        "deporte", "deportes", "ciencias del deporte", "deporte y fitness",
        "deporte y recreacion", "deporte y actividad fisica", "recreacion",
        "recreacion y deporte", "deporte y ciencias del ejercicio",
        "idiomas y deporte",
    ],
    AGRO: [
        "agricultura", "horticultura", "agronomia", "veterinaria",
        "ciencias animales", "floristeria", "agroindustria", "agronegocios",
        "agropecuario", "ciencias agrarias", "ciencias agropecuarias",
        "cuidado animal", "agricultura y veterinaria",
        "agronomia y veterinaria", "agricultura y paisajismo",
    ],
    AMBIENTE: [
        "medio ambiente", "ciencias ambientales", "ciencias y medio ambiente",
        "sostenibilidad",
    ],
    OFICIOS: [
        "oficios", "oficios tecnicos", "automotriz", "mecanica",
        "mecanica automotriz", "electricidad", "seguridad laboral",
        "seguridad ocupacional", "construccion y oficios",
        "oficios y construccion", "formacion tecnica", "formacion vocacional",
    ],
    BELLEZA: [
        "belleza", "belleza y estetica", "estetica y belleza",
        "belleza y cosmetica", "belleza y cosmetologia", "peluqueria y belleza",
    ],
    IDIOMAS: [
        "idiomas", "idiomas - ingles", "idiomas - espanol", "idiomas - frances",
        "idiomas - italiano", "idiomas - aleman", "idiomas - chino",
        "idiomas - arabe y frances", "idiomas - frances de negocios",
        "idiomas - italiano de negocios", "idiomas y musica", "idiomas y danza",
    ],
    PREPARACION: [
        "preparacion universitaria", "preparacion academica", "preparatorio",
        "estudios generales", "formacion general", "formacion basica",
        "educacion secundaria", "secundaria", "secundaria (k-12)", "general",
    ],
}


def _norm(s: str) -> str:
    """Minúsculas, sin tildes, y **cualquier separador tratado como espacio**.

    Los separadores se colapsan a espacio en vez de conservarse, y no es un
    detalle: el catálogo escribe "Idiomas · Inglés" con punto medio (U+00B7),
    que al pasar a ASCII simplemente desaparece; si aquí se guardara un guion,
    las dos formas dejarían de coincidir. Ya pasó: 116 filas de idiomas se
    quedaron sin mapear por eso.
    """
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[-–·/&,]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


_INDICE = {}
for _canon, _crudos in _MAPA_CRUDO.items():
    for _c in _crudos:
        _INDICE[_norm(_c)] = _canon


def normalizar(area: str) -> str | None:
    """Lleva un `area` del catálogo al vocabulario cerrado, o None.

    Devuelve **None** cuando no reconoce el valor, a propósito: quien llama debe
    contarlo y revisarlo, no meterlo en un cajón "Otros". Un área mal clasificada
    desaparece del filtro sin que nadie note que faltaba.
    """
    n = _norm(area)
    if not n:
        return None
    if n in _INDICE:
        return _INDICE[n]
    # Segundo intento · algunos valores traen un paréntesis aclaratorio
    # ("Artes (Fotografía)") o un sufijo de idioma. Se prueba sin él.
    sin_parentesis = re.sub(r"\s*\(.*?\)\s*", " ", n).strip()
    if sin_parentesis != n and sin_parentesis in _INDICE:
        return _INDICE[sin_parentesis]
    return None
