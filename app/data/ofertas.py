# app/data/ofertas.py

from typing import Optional

OFERTAS: list[dict] = [
    {
        "id": "oferta-1",
        "slug": "work-travel-usa-verano-2025",
        "name": "Work & Travel USA - Verano 2025",
        "shortDescription": "Trabaja y viaja por Estados Unidos durante el verano. Una experiencia única para mejorar tu inglés y ganar experiencia internacional.",
        "fullDescription": (
            "El programa Work & Travel USA te permite trabajar legalmente en Estados Unidos durante tus vacaciones de verano universitarias.\n\n"
            "Durante 3 a 4 meses, trabajaras en destinos turisticos como parques nacionales, resorts de playa, o ciudades iconicas como Nueva York o San Francisco.\n\n"
            "**Lo que incluye:**\n"
            "- Visa J-1 de intercambio cultural\n"
            "- Colocacion laboral garantizada\n"
            "- Orientacion pre-partida\n"
            "- Soporte 24/7 durante tu estancia\n"
            "- Seguro medico basico\n\n"
            "**Requisitos:**\n"
            "- Ser estudiante universitario activo\n"
            "- Tener entre 18 y 28 años\n"
            "- Nivel de inglés intermedio\n"
            "- Disponibilidad de 3-4 meses en verano\n\n"
            "Es la oportunidad perfecta para sumergirte en la cultura americana, hacer amigos de todo el mundo, y regresar con historias increíbles."
        ),
        "highlights": [
            "Visa J-1 incluida",
            "Trabajo garantizado",
            "Ingreso promedio: $2,500-4,000 USD",
            "Viaja 30 dias despues de trabajar",
            "Soporte 24/7",
        ],
        "category": "work_travel",
        "tags": ["verano", "trabajo", "usa", "cultural", "inglés", "experiencia-laboral"],
        "provider": {
            "id": "provider-1",
            "name": "Global Exchange Programs",
            "logo": "https://images.unsplash.com/photo-1560179707-f14e90ef3623?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Estados Unidos"],
        "cities": ["Varios destinos"],
        "duration": {"min": 3, "max": 4, "type": "meses"},
        "cost": {
            "min": 2500,
            "max": 3500,
            "currency": "USD",
            "includes": [
                "Tramite de visa J-1",
                "Colocacion laboral",
                "Seguro medico basico",
                "Orientacion pre-partida",
                "Soporte durante el programa",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Alojamiento",
                "Gastos personales",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 28},
            "requiredEducation": ["Estudiante universitario activo"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "Constancia de estudios",
                "Formulario DS-2019",
            ],
            "languageRequirement": "intermedio",
            "languageTests": ["TOEFL iBT 52+", "IELTS 4.5+", "Entrevista"],
        },
        "startDates": ["Mayo 2025", "Junio 2025"],
        "deadlines": [
            {
                "name": "Inscripcion temprana",
                "date": "2025-02-15",
                "type": "application",
            },
            {
                "name": "Inscripcion regular",
                "date": "2025-03-31",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1485738422979-f5c462d49f74?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1501594907352-04cda38ebc29?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1534430480872-3498386e7856?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop"},
        ],
        "featured": True,
        "active": True,
    },
    {
        "id": "oferta-2",
        "slug": "curso-inglés-dublin-12-semanas",
        "name": "Curso de Ingles en Dublin - 12 Semanas",
        "shortDescription": "Aprende inglés en la vibrante capital irlandesa. Clases intensivas con profesores nativos y actividades culturales semanales.",
        "fullDescription": (
            "Sumérgete en el idioma inglés mientras vives en una de las ciudades más acogedoras de Europa.\n\n"
            "Dublin ofrece la combinacion perfecta entre una ciudad moderna y rica historia cultural. Nuestro programa de 12 semanas te llevara desde nivel basico hasta intermedio-alto.\n\n"
            "**Metodologia:**\n"
            "- 20 horas de clase por semana\n"
            "- Grupos reducidos (max 15 estudiantes)\n"
            "- Profesores certificados CELTA/DELTA\n"
            "- Material didactico incluido\n"
            "- Examen de ubicacion inicial\n\n"
            "**Actividades incluidas:**\n"
            "- Tours por la ciudad cada sabado\n"
            "- Intercambio de idiomas semanal\n"
            "- Visitas a lugares iconicos (Cliffs of Moher, Ring of Kerry)\n"
            "- Eventos sociales cada viernes\n\n"
            "**Alojamiento:**\n"
            "- Familia anfitriona (opciónrecomendada)\n"
            "- Residencia estudiantil\n"
            "- Apartamento compartido"
        ),
        "highlights": [
            "20 horas de clase/semana",
            "Profesores nativos certificados",
            "Actividades culturales incluidas",
            "Permiso de trabajo 20h/semana",
            "Certificado al finalizar",
        ],
        "category": "curso_idiomas",
        "tags": ["inglés", "europa", "irlanda", "dublin", "idiomas", "intensivo"],
        "provider": {
            "id": "provider-2",
            "name": "EduIreland Academy",
            "logo": "https://images.unsplash.com/photo-1598618443855-232ee0f819f6?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Irlanda"],
        "cities": ["Dublin"],
        "duration": {"min": 12, "max": 25, "type": "semanas"},
        "cost": {
            "min": 4000,
            "max": 8000,
            "currency": "USD",
            "includes": [
                "Matricula del curso",
                "Material didactico",
                "Certificado de finalizacion",
                "Actividades culturales semanales",
                "Seguro medico estudiantil",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (disponible por $800-1500/mes)",
                "Alimentacion",
                "Transporte local",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 16, "max": 50},
            "requiredDocuments": [
                "Pasaporte vigente",
                "Prueba de fondos",
                "Seguro de viaje",
            ],
            "languageRequirement": "basico",
        },
        "startDates": ["Primer lunes de cada mes"],
        "deadlines": [
            {
                "name": "Inscripcion",
                "date": "2025-04-30",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1549918864-48ac978761a4?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1564959130747-897fb406b9af?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=800&h=600&fit=crop"},
        ],
        "featured": True,
        "active": True,
    },
    {
        "id": "oferta-3",
        "slug": "semestre-academico-espana",
        "name": "Semestre Académico en España",
        "shortDescription": "Estudia un semestre en prestigiosas universidades espanolas. Convalida materias y vive la experiencia europea.",
        "fullDescription": (
            "Vive la experiencia de estudiar en España, un país con universidades de renombre mundial y una cultura vibrante.\n\n"
            "Nuestro programa te permite estudiar un semestre completo en universidades como la Universidad de Barcelona, Universidad Complutense de Madrid, o la Universidad de Salamanca.\n\n"
            "**Beneficios académicos:**\n"
            "- Convalidacion de materias con tu universidad de origen\n"
            "- Acceso a biblioteca y recursos universitarios\n"
            "- Tutoria académica personalizada\n"
            "- Transcripciones oficiales\n\n"
            "**Ciudades disponibles:**\n"
            "- Madrid: capital cosmopolita\n"
            "- Barcelona: arte, playa y arquitectura\n"
            "- Salamanca: ciudad universitaria por excelencia\n"
            "- Sevilla: tradicion y flamenco\n"
            "- Valencia: innovación y mediterráneo\n\n"
            "**Soporte:**\n"
            "- Orientacion pre-partida\n"
            "- Recogida en aeropuerto\n"
            "- Acompanamiento en tramites de residencia\n"
            "- Tutor local asignado"
        ),
        "highlights": [
            "Materias convalidables",
            "Universidades de prestigio",
            "Sin barrera de idioma",
            "Visa de estudiante",
            "Viaja por Europa",
        ],
        "category": "semestre_academico",
        "tags": ["universidad", "espana", "europa", "academico", "convalidacion", "erasmus"],
        "provider": {
            "id": "provider-3",
            "name": "Study Abroad Spain",
            "logo": "https://images.unsplash.com/photo-1539037116277-4db20889f2d4?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["España"],
        "cities": ["Madrid", "Barcelona", "Salamanca", "Sevilla", "Valencia"],
        "duration": {"min": 1, "max": 2, "type": "semestres"},
        "cost": {
            "min": 8000,
            "max": 15000,
            "currency": "USD",
            "includes": [
                "Matricula universitaria",
                "Orientacion y recogida",
                "Seguro medico estudiantil",
                "Soporte académico",
                "Tramite de visa",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Alojamiento ($400-900/mes)",
                "Alimentacion",
                "Transporte",
                "Material de estudio",
            ],
        },
        "budgetTier": "alto",
        "eligibility": {
            "ageRange": {"min": 18, "max": 30},
            "requiredEducation": ["Estudiante universitario (minimo 2 semestres cursados)"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "Transcripciones académicas",
                "Carta de recomendacion",
                "Carta de motivacion",
                "Prueba de fondos",
            ],
            "languageRequirement": "ninguno",
        },
        "startDates": ["Septiembre 2025", "Febrero 2026"],
        "deadlines": [
            {
                "name": "Semestre de otono",
                "date": "2025-05-15",
                "type": "application",
            },
            {
                "name": "Semestre de primavera",
                "date": "2025-10-31",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1543783207-ec64e4d95325?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1509840841025-9088ba78a826?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=800&h=600&fit=crop"},
        ],
        "featured": True,
        "active": True,
    },
    {
        "id": "oferta-4",
        "slug": "voluntariado-costa-rica",
        "name": "Voluntariado en Costa Rica",
        "shortDescription": "Contribuye a proyectos de conservacion ambiental y comunidad en uno de los paises más biodiversos del mundo.",
        "fullDescription": (
            "Costa Rica es un paraiso natural y un lider mundial en conservacion ambiental. Nuestro programa de voluntariado te permite contribuir mientras vives una experiencia transformadora.\n\n"
            "**Proyectos disponibles:**\n\n"
            "**1. Conservacion de tortugas marinas (Mar-Oct)**\n"
            "- Patrullaje nocturno de playas\n"
            "- Proteccion de nidos\n"
            "- Liberacion de crias\n"
            "- Ubicación: Costa Caribe\n\n"
            "**2. Rescate de vida silvestre**\n"
            "- Cuidado de animales rescatados\n"
            "- Rehabilitacion y liberacion\n"
            "- Educacion ambiental\n"
            "- Ubicación: Limón\n\n"
            "**3. Enseñanza de inglés en comunidades**\n"
            "- Clases para ninos y adultos\n"
            "- Actividades recreativas\n"
            "- Desarrollo comunitario\n"
            "- Ubicación: San Jose y alrededores\n\n"
            "**4. Agricultura sostenible**\n"
            "- Trabajo en fincas organicas\n"
            "- Aprendizaje de permacultura\n"
            "- Vida rural auténtica\n"
            "- Ubicación: Zona rural\n\n"
            "**Incluye alojamiento y alimentacion con familias locales o en la reserva.**"
        ),
        "highlights": [
            "Impacto real en conservacion",
            "Alojamiento y comidas incluidos",
            "Certificado de voluntariado",
            "Experiencia intercultural",
            "Sin requisito de idioma",
        ],
        "category": "voluntariado",
        "tags": ["voluntariado", "naturaleza", "conservacion", "latinoamerica", "tortugas", "comunidad"],
        "provider": {
            "id": "provider-4",
            "name": "Pura Vida Volunteers",
            "logo": "https://images.unsplash.com/photo-1518531933037-91b2f5f229cc?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Costa Rica"],
        "cities": ["Limón", "San Jose", "Guanacaste"],
        "duration": {"min": 2, "max": 12, "type": "semanas"},
        "cost": {
            "min": 500,
            "max": 2000,
            "currency": "USD",
            "includes": [
                "Alojamiento",
                "Tres comidas diarias",
                "Orientacion del proyecto",
                "Transporte al proyecto",
                "Certificado de voluntariado",
                "Coordinador local",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Seguro de viaje",
                "Gastos personales",
                "Actividades extras",
            ],
        },
        "budgetTier": "bajo",
        "eligibility": {
            "ageRange": {"min": 18, "max": 65},
            "requiredDocuments": [
                "Pasaporte vigente",
                "Seguro de viaje",
                "Formulario de salud",
            ],
            "languageRequirement": "basico",
        },
        "startDates": ["Cualquier lunes del año"],
        "deadlines": [
            {
                "name": "Inscripcion continua",
                "date": "2025-12-31",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1596402184320-417e7178b2cd?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-5",
        "slug": "practicas-hoteleria-australia",
        "name": "Prácticas en Hoteleria - Australia",
        "shortDescription": "Desarrolla tu carrera en la industria hotelera con prácticas pagadas en hoteles de lujo en Australia.",
        "fullDescription": (
            "Australia es reconocida mundialmente por su industria hotelera y turistica de clase mundial. Este programa te ofrece la oportunidad de realizar prácticas profesionales pagadas en hoteles de 4 y 5 estrellas.\n\n"
            "**Caracteristicas del programa:**\n\n"
            "**Posiciones disponibles:**\n"
            "- Recepcion y Guest Relations\n"
            "- Food & Beverage Service\n"
            "- Housekeeping Management\n"
            "- Cocina y Artes Culinarias\n"
            "- Eventos y Banquetes\n\n"
            "**Hoteles asociados:**\n"
            "- Cadenas internacionales (Marriott, Hilton, IHG)\n"
            "- Resorts de lujo en Gold Coast y Sydney\n"
            "- Boutique hotels en Melbourne\n\n"
            "**Beneficios:**\n"
            "- Salario australiano competitivo\n"
            "- Experiencia en hoteles de prestigio\n"
            "- Certificación internacional\n"
            "- Posibilidad de extension\n"
            "- Red de contactos global\n\n"
            "**Requisitos:**\n"
            "- Estudiante o recien graduado en Hoteleria, Turismo o afines\n"
            "- Nivel avanzado de inglés\n"
            "- Actitud de servicio\n"
            "- Disponibilidad de 6-12 meses"
        ),
        "highlights": [
            "Prácticas PAGADAS",
            "Hoteles de lujo",
            "Certificación internacional",
            "Posibilidad de extension",
            "Salario competitivo",
        ],
        "category": "practicas",
        "tags": ["practicas", "hoteleria", "australia", "pagado", "turismo", "profesional"],
        "provider": {
            "id": "provider-5",
            "name": "Hospitality Abroad",
            "logo": "https://images.unsplash.com/photo-1571896349842-33c89424de2d?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Australia"],
        "cities": ["Sydney", "Melbourne", "Gold Coast", "Brisbane"],
        "duration": {"min": 6, "max": 12, "type": "meses"},
        "cost": {
            "min": 3000,
            "max": 5000,
            "currency": "USD",
            "includes": [
                "Colocacion garantizada",
                "Tramite de visa",
                "Orientacion pre-partida",
                "Soporte durante prácticas",
                "Certificado de prácticas",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Alojamiento inicial (luego con salario)",
                "Gastos personales",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 30},
            "requiredEducation": ["Estudiante o graduado en Hoteleria, Turismo, Gastronomia o afines"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "CV en inglés",
                "Certificado de estudios",
                "Carta de motivacion",
                "Certificado de inglés",
            ],
            "languageRequirement": "avanzado",
            "languageTests": ["IELTS 5.5+", "TOEFL iBT 70+", "Cambridge FCE"],
        },
        "startDates": ["Febrero 2025", "Julio 2025"],
        "deadlines": [
            {
                "name": "Convocatoria Febrero",
                "date": "2024-11-30",
                "type": "application",
            },
            {
                "name": "Convocatoria Julio",
                "date": "2025-04-30",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1564501049412-61c2a3083791?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-6",
        "slug": "curso-frances-paris",
        "name": "Curso de Frances en París",
        "shortDescription": "Aprende frances en la ciudad del amor. Programa intensivo con inmersión cultural completa.",
        "fullDescription": (
            "París no solo es una de las ciudades más hermosas del mundo, sino también el lugar ideal para aprender frances de forma auténtica.\n\n"
            "**El programa:**\n\n"
            "Nuestro curso intensivo de frances combina clases de alta calidad con una inmersión cultural única. Desde los cafes de Montmartre hasta los museos del Louvre, cada momento es una oportunidad de aprendizaje.\n\n"
            "**Niveles disponibles:**\n"
            "- Principiante absoluto (A1)\n"
            "- Elemental (A2)\n"
            "- Intermedio (B1-B2)\n"
            "- Avanzado (C1)\n\n"
            "**Metodologia:**\n"
            "- Enfoque comúnicativo\n"
            "- Grupos pequeños (max 12 estudiantes)\n"
            "- Profesores nativos calificados\n"
            "- Laboratorio de idiomas\n"
            "- Actividades de inmersión\n\n"
            "**Actividades culturales incluidas:**\n"
            "- Visitas a museos\n"
            "- Tours gastronomicos\n"
            "- Intercambio con franceses\n"
            "- Excursiones a Versailles y Normandia\n\n"
            "**Alojamiento:**\n"
            "- Familia francesa (inmersión total)\n"
            "- Residencia estudiantil\n"
            "- Estudio independiente"
        ),
        "highlights": [
            "Ubicación en el centro de París",
            "Inmersión cultural completa",
            "Grupos reducidos",
            "Actividades semanales",
            "Certificación DELF/DALF prep",
        ],
        "category": "curso_idiomas",
        "tags": ["frances", "paris", "francia", "europa", "idiomas", "cultura"],
        "provider": {
            "id": "provider-6",
            "name": "Alliance Francaise Partner",
            "logo": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Francia"],
        "cities": ["París"],
        "duration": {"min": 4, "max": 24, "type": "semanas"},
        "cost": {
            "min": 3500,
            "max": 12000,
            "currency": "EUR",
            "includes": [
                "Matricula del curso",
                "Material didactico",
                "Actividades culturales",
                "Examen de ubicacion",
                "Certificado de finalizacion",
                "Wifi y espacios de estudio",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (desde EUR 700/mes)",
                "Alimentacion",
                "Transporte en París",
                "Seguro de viaje",
            ],
        },
        "budgetTier": "alto",
        "eligibility": {
            "ageRange": {"min": 16, "max": 60},
            "requiredDocuments": [
                "Pasaporte vigente",
                "Seguro de viaje",
                "Prueba de fondos (para visa larga estancia)",
            ],
            "languageRequirement": "ninguno",
        },
        "startDates": ["Primer lunes de cada mes"],
        "deadlines": [
            {
                "name": "Inscripcion continua",
                "date": "2025-12-31",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1499856871958-5b9627545d1a?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1509439581779-6298f75bf6e5?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-7",
        "slug": "certificacion-google-marketing-online",
        "name": "Certificación Google Digital Marketing - Online + Berlin",
        "shortDescription": "Obtiene la certificacion de Google en Marketing Digital con un componente presencial en Berlin.",
        "fullDescription": (
            "Combina el aprendizaje online con una experiencia presencial intensiva en Berlin, uno de los hubs de startups más importantes de Europa.\n\n"
            "**Estructura del programa:**\n\n"
            "**Fase 1: Online (8 semanas)**\n"
            "- Fundamentos de Marketing Digital\n"
            "- Google Ads y Analytics\n"
            "- SEO y SEM\n"
            "- Redes Sociales\n"
            "- Email Marketing\n"
            "- Content Marketing\n\n"
            "**Fase 2: Presencial en Berlin (2 semanas)**\n"
            "- Workshops intensivos\n"
            "- Visitas a startups y agencias\n"
            "- Networking con profesionales\n"
            "- Proyecto final en equipo\n"
            "- Presentacion ante panel de expertos\n\n"
            "**Certificaciónes incluidas:**\n"
            "- Google Ads Search\n"
            "- Google Analytics\n"
            "- Google Digital Marketing\n"
            "- Certificado del programa\n\n"
            "**Beneficios:**\n"
            "- Aprende de expertos de la industria\n"
            "- Networking internacional\n"
            "- Portfolio de proyectos reales\n"
            "- Acceso a bolsa de empleo"
        ),
        "highlights": [
            "Certificaciónes Google oficiales",
            "2 semanas en Berlin",
            "Portfolio de proyectos",
            "Red de contactos",
            "Bolsa de empleo",
        ],
        "category": "certificacion_corta",
        "tags": ["marketing", "digital", "google", "alemania", "online", "certificacion", "tecnologia"],
        "provider": {
            "id": "provider-7",
            "name": "Digital Skills Academy",
            "logo": "https://images.unsplash.com/photo-1573804633927-bfcbcd909acd?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Alemania"],
        "cities": ["Berlin"],
        "duration": {"min": 10, "max": 10, "type": "semanas"},
        "cost": {
            "min": 2500,
            "max": 3500,
            "currency": "EUR",
            "includes": [
                "Curso online completo",
                "Bootcamp presencial 2 semanas",
                "Examenes de certificacion",
                "Material y recursos",
                "Alojamiento en Berlin",
                "Actividades de networking",
            ],
            "excludes": [
                "Vuelos a Berlin",
                "Alimentacion",
                "Transporte local",
                "Seguro de viaje",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 45},
            "requiredEducation": ["Bachillerato completado"],
            "requiredDocuments": [
                "Documento de identidad",
                "CV actualizado",
                "Laptop personal",
            ],
            "languageRequirement": "intermedio",
            "languageTests": ["Ingles intermedio (B1+)"],
        },
        "startDates": ["Marzo 2025", "Junio 2025", "Octubre 2025"],
        "deadlines": [
            {
                "name": "Cohorte Marzo",
                "date": "2025-02-15",
                "type": "application",
            },
            {
                "name": "Cohorte Junio",
                "date": "2025-05-15",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1560472354-b33ff0c44a43?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1559136555-9303baea8ebd?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-8",
        "slug": "work-travel-canada-verano-2025",
        "name": "Work & Travel Canada - Verano 2025",
        "shortDescription": "Trabaja en los mejores resorts de ski y naturaleza en Canada. Experiencia única en uno de los paises más seguros del mundo.",
        "fullDescription": (
            "Canada es uno de los destinos más solicitados para Work & Travel. Con sus impresionantes paisajes, gente amigable y alta calidad de vida, es el lugar perfecto para una experiencia internacional.\n\n"
            "**Destinos principales:**\n"
            "- Banff y Lake Louise (Alberta)\n"
            "- Whistler (British Columbia)\n"
            "- Mont Tremblant (Quebec)\n"
            "- Niagara Falls (Ontario)\n\n"
            "**Posiciones disponibles:**\n"
            "- Hoteleria y hospitalidad\n"
            "- Food & Beverage\n"
            "- Guias de actividades al aire libre\n"
            "- Retail en tiendas de ski\n"
            "- Limpieza y mantenimiento\n\n"
            "**Beneficios:**\n"
            "- Alojamiento subsidiado por el empleador\n"
            "- Pase de ski gratuito (destinos de montana)\n"
            "- Comidas incluidas en muchos trabajos\n"
            "- Ambiente internacional"
        ),
        "highlights": [
            "Alojamiento subsidiado",
            "Pase de ski incluido",
            "Ambiente internacional",
            "Naturaleza espectacular",
            "Alta calidad de vida",
        ],
        "category": "work_travel",
        "tags": ["canada", "ski", "naturaleza", "verano", "trabajo", "montana"],
        "provider": {
            "id": "provider-8",
            "name": "Canada Work Experience",
            "logo": "https://images.unsplash.com/photo-1517935706615-2717063c2225?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Canada"],
        "cities": ["Banff", "Whistler", "Toronto", "Vancouver"],
        "duration": {"min": 4, "max": 6, "type": "meses"},
        "cost": {
            "min": 2800,
            "max": 4000,
            "currency": "USD",
            "includes": [
                "Tramite de visa IEC",
                "Colocacion laboral",
                "Seguro medico",
                "Orientacion pre-partida",
                "Soporte en destino",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Gastos personales",
                "Equipamiento de ski (opcional)",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 35},
            "requiredEducation": ["Bachillerato completado"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "Prueba de fondos CAD $2,500",
                "Certificado de policia",
            ],
            "languageRequirement": "intermedio",
            "languageTests": ["IELTS 5.0+", "TOEFL iBT 60+"],
        },
        "startDates": ["Noviembre 2025", "Diciembre 2025"],
        "deadlines": [
            {
                "name": "Temporada invierno",
                "date": "2025-08-31",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1503614472-8c93d56e92ce?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1609825488888-3a766db05542?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-9",
        "slug": "curso-aleman-munich",
        "name": "Curso de Aleman en Munich",
        "shortDescription": "Aprende aleman en la capital de Bavaria. Combina clases intensivas con la rica cultura alemana.",
        "fullDescription": (
            "Munich es la puerta de entrada perfecta al idioma aleman. Con su mezcla de tradicion bavara y modernidad, ofrece un ambiente ideal para aprender.\n\n"
            "**El programa:**\n"
            "Nuestro curso intensivo de aleman te prepara para vivir, estudiar o trabajar en paises germanoparlantes. Desde principiante absoluto hasta nivel avanzado.\n\n"
            "**Niveles:**\n"
            "- A1 a C1 segun el Marco Europeo\n"
            "- Preparacion para TestDaF y Goethe-Zertifikat\n\n"
            "**Metodologia:**\n"
            "- 25 horas de clase por semana\n"
            "- Grupos reducidos (8-12 estudiantes)\n"
            "- Profesores nativos certificados\n"
            "- Laboratorio de idiomas moderno\n"
            "- Actividades culturales semanales\n\n"
            "**Actividades incluidas:**\n"
            "- Tours por Munich\n"
            "- Visitas a fabricas de cerveza\n"
            "- Excursion a los Alpes\n"
            "- Intercambio con alemanes\n"
            "- Visita al castillo Neuschwanstein"
        ),
        "highlights": [
            "25 horas/semana",
            "Prep certificaciones oficiales",
            "Ubicación céntrica",
            "Excursiones incluidas",
            "Visa de estudiante",
        ],
        "category": "curso_idiomas",
        "tags": ["aleman", "alemania", "munich", "europa", "idiomas", "intensivo"],
        "provider": {
            "id": "provider-9",
            "name": "Goethe Institut Partner",
            "logo": "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Alemania"],
        "cities": ["Munich"],
        "duration": {"min": 8, "max": 24, "type": "semanas"},
        "cost": {
            "min": 3000,
            "max": 9000,
            "currency": "EUR",
            "includes": [
                "Matricula del curso",
                "Material didactico",
                "Examen de certificacion",
                "Actividades culturales",
                "Certificado de finalizacion",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (desde EUR 600/mes)",
                "Alimentacion",
                "Seguro de viaje",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 17, "max": 55},
            "requiredDocuments": [
                "Pasaporte vigente",
                "Seguro de viaje",
                "Prueba de fondos",
            ],
            "languageRequirement": "ninguno",
        },
        "startDates": ["Primer lunes de cada mes"],
        "deadlines": [
            {
                "name": "Inscripcion continua",
                "date": "2025-12-31",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1595867818082-083862f3d630?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1534313314376-a72289b6181e?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-10",
        "slug": "semestre-academico-italia",
        "name": "Semestre Académico en Italia",
        "shortDescription": "Estudia en las universidades más antiguas del mundo. Roma, Milan, Florencia y más te esperan.",
        "fullDescription": (
            "Italia combina historia milenaria, arte incomparable y una de las tradiciones académicas más antiguas del mundo.\n\n"
            "**Universidades disponibles:**\n"
            "- Universita di Bologna (la más antigua de Europa)\n"
            "- Sapienza Roma\n"
            "- Politecnico di Milano\n"
            "- Universita di Firenze\n"
            "- Universita di Padova\n\n"
            "**Areas de estudio populares:**\n"
            "- Arte y Diseno\n"
            "- Arquitectura\n"
            "- Moda\n"
            "- Negocios Internacionales\n"
            "- Historia del Arte\n"
            "- Gastronomia\n\n"
            "**Beneficios:**\n"
            "- Convalidacion de materias\n"
            "- Acceso a recursos universitarios\n"
            "- Tutoria académica\n"
            "- Viajes académicos incluidos\n\n"
            "**Vida estudiantil:**\n"
            "- Ciudades vibrantes y seguras\n"
            "- Comida excepcional\n"
            "- Viaja por Europa facilmente\n"
            "- Comunidad internacional"
        ),
        "highlights": [
            "Universidades históricas",
            "Arte y cultura únicos",
            "Materias convalidables",
            "Viaja por Europa",
            "Sin barrera de idioma (inglés)",
        ],
        "category": "semestre_academico",
        "tags": ["italia", "universidad", "arte", "europa", "academico", "diseno"],
        "provider": {
            "id": "provider-10",
            "name": "Study in Italy",
            "logo": "https://images.unsplash.com/photo-1523906834658-6e24ef2386f9?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Italia"],
        "cities": ["Roma", "Milan", "Florencia", "Bologna", "Venecia"],
        "duration": {"min": 1, "max": 2, "type": "semestres"},
        "cost": {
            "min": 7000,
            "max": 14000,
            "currency": "EUR",
            "includes": [
                "Matricula universitaria",
                "Orientacion pre-partida",
                "Recogida aeropuerto",
                "Soporte académico",
                "Seguro medico",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (EUR 400-800/mes)",
                "Alimentacion",
                "Material de estudio",
            ],
        },
        "budgetTier": "alto",
        "eligibility": {
            "ageRange": {"min": 18, "max": 30},
            "requiredEducation": ["Estudiante universitario activo"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "Transcripciones",
                "Carta de motivacion",
                "Prueba de fondos",
            ],
            "languageRequirement": "basico",
            "languageTests": ["Italiano A2 o Ingles B1"],
        },
        "startDates": ["Septiembre 2025", "Febrero 2026"],
        "deadlines": [
            {
                "name": "Semestre otono",
                "date": "2025-05-01",
                "type": "application",
            },
            {
                "name": "Semestre primavera",
                "date": "2025-11-01",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1523906834658-6e24ef2386f9?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1515542622106-78bda8ba0e5b?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1534445867742-43195f401b6c?w=800&h=600&fit=crop"},
        ],
        "featured": True,
        "active": True,
    },
    {
        "id": "oferta-11",
        "slug": "practicas-tech-silicon-valley",
        "name": "Prácticas Tech en Silicon Valley",
        "shortDescription": "Trabaja en startups y empresas tech en el corazon de la innovación mundial. Una experiencia transformadora.",
        "fullDescription": (
            "Silicon Valley es el epicentro mundial de la tecnología e innovación. Este programa te conecta con startups y empresas tech para una experiencia profesional única.\n\n"
            "**Empresas asociadas:**\n"
            "- Startups en etapa temprana\n"
            "- Scale-ups en crecimiento\n"
            "- Empresas establecidas de tech\n\n"
            "**Areas de trabajo:**\n"
            "- Desarrollo de Software\n"
            "- Data Science & AI\n"
            "- Product Management\n"
            "- UX/UI Design\n"
            "- Marketing Digital\n"
            "- Business Development\n\n"
            "**El programa incluye:**\n"
            "- Colocacion en empresa tech\n"
            "- Mentoria profesional\n"
            "- Workshops semanales\n"
            "- Networking events\n"
            "- Demo Day al finalizar\n\n"
            "**Beneficios únicos:**\n"
            "- Trabajar en ambiente startup\n"
            "- Construir red de contactos global\n"
            "- Referencias profesionales\n"
            "- Posibilidad de oferta laboral"
        ),
        "highlights": [
            "Startups de Silicon Valley",
            "Mentoria profesional",
            "Networking intensivo",
            "Workshops tech",
            "Demo Day",
        ],
        "category": "practicas",
        "tags": ["tecnologia", "startups", "usa", "silicon valley", "innovacion", "software"],
        "provider": {
            "id": "provider-11",
            "name": "Tech Abroad Programs",
            "logo": "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Estados Unidos"],
        "cities": ["San Francisco", "Palo Alto", "Mountain View"],
        "duration": {"min": 3, "max": 6, "type": "meses"},
        "cost": {
            "min": 5000,
            "max": 8000,
            "currency": "USD",
            "includes": [
                "Colocacion en startup",
                "Visa J-1 tramite",
                "Mentoria profesional",
                "Workshops y eventos",
                "Soporte durante programa",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (compartido desde $1200/mes)",
                "Alimentacion",
                "Transporte local",
            ],
        },
        "budgetTier": "alto",
        "eligibility": {
            "ageRange": {"min": 20, "max": 30},
            "requiredEducation": ["Estudiante o recien graduado en tecnología, negocios o diseno"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "CV en inglés",
                "Portfolio (para roles tecnicos)",
                "Certificado de estudios",
                "Video presentacion",
            ],
            "languageRequirement": "avanzado",
            "languageTests": ["TOEFL iBT 80+", "IELTS 6.5+"],
        },
        "startDates": ["Enero 2025", "Mayo 2025", "Septiembre 2025"],
        "deadlines": [
            {
                "name": "Cohorte Enero",
                "date": "2024-10-15",
                "type": "application",
            },
            {
                "name": "Cohorte Mayo",
                "date": "2025-02-15",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1504384764586-bb4cdc1707b0?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1531482615713-2afd69097998?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=800&h=600&fit=crop"},
        ],
        "featured": True,
        "active": True,
    },
    {
        "id": "oferta-12",
        "slug": "voluntariado-tanzania-safari",
        "name": "Voluntariado Conservacion en Tanzania",
        "shortDescription": "Contribuye a la conservacion de vida silvestre africana. Trabaja con elefantes, leones y más en su habitat natural.",
        "fullDescription": (
            "Tanzania alberga algunos de los ecosistemas más espectaculares del planeta. Este programa te permite contribuir directamente a su conservacion.\n\n"
            "**Proyectos disponibles:**\n\n"
            "**1. Conservacion de elefantes**\n"
            "- Monitoreo de manadas\n"
            "- Investigacion de comportamiento\n"
            "- Reduccion de conflictos humano-animal\n"
            "- Ubicación: Parque Nacional Tarangire\n\n"
            "**2. Proteccion de grandes felinos**\n"
            "- Monitoreo de leones y leopardos\n"
            "- Camaras trampa\n"
            "- Trabajo con comunidades Maasai\n"
            "- Ubicación: Serengeti\n\n"
            "**3. Veterinaria de vida silvestre**\n"
            "- Asistencia en tratamientos\n"
            "- Rescate de animales\n"
            "- Educacion comunitaria\n"
            "- Requiere background medico/veterinario\n\n"
            "**Experiencia incluida:**\n"
            "- Safari en Serengeti\n"
            "- Visita crater Ngorongoro\n"
            "- Interaccion con comunidades locales\n"
            "- Certificado de conservacion"
        ),
        "highlights": [
            "Safari incluido",
            "Trabajo con grandes felinos",
            "Alojamiento en lodge",
            "Impacto real",
            "Certificado de conservacion",
        ],
        "category": "voluntariado",
        "tags": ["africa", "safari", "conservacion", "animales", "naturaleza", "tanzania"],
        "provider": {
            "id": "provider-12",
            "name": "African Wildlife Conservation",
            "logo": "https://images.unsplash.com/photo-1516426122078-c23e76319801?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Tanzania"],
        "cities": ["Arusha", "Serengeti", "Tarangire"],
        "duration": {"min": 2, "max": 8, "type": "semanas"},
        "cost": {
            "min": 1500,
            "max": 4000,
            "currency": "USD",
            "includes": [
                "Alojamiento en lodge",
                "Tres comidas diarias",
                "Safari de bienvenida",
                "Transporte al proyecto",
                "Entrenamiento y equipo",
                "Coordinador 24/7",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Visa de Tanzania ($50)",
                "Vacunas recomendadas",
                "Seguro de viaje",
                "Safaris adicionales",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 65},
            "requiredDocuments": [
                "Pasaporte vigente (6 meses)",
                "Certificado de vacunas",
                "Seguro de viaje con evacuacion",
                "Formulario medico",
            ],
            "languageRequirement": "basico",
        },
        "startDates": ["Disponible todo el año"],
        "deadlines": [
            {
                "name": "Inscripcion continua",
                "date": "2025-12-31",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1516426122078-c23e76319801?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1547970810-dc1eac37d174?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1489392191049-fc10c97e64b6?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-13",
        "slug": "pregrado-negocios-holanda",
        "name": "Pregrado en Negocios - Holanda",
        "shortDescription": "Estudia tu carrera completa en una de las economias más innovadoras de Europa. Programas 100% en inglés.",
        "fullDescription": (
            "Holanda ofrece educación de clase mundial a precios accesibles para estudiantes internacionales. Con programas completamente en inglés y un mercado laboral dinámico.\n\n"
            "**Universidades asociadas:**\n"
            "- University of Amsterdam\n"
            "- Rotterdam School of Management\n"
            "- Tilburg University\n"
            "- Radboud University\n"
            "- University of Groningen\n\n"
            "**Programas disponibles:**\n"
            "- International Business Administration\n"
            "- Economics & Business\n"
            "- Business Analytics\n"
            "- Entrepreneurship\n"
            "- Finance & Accounting\n\n"
            "**Ventajas de estudiar en Holanda:**\n"
            "- Educacion de alta calidad (top 100 mundial)\n"
            "- Programas 100% en inglés\n"
            "- Costo accesible vs UK/USA\n"
            "- Permiso de trabajo post-estudio\n"
            "- Hub de empresas multinacionales\n"
            "- Excelente calidad de vida\n\n"
            "**Soporte incluido:**\n"
            "- Asesoria de admision\n"
            "- Tramite de visa\n"
            "- Orientacion pre-partida\n"
            "- Buddy program al llegar"
        ),
        "highlights": [
            "Universidades top 100",
            "100% en inglés",
            "Permiso trabajo post-estudio",
            "Costo accesible",
            "Hub de multinacionales",
        ],
        "category": "carrera_completa",
        "tags": ["holanda", "negocios", "europa", "pregrado", "universidad", "internacional"],
        "provider": {
            "id": "provider-13",
            "name": "Study in Holland",
            "logo": "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Holanda"],
        "cities": ["Amsterdam", "Rotterdam", "La Haya", "Utrecht"],
        "duration": {"min": 6, "max": 8, "type": "semestres"},
        "cost": {
            "min": 8000,
            "max": 15000,
            "currency": "EUR",
            "includes": [
                "Asesoria de admision",
                "Tramite de aplicacion",
                "Soporte de visa",
                "Orientacion pre-partida",
                "Buddy program",
            ],
            "excludes": [
                "Matricula universitaria (EUR 2,200/año aprox)",
                "Vuelos",
                "Alojamiento (EUR 400-700/mes)",
                "Seguro de salud (EUR 100/mes)",
                "Libros y materiales",
            ],
        },
        "budgetTier": "alto",
        "eligibility": {
            "ageRange": {"min": 17, "max": 25},
            "requiredEducation": ["Bachillerato completado con buen promedio"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "Diploma de bachillerato",
                "Transcripciones",
                "Certificado de inglés",
                "Carta de motivacion",
                "Prueba de fondos",
            ],
            "languageRequirement": "avanzado",
            "languageTests": ["IELTS 6.0+", "TOEFL iBT 80+"],
        },
        "startDates": ["Septiembre 2025"],
        "deadlines": [
            {
                "name": "Admision regular",
                "date": "2025-05-01",
                "type": "application",
            },
            {
                "name": "Admision tardia",
                "date": "2025-07-01",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1512470876337-1dc8e16c5b84?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-14",
        "slug": "certificacion-ux-design-londres",
        "name": "Certificación UX/UI Design - Londres",
        "shortDescription": "Bootcamp intensivo de diseno de experiencia de usuario en una de las capitales creativas del mundo.",
        "fullDescription": (
            "Londres es un centro mundial del diseno y la creatividad. Este bootcamp intensivo te prepara para una carrera en UX/UI Design con proyectos reales.\n\n"
            "**El programa:**\n\n"
            "**Modulo 1: Fundamentos UX (3 semanas)**\n"
            "- Investigacion de usuarios\n"
            "- Arquitectura de información\n"
            "- User journey mapping\n"
            "- Principios de usabilidad\n\n"
            "**Modulo 2: UI Design (3 semanas)**\n"
            "- Sistemas de diseno\n"
            "- Tipografia y color\n"
            "- Figma avanzado\n"
            "- Prototipado interactivo\n\n"
            "**Modulo 3: Proyecto Final (2 semanas)**\n"
            "- Cliente real de la industria\n"
            "- Proceso completo de diseno\n"
            "- Presentacion ante jurado\n"
            "- Portfolio profesional\n\n"
            "**Metodologia:**\n"
            "- Clases presenciales 9am-5pm\n"
            "- Proyectos prácticos diarios\n"
            "- Mentoria 1:1 semanal\n"
            "- Workshops con profesionales\n\n"
            "**Extras:**\n"
            "- Visitas a estudios de diseno\n"
            "- Networking con la industria\n"
            "- Acceso a Figma Pro (1 año)"
        ),
        "highlights": [
            "Proyecto con cliente real",
            "Portfolio profesional",
            "Figma Pro incluido",
            "Networking industria",
            "Certificación reconocida",
        ],
        "category": "certificacion_corta",
        "tags": ["diseno", "ux", "ui", "londres", "bootcamp", "tecnologia", "figma"],
        "provider": {
            "id": "provider-14",
            "name": "London Design Academy",
            "logo": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Reino Unido"],
        "cities": ["Londres"],
        "duration": {"min": 8, "max": 8, "type": "semanas"},
        "cost": {
            "min": 4500,
            "max": 5500,
            "currency": "EUR",
            "includes": [
                "Curso completo",
                "Material y recursos",
                "Figma Pro 1 año",
                "Certificado",
                "Proyecto con cliente real",
                "Networking events",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (desde GBP 800/mes)",
                "Alimentacion",
                "Visa (si aplica)",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 45},
            "requiredDocuments": [
                "Pasaporte vigente",
                "Portfolio basico (opcional)",
                "CV",
                "Carta de motivacion",
            ],
            "languageRequirement": "intermedio",
            "languageTests": ["Ingles B2+"],
        },
        "startDates": ["Febrero 2025", "Mayo 2025", "Septiembre 2025"],
        "deadlines": [
            {
                "name": "Cohorte Febrero",
                "date": "2025-01-15",
                "type": "application",
            },
            {
                "name": "Cohorte Mayo",
                "date": "2025-04-01",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1517292987719-0369a794ec0f?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-15",
        "slug": "work-travel-nueva-zelanda",
        "name": "Work & Travel Nueva Zelanda",
        "shortDescription": "Trabaja y explora uno de los paises más hermosos del mundo. Paisajes de pelicula y aventura garantizada.",
        "fullDescription": (
            "Nueva Zelanda es el destino sonado para amantes de la naturaleza y la aventura. Con la visa Working Holiday puedes trabajar y viajar por hasta 12 meses.\n\n"
            "**Tipos de trabajo comunes:**\n"
            "- Agricultura y horticultura (picking de frutas)\n"
            "- Hoteleria y hospitalidad\n"
            "- Turismo y aventura\n"
            "- Trabajo en ski resorts (invierno)\n"
            "- Au pair\n\n"
            "**Destinos populares:**\n"
            "- Queenstown (aventura extrema)\n"
            "- Auckland (ciudad cosmopolita)\n"
            "- Wellington (capital cultural)\n"
            "- Rotorua (cultura Maori)\n"
            "- Milford Sound (naturaleza epica)\n\n"
            "**Beneficios del programa:**\n"
            "- Visa Working Holiday (12 meses)\n"
            "- Colocacion laboral inicial\n"
            "- Orientacion en Auckland\n"
            "- SIM card y cuenta bancaria\n"
            "- Soporte continuo\n\n"
            "**Experiencias únicas:**\n"
            "- Bungee jumping en Queenstown\n"
            "- Hobbiton\n"
            "- Glaciares y fiordos\n"
            "- Cultura Maori"
        ),
        "highlights": [
            "12 meses de visa",
            "Paisajes de pelicula",
            "Trabajo garantizado inicial",
            "Aventura extrema",
            "Cultura Maori",
        ],
        "category": "work_travel",
        "tags": ["nueva zelanda", "aventura", "naturaleza", "working holiday", "oceania"],
        "provider": {
            "id": "provider-15",
            "name": "Kiwi Experience Programs",
            "logo": "https://images.unsplash.com/photo-1507699622108-4be3abd695ad?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Nueva Zelanda"],
        "cities": ["Auckland", "Queenstown", "Wellington", "Rotorua"],
        "duration": {"min": 6, "max": 12, "type": "meses"},
        "cost": {
            "min": 2000,
            "max": 3500,
            "currency": "USD",
            "includes": [
                "Tramite de visa WHV",
                "Orientacion en Auckland (3 dias)",
                "Colocacion laboral inicial",
                "SIM card",
                "Apertura cuenta bancaria",
                "Soporte 24/7",
            ],
            "excludes": [
                "Vuelos internacionales",
                "Alojamiento",
                "Alimentacion",
                "Seguro de viaje obligatorio",
            ],
        },
        "budgetTier": "medio",
        "eligibility": {
            "ageRange": {"min": 18, "max": 30},
            "requiredDocuments": [
                "Pasaporte vigente",
                "Prueba de fondos NZD $4,200",
                "Boleto de regreso o fondos adicionales",
                "Seguro de viaje completo",
            ],
            "languageRequirement": "intermedio",
            "languageTests": ["Ingles funcional"],
        },
        "startDates": ["Cualquier momento del año"],
        "deadlines": [
            {
                "name": "Inscripcion continua",
                "date": "2025-12-31",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1507699622108-4be3abd695ad?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1469521669194-babb45599def?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-16",
        "slug": "curso-inglés-malta",
        "name": "Curso de Ingles en Malta",
        "shortDescription": "Aprende inglés en una isla mediterránea con historia, playas y vida nocturna. La opciónmás económica de Europa.",
        "fullDescription": (
            "Malta es el secreto mejor guardado para aprender inglés en Europa. Ex-colonia británica con clima mediterráneo, precios accesibles y ambiente joven.\n\n"
            "**Por que Malta:**\n"
            "- Ingles es idioma oficial\n"
            "- Clima soleado todo el año\n"
            "- Más económico que UK o Irlanda\n"
            "- Playas espectaculares\n"
            "- Rica historia y cultura\n"
            "- Vida nocturna vibrante\n\n"
            "**El programa:**\n"
            "- 20 horas de clase/semana (estandar)\n"
            "- 30 horas de clase/semana (intensivo)\n"
            "- Grupos de maximo 12 estudiantes\n"
            "- Profesores nativos certificados\n"
            "- Niveles desde A1 hasta C2\n\n"
            "**Actividades incluidas:**\n"
            "- Excursion a Gozo y Comino\n"
            "- Tours historicos en Valletta\n"
            "- Beach activities\n"
            "- Intercambio de idiomas\n"
            "- Fiestas de bienvenida\n\n"
            "**Alojamiento:**\n"
            "- Residencia estudiantil (más social)\n"
            "- Familia anfitriona (inmersión)\n"
            "- Apartamento compartido"
        ),
        "highlights": [
            "Más económico de Europa",
            "Clima mediterráneo",
            "Playas increíbles",
            "Vida social activa",
            "Historia fascinante",
        ],
        "category": "curso_idiomas",
        "tags": ["inglés", "malta", "mediterráneo", "europa", "idiomas", "playa", "económico"],
        "provider": {
            "id": "provider-16",
            "name": "Malta English Academy",
            "logo": "https://images.unsplash.com/photo-1514222709107-a180c68d72b4?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Malta"],
        "cities": ["St. Julians", "Sliema", "Valletta"],
        "duration": {"min": 2, "max": 24, "type": "semanas"},
        "cost": {
            "min": 800,
            "max": 5000,
            "currency": "EUR",
            "includes": [
                "Matricula del curso",
                "Material didactico",
                "Examen de ubicacion",
                "Certificado de finalizacion",
                "Actividades semanales",
                "Wifi en escuela",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (desde EUR 150/semana)",
                "Alimentacion",
                "Seguro de viaje",
            ],
        },
        "budgetTier": "bajo",
        "eligibility": {
            "ageRange": {"min": 16, "max": 60},
            "requiredDocuments": [
                "Pasaporte o ID europeo",
                "Seguro de viaje",
            ],
            "languageRequirement": "ninguno",
        },
        "startDates": ["Todos los lunes del año"],
        "deadlines": [
            {
                "name": "Inscripcion continua",
                "date": "2025-12-31",
                "type": "enrollment",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1514222709107-a180c68d72b4?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1555990538-1e6e5c0e2c0b?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
    {
        "id": "oferta-17",
        "slug": "semestre-canada-vancouver",
        "name": "Semestre Académico en Canada - Vancouver",
        "shortDescription": "Estudia en una de las ciudades más habitables del mundo. Naturaleza, diversidad y excelencia académica.",
        "fullDescription": (
            "Vancouver combina lo mejor de ambos mundos: una ciudad cosmopolita rodeada de naturaleza espectacular. Ideal para estudiantes que buscan calidad de vida.\n\n"
            "**Universidades disponibles:**\n"
            "- University of British Columbia (UBC)\n"
            "- Simon Fraser University\n"
            "- University of Victoria\n"
            "- BCIT\n\n"
            "**Areas populares:**\n"
            "- Computer Science\n"
            "- Business & Management\n"
            "- Environmental Studies\n"
            "- Film & Media\n"
            "- Engineering\n\n"
            "**Por que Vancouver:**\n"
            "- Ciudad más habitable del mundo (ranking)\n"
            "- Diversidad cultural increible\n"
            "- Proximidad a naturaleza\n"
            "- Hub de tecnología y cine\n"
            "- Permiso de trabajo part-time\n"
            "- Post-study work permit\n\n"
            "**Actividades:**\n"
            "- Skiing en Whistler\n"
            "- Hiking en las Rockies\n"
            "- Kayak en el oceano\n"
            "- Explore Victoria y Seattle"
        ),
        "highlights": [
            "Ciudad más habitable",
            "Trabajo part-time permitido",
            "Naturaleza espectacular",
            "Hub de tecnología",
            "Post-study work permit",
        ],
        "category": "semestre_academico",
        "tags": ["canada", "vancouver", "universidad", "naturaleza", "tecnologia", "academico"],
        "provider": {
            "id": "provider-17",
            "name": "Study Canada West",
            "logo": "https://images.unsplash.com/photo-1559511260-66a654ae982a?w=100&h=100&fit=crop",
            "verified": True,
        },
        "countries": ["Canada"],
        "cities": ["Vancouver", "Victoria", "Burnaby"],
        "duration": {"min": 1, "max": 2, "type": "semestres"},
        "cost": {
            "min": 10000,
            "max": 18000,
            "currency": "USD",
            "includes": [
                "Matricula universitaria",
                "Tramite de visa",
                "Orientacion pre-partida",
                "Recogida aeropuerto",
                "Soporte académico",
                "Seguro medico estudiantil",
            ],
            "excludes": [
                "Vuelos",
                "Alojamiento (CAD 800-1500/mes)",
                "Alimentacion",
                "Transporte local",
                "Libros",
            ],
        },
        "budgetTier": "alto",
        "eligibility": {
            "ageRange": {"min": 18, "max": 30},
            "requiredEducation": ["Estudiante universitario (2+ semestres)"],
            "requiredDocuments": [
                "Pasaporte vigente",
                "Transcripciones",
                "Certificado de inglés",
                "Carta de motivacion",
                "Prueba de fondos",
            ],
            "languageRequirement": "avanzado",
            "languageTests": ["IELTS 6.5+", "TOEFL iBT 90+"],
        },
        "startDates": ["Septiembre 2025", "Enero 2026"],
        "deadlines": [
            {
                "name": "Fall semester",
                "date": "2025-04-01",
                "type": "application",
            },
            {
                "name": "Winter semester",
                "date": "2025-09-01",
                "type": "application",
            },
        ],
        "featuredImage": "https://images.unsplash.com/photo-1559511260-66a654ae982a?w=800&h=600&fit=crop",
        "media": [
            {"type": "image", "url": "https://images.unsplash.com/photo-1609825488888-3a766db05542?w=800&h=600&fit=crop"},
            {"type": "image", "url": "https://images.unsplash.com/photo-1503614472-8c93d56e92ce?w=800&h=600&fit=crop"},
        ],
        "featured": False,
        "active": True,
    },
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_all_ofertas() -> list[dict]:
    """Return all active ofertas."""
    return [o for o in OFERTAS if o.get("active")]


def get_oferta_by_slug(slug: str) -> Optional[dict]:
    """Return a single oferta matching the given slug, or None."""
    for o in OFERTAS:
        if o["slug"] == slug:
            return o
    return None


def get_featured_ofertas() -> list[dict]:
    """Return ofertas that are both featured and active."""
    return [o for o in OFERTAS if o.get("featured") and o.get("active")]


def filter_ofertas(filters: dict) -> list[dict]:
    """
    Filter ofertas by the supplied criteria.

    Supported filter keys
    ---------------------
    - category (str): exact match on oferta category
    - countries (list[str]): oferta must include at least one of these countries
    - budgetTier (str): exact match on budgetTier
    - duration (str): exact match on duration type (meses, semanas, semestres)
    - languageRequirement (str): oferta language requirement must be at most
      the given level (ninguno < basico < intermedio < avanzado)
    - searchQuery (str): case-insensitive substring search across name,
      shortDescription, tags, countries, and provider name
    """
    level_order = ["ninguno", "basico", "intermedio", "avanzado"]
    results = []

    for oferta in OFERTAS:
        if not oferta.get("active"):
            continue

        # category
        if "category" in filters and filters["category"]:
            if oferta["category"] != filters["category"]:
                continue

        # countries
        if "countries" in filters and filters["countries"]:
            if not any(c in oferta["countries"] for c in filters["countries"]):
                continue

        # budgetTier
        if "budgetTier" in filters and filters["budgetTier"]:
            if oferta["budgetTier"] != filters["budgetTier"]:
                continue

        # duration type
        dur_type = filters.get("durationType") or filters.get("duration")
        if dur_type:
            if oferta["duration"]["type"] != dur_type:
                continue

        # min/max duration
        if "minDuration" in filters and filters["minDuration"] is not None:
            if oferta["duration"]["max"] < filters["minDuration"]:
                continue
        if "maxDuration" in filters and filters["maxDuration"] is not None:
            if oferta["duration"]["min"] > filters["maxDuration"]:
                continue

        # languageRequirement
        if "languageRequirement" in filters and filters["languageRequirement"]:
            oferta_lang = oferta.get("eligibility", {}).get("languageRequirement", "ninguno")
            oferta_idx = level_order.index(oferta_lang) if oferta_lang in level_order else 0
            filter_idx = level_order.index(filters["languageRequirement"]) if filters["languageRequirement"] in level_order else 0
            if oferta_idx > filter_idx:
                continue

        # searchQuery
        if "searchQuery" in filters and filters["searchQuery"]:
            query = filters["searchQuery"].lower()
            searchable = " ".join([
                oferta["name"],
                oferta["shortDescription"],
                *oferta["tags"],
                *oferta["countries"],
                oferta["provider"]["name"],
            ]).lower()
            if query not in searchable:
                continue

        results.append(oferta)

    return results
