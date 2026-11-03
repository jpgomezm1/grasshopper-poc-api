"""Campamentos de vacaciones para 10° · E-2 (2026-11-02).

El demo de la clienta, paquete de 10° ("Perfil de Competencias"), pide
recomendaciones de "summer/winter camps". La fuente estaba pendiente de ella
(V-11); JP decidió que la armamos nosotros.

Cómo se armó la lista
---------------------
Cada programa se verificó en su página OFICIAL el día que dice `verificado`:
que existe, que tiene edición vigente, que admite estudiantes de 15-16 años y su
temporada. Lo que no se pudo verificar ahí, no entró.

Lo que esta lista NO trae, a propósito
---------------------------------------
- **Precios.** Cambian cada año y no son nuestros: el estudiante los ve en la
  página oficial. Un precio viejo en pantalla es peor que ninguno.
- **Fechas exactas.** Solo los meses de la temporada, por la misma razón.

Al actualizar: volver a verificar en la página oficial y cambiar `verificado`.
Las `areas` usan los 10 ids de `app/api/v1/study_preferences.py` (ISCED).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

AREAS = (
    "education", "arts_humanities", "social_sciences", "business_law", "natural_sciences",
    "ict", "engineering", "agriculture", "health", "services",
)

# Países que cuentan como "cerca" para quien quiere estudiar en Colombia.
_CERCA = ("Colombia", "México", "Chile", "Argentina", "Perú", "Ecuador", "Brasil", "Costa Rica")

# El orden importa: mezcla destinos a propósito (Colombia, EE. UU., Reino Unido,
# Canadá, Chile, Europa…), porque `campamentos_para` lo respeta al completar.
# Notas de la verificación (2026-11-02): Harvard, Yale, KCL, EHL y Cornell
# presencial piden 16 años cumplidos (por eso `edades` se muestra); los de
# EE. UU. requieren visa de turista para un colombiano; Stanford Humanities y
# Academia UC no dicen en su página si admiten extranjeros. Descartados por no
# admitir colombianos o no poderse verificar: UC Davis, Carnegie Mellon, Purdue,
# LSE, IE University, Goethe-Institut, EAFIT (sin convocatoria vigente), etc.
CAMPAMENTOS: List[Dict[str, Any]] = [{'id': 'uniandes-escuela-verano-jovenes',
  'nombre': 'Escuela de Verano para Jóvenes',
  'institucion': 'Universidad de los Andes',
  'pais': 'Colombia',
  'ciudad': 'Bogotá',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '2 semanas',
  'edades': '15-17 (grados 10 y 11)',
  'idioma': 'español',
  'areas': ['engineering', 'business_law', 'social_sciences', 'arts_humanities'],
  'descripcion': 'Eliges tres facultades y conoces sus bases con profesores de Los Andes a través de '
                 'talleres y laboratorios; si después entras a la universidad, te reconocen dos créditos.',
  'url': 'https://educacioncontinua.uniandes.edu.co/escuela-de-verano-para-jovenes/p',
  'verificado': '2026-11-02'},
 {'id': 'harvard-pre-college',
  'nombre': 'Pre-College Program',
  'institucion': 'Harvard Summer School',
  'pais': 'Estados Unidos',
  'ciudad': 'Cambridge, MA',
  'temporada': 'verano',
  'meses': 'jun-ago',
  'duracion': '2 semanas',
  'edades': '16-18',
  'idioma': 'inglés',
  'areas': ['business_law', 'social_sciences', 'health', 'arts_humanities'],
  'descripcion': 'Vives dos semanas en el campus de Harvard y tomas un curso sin créditos en temas como '
                 'derecho, psicología, medicina, negocios o escritura.',
  'url': 'https://summer.harvard.edu/high-school-programs/pre-college-program/',
  'verificado': '2026-11-02'},
 {'id': 'kcl-pre-university',
  'nombre': 'Pre-University Summer School',
  'institucion': "King's College London",
  'pais': 'Reino Unido',
  'ciudad': 'Londres',
  'temporada': 'verano',
  'meses': 'jul',
  'duracion': '1 a 3 semanas',
  'edades': '16-17',
  'idioma': 'inglés',
  'areas': ['health', 'business_law', 'ict', 'social_sciences', 'engineering'],
  'descripcion': 'Tomas módulos de una semana en temas como ciencias médicas, derecho, negocios, '
                 'computación, psicología o relaciones internacionales en el centro de Londres.',
  'url': 'https://www.kcl.ac.uk/summer/summer-on-campus/pre-university-summer-school',
  'verificado': '2026-11-02'},
 {'id': 'shad-canada',
  'nombre': 'Shad',
  'institucion': 'Shad Canada (en universidades canadienses)',
  'pais': 'Canadá',
  'ciudad': 'Varias universidades de Canadá',
  'temporada': 'verano',
  'meses': 'jul',
  'duracion': '4 semanas',
  'edades': '15-17',
  'idioma': 'inglés o francés',
  'areas': ['engineering', 'natural_sciences', 'business_law'],
  'descripcion': 'Vives casi un mes en una universidad canadiense haciendo laboratorios de ciencia, '
                 'tecnología y diseño, y un proyecto en equipo de emprendimiento.',
  'url': 'https://www.shad.ca/participate/',
  'verificado': '2026-11-02'},
 {'id': 'academia-uc-chile',
  'nombre': 'Academia UC',
  'institucion': 'Pontificia Universidad Católica de Chile',
  'pais': 'Chile',
  'ciudad': 'Santiago',
  'temporada': 'invierno',
  'meses': 'ene',
  'duracion': 'cursos de pocos días',
  'edades': '14-18',
  'idioma': 'español',
  'areas': ['education',
            'agriculture',
            'health',
            'engineering',
            'natural_sciences',
            'social_sciences',
            'arts_humanities'],
  'descripcion': 'Tomas cursos cortos y prácticos en la UC durante el verano chileno (tus vacaciones de fin '
                 'de año) en áreas como salud, ingeniería, educación, arquitectura o ciencias agropecuarias.',
  'url': 'https://academia.uc.cl/',
  'verificado': '2026-11-02'},
 {'id': 'sciences-po-pre-college',
  'nombre': 'Pre-College Programme (presencial)',
  'institucion': 'Sciences Po',
  'pais': 'Francia',
  'ciudad': 'Reims',
  'temporada': 'verano',
  'meses': 'jul',
  'duracion': '2 a 3 semanas',
  'edades': 'menores de 18, en colegio',
  'idioma': 'inglés',
  'areas': ['social_sciences', 'business_law'],
  'descripcion': 'Te acercas a la ciencia política y las relaciones internacionales con el método de '
                 'Sciences Po, entre clases comunes y tutorías.',
  'url': 'https://www.sciencespo.fr/summer-school/en/pre-college-programmes/on-campus-programme',
  'verificado': '2026-11-02'},
 {'id': 'javeriana-escuela-verano-senior',
  'nombre': 'Escuela de Verano Senior (Ingeniería)',
  'institucion': 'Pontificia Universidad Javeriana',
  'pais': 'Colombia',
  'ciudad': 'Bogotá',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '2 semanas',
  'edades': '15-18 (grados 9 a 11)',
  'idioma': 'español',
  'areas': ['engineering', 'ict'],
  'descripcion': 'Haces nueve retos prácticos en los laboratorios de la Facultad de Ingeniería para conocer '
                 'distintas ramas de la ingeniería.',
  'url': 'https://educacionvirtual.javeriana.edu.co/escuela-verano-senior',
  'verificado': '2026-11-02'},
 {'id': 'yale-yygs',
  'nombre': 'Yale Young Global Scholars',
  'institucion': 'Yale University',
  'pais': 'Estados Unidos',
  'ciudad': 'New Haven, CT',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '2 semanas',
  'edades': '16-18',
  'idioma': 'inglés',
  'areas': ['social_sciences', 'business_law', 'natural_sciences'],
  'descripcion': 'Convives con estudiantes de más de 150 países y trabajas en un eje interdisciplinario: '
                 'política, derecho y economía; ciencia y tecnología, o retos globales.',
  'url': 'https://globalscholars.yale.edu/',
  'verificado': '2026-11-02'},
 {'id': 'les-roches-hospitality-camp',
  'nombre': 'Hospitality Leadership Camp',
  'institucion': 'Les Roches',
  'pais': 'Suiza',
  'ciudad': 'Crans-Montana (también Marbella, España)',
  'temporada': 'verano',
  'meses': 'jul-ago',
  'duracion': '1 a 3 semanas',
  'edades': '15-17',
  'idioma': 'inglés',
  'areas': ['services', 'business_law'],
  'descripcion': 'Vives la hotelería y el negocio del deporte con retos prácticos, trabajo en equipo y '
                 'actividades de liderazgo.',
  'url': 'https://lesroches.edu/summer-programs/',
  'verificado': '2026-11-02'},
 {'id': 'ubc-future-global-leaders',
  'nombre': 'UBC Future Global Leaders',
  'institucion': 'University of British Columbia',
  'pais': 'Canadá',
  'ciudad': 'Vancouver',
  'temporada': 'verano',
  'meses': 'jul-ago',
  'duracion': '3 semanas',
  'edades': '15-18',
  'idioma': 'inglés',
  'areas': ['ict', 'health', 'social_sciences'],
  'descripcion': 'Combinas clases universitarias, talleres de habilidades y vida de campus en UBC para '
                 'explorar qué carrera te interesa.',
  'url': 'https://extendedlearning.ubc.ca/programs-high-school-students/ubc-future-global-leaders',
  'verificado': '2026-11-02'},
 {'id': 'ual-international-summer-school',
  'nombre': 'UAL International Summer School (16 a 18 años)',
  'institucion': 'University of the Arts London',
  'pais': 'Reino Unido',
  'ciudad': 'Londres',
  'temporada': 'verano',
  'meses': 'jul',
  'duracion': '3 semanas',
  'edades': '16-18',
  'idioma': 'inglés',
  'areas': ['arts_humanities'],
  'descripcion': 'Haces un intensivo de arte y diseño en los campus de UAL y armas piezas para tu '
                 'portafolio.',
  'url': 'https://www.arts.ac.uk/study-at-ual/short-courses/summer-short-courses/ual-international-summer-school',
  'verificado': '2026-11-02'},
 {'id': 'brown-summer-at-brown',
  'nombre': 'Summer@Brown',
  'institucion': 'Brown University',
  'pais': 'Estados Unidos',
  'ciudad': 'Providence, RI',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '1 a 3 semanas',
  'edades': '14-18',
  'idioma': 'inglés',
  'areas': ['health', 'engineering', 'business_law', 'natural_sciences', 'arts_humanities'],
  'descripcion': 'Eliges entre más de 230 cursos cortos en el campus, desde ciencias médicas e ingeniería '
                 'hasta negocios, derecho, artes y escritura.',
  'url': 'https://precollege.brown.edu/programs/summerbrown',
  'verificado': '2026-11-02'},
 {'id': 'ehl-hospitality-business-innovation',
  'nombre': 'Junior Academy · Hospitality Business & Innovation',
  'institucion': 'EHL Hospitality Business School',
  'pais': 'Suiza',
  'ciudad': 'Lausana',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '1 a 2 semanas',
  'edades': '16-18',
  'idioma': 'inglés',
  'areas': ['services', 'business_law'],
  'descripcion': 'Pasas una semana en la escuela de hotelería de Lausana con clases y talleres de gestión '
                 'hotelera y negocios.',
  'url': 'https://www.ehl.edu/en/study/pre-university-courses/hospitality-business-innovation',
  'verificado': '2026-11-02'},
 {'id': 'berklee-valencia-summer-performance',
  'nombre': 'Spain Summer Performance Program',
  'institucion': 'Berklee Valencia',
  'pais': 'España',
  'ciudad': 'Valencia',
  'temporada': 'verano',
  'meses': 'jul',
  'duracion': '2 semanas',
  'edades': '15-29',
  'idioma': 'inglés',
  'areas': ['arts_humanities'],
  'descripcion': 'Haces un intensivo de interpretación musical en el campus de Berklee en Valencia.',
  'url': 'https://valencia.berklee.edu/academics/summer-programs',
  'verificado': '2026-11-02'},
 {'id': 'georgetown-medical-academy',
  'nombre': 'Medical Academy',
  'institucion': 'Georgetown University Summer Programs',
  'pais': 'Estados Unidos',
  'ciudad': 'Washington, D.C.',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '1 semana',
  'edades': '15-18',
  'idioma': 'inglés',
  'areas': ['health'],
  'descripcion': 'Exploras la medicina en el centro médico de Georgetown con laboratorios de sutura, yesos, '
                 'disección y simulador de pacientes.',
  'url': 'https://summer.georgetown.edu/programs/SHS19/medical-institute/',
  'verificado': '2026-11-02'},
 {'id': 'columbia-nyc-residential',
  'nombre': 'NYC Residential Summer (Pre-College)',
  'institucion': 'Columbia University',
  'pais': 'Estados Unidos',
  'ciudad': 'Nueva York, NY',
  'temporada': 'verano',
  'meses': 'jun-ago',
  'duracion': '3 o 6 semanas',
  'edades': '15-18',
  'idioma': 'inglés',
  'areas': ['social_sciences', 'business_law', 'arts_humanities'],
  'descripcion': 'Vives en el campus de Columbia en Manhattan y tomas un curso intensivo entre más de 70 '
                 'opciones de una docena de áreas.',
  'url': 'https://precollege.sps.columbia.edu/programs/summer-programs/nyc-residential-summer',
  'verificado': '2026-11-02'},
 {'id': 'stanford-summer-humanities',
  'nombre': 'Stanford Summer Humanities Institute',
  'institucion': 'Stanford Pre-Collegiate Studies',
  'pais': 'Estados Unidos',
  'ciudad': 'Stanford, CA',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '3 semanas',
  'edades': '15-17',
  'idioma': 'inglés',
  'areas': ['arts_humanities', 'social_sciences'],
  'descripcion': 'Vives en el campus de Stanford y participas en seminarios con profesores sobre filosofía, '
                 'historia, literatura y política.',
  'url': 'https://summerhumanities.spcs.stanford.edu/',
  'verificado': '2026-11-02'},
 {'id': 'uconn-pre-college',
  'nombre': 'UConn Pre-College Summer',
  'institucion': 'University of Connecticut',
  'pais': 'Estados Unidos',
  'ciudad': 'Storrs, CT',
  'temporada': 'verano',
  'meses': 'jun-jul',
  'duracion': '1 semana por sesión',
  'edades': '14-17',
  'idioma': 'inglés',
  'areas': ['health', 'agriculture', 'natural_sciences'],
  'descripcion': 'Pasas una semana en la universidad explorando áreas como premedicina, enfermería, biología '
                 'marina o veterinaria.',
  'url': 'https://precollege-summer.uconn.edu/',
  'verificado': '2026-11-02'},
 {'id': 'cornell-precollege',
  'nombre': 'Precollege Studies',
  'institucion': 'Cornell University',
  'pais': 'Estados Unidos',
  'ciudad': 'Ithaca, NY (o en línea)',
  'temporada': 'ambas',
  'meses': 'jun-ago presencial · dic-ene en línea',
  'duracion': '3 a 6 semanas',
  'edades': '16-18 presencial · 15-19 en línea',
  'idioma': 'inglés',
  'areas': ['services', 'business_law', 'natural_sciences'],
  'descripcion': 'Tomas cursos universitarios reales de Cornell, incluida su escuela de hotelería, en el '
                 'campus en verano o en línea a fin de año.',
  'url': 'https://sce.cornell.edu/precollege/admission/eligibility/summer',
  'verificado': '2026-11-02'},
 {'id': 'interlochen-arts-camp',
  'nombre': 'Interlochen Arts Camp',
  'institucion': 'Interlochen Center for the Arts',
  'pais': 'Estados Unidos',
  'ciudad': 'Interlochen, MI',
  'temporada': 'verano',
  'meses': 'jun-ago',
  'duracion': '1, 3 o 6 semanas',
  'edades': '14-18',
  'idioma': 'inglés',
  'areas': ['arts_humanities'],
  'descripcion': 'Te dedicas a fondo a una disciplina artística (música, teatro, danza, cine, escritura '
                 'creativa o artes visuales) con jóvenes artistas de todo el mundo.',
  'url': 'https://www.interlochen.org/art-summer-camp',
  'verificado': '2026-11-02'},
 {'id': 'berklee-aspire-boston',
  'nombre': 'Aspire: Five-Week Music Performance Intensive',
  'institucion': 'Berklee College of Music',
  'pais': 'Estados Unidos',
  'ciudad': 'Boston, MA',
  'temporada': 'verano',
  'meses': 'jul-ago',
  'duracion': '5 semanas',
  'edades': '15 o más',
  'idioma': 'inglés',
  'areas': ['arts_humanities'],
  'descripcion': 'Estudias interpretación musical cinco semanas en Berklee y cierras con presentaciones en '
                 'vivo en el campus.',
  'url': 'https://summer.berklee.edu/programs/aspire-five-week-music-performance-intensive',
  'verificado': '2026-11-02'},
 {'id': 'mathcamp',
  'nombre': 'Canada/USA Mathcamp',
  'institucion': 'Mathcamp (organización sin ánimo de lucro)',
  'pais': 'Estados Unidos',
  'ciudad': 'Sede rotativa',
  'temporada': 'verano',
  'meses': 'jun-ago',
  'duracion': '5 semanas',
  'edades': '13-18',
  'idioma': 'inglés',
  'areas': ['natural_sciences', 'ict'],
  'descripcion': 'Te sumerges en matemáticas avanzadas con estudiantes de todo el mundo a través de clases, '
                 'problemas y proyectos.',
  'url': 'https://www.mathcamp.org/',
  'verificado': '2026-11-02'},
 {'id': 'promys',
  'nombre': 'PROMYS',
  'institucion': 'Boston University · Departamento de Matemáticas',
  'pais': 'Estados Unidos',
  'ciudad': 'Boston, MA',
  'temporada': 'verano',
  'meses': 'jun-ago',
  'duracion': '6 semanas',
  'edades': '14-18',
  'idioma': 'inglés',
  'areas': ['natural_sciences'],
  'descripcion': 'Vives seis semanas en Boston University resolviendo problemas de teoría de números y '
                 'aprendiendo a pensar como un matemático.',
  'url': 'https://promys.org/programs/promys/for-students/',
  'verificado': '2026-11-02'},
 {'id': 'concordia-language-villages',
  'nombre': 'Concordia Language Villages',
  'institucion': 'Concordia College',
  'pais': 'Estados Unidos',
  'ciudad': 'Bemidji, MN',
  'temporada': 'verano',
  'meses': 'jun-ago',
  'duracion': '1, 2 o 4 semanas',
  'edades': '7-18',
  'idioma': 'inglés y el idioma de la villa',
  'areas': ['arts_humanities'],
  'descripcion': 'Vives en una aldea de inmersión donde aprendes y usas a diario uno de sus 14 idiomas y su '
                 'cultura.',
  'url': 'https://www.concordialanguagevillages.org/summer-youth-camps/',
  'verificado': '2026-11-02'}]

# Cuántos se muestran en el plan: más de 4 deja de ser una recomendación.
MAXIMO = 4


def campamentos_para(area: Optional[str], interes_exterior: Optional[str]) -> List[Dict[str, Any]]:
    """Hasta 4 campamentos para un estudiante de 10°.

    - Primero, los de su área de estudio (si la eligió).
    - Si dijo que NO quiere estudiar afuera (`international_interest == "no"`),
      los de Colombia y Latinoamérica van primero; si dijo que sí o quizás, el
      orden de la lista (que mezcla destinos) se respeta.
    - Si no hay suficientes de su área, se completa con otros, sin repetir país
      mientras se pueda, para que vea variedad y no cuatro de Estados Unidos.
    """
    area = area if area in AREAS else None
    cerca_primero = interes_exterior == "no"

    def orden(c: Dict[str, Any]) -> tuple:
        return (
            0 if area and area in c["areas"] else 1,
            0 if (cerca_primero and c["pais"] in _CERCA) else 1,
        )

    candidatos = sorted(CAMPAMENTOS, key=orden)  # sorted es estable: respeta la lista
    elegidos: List[Dict[str, Any]] = []
    paises: set = set()
    # Primera pasada: los de su área, sin límite de país.
    for c in candidatos:
        if area and area in c["areas"] and len(elegidos) < MAXIMO:
            elegidos.append(c)
            paises.add(c["pais"])
    # Segunda: completar con variedad de países.
    for c in candidatos:
        if len(elegidos) >= MAXIMO:
            break
        if c not in elegidos and c["pais"] not in paises:
            elegidos.append(c)
            paises.add(c["pais"])
    # Tercera: si aún faltan (lista corta), lo que quede.
    for c in candidatos:
        if len(elegidos) >= MAXIMO:
            break
        if c not in elegidos:
            elegidos.append(c)
    return [_publico(c) for c in elegidos]


def _publico(c: Dict[str, Any]) -> Dict[str, Any]:
    """Lo que viaja al front (sin `areas` ni `verificado`, que son internos)."""
    return {k: c[k] for k in (
        "id", "nombre", "institucion", "pais", "ciudad", "temporada",
        "meses", "duracion", "edades", "idioma", "descripcion", "url",
    )}
