# Auditoría del catálogo de instituciones

**380 instituciones auditadas** de las 630 con sitio propio (el catálogo completo son 2.511 filas, todas a nivel institución).

Cada ficha se visitó **sólo en su dominio oficial**. Ver `README.md` para por qué eso no es opcional.

## Veredicto

| Veredicto | Fichas | % | Qué significa |
|---|---:|---:|---|
| `inservible` | 119 | 31% | **No se puede usar.** Extraer de aquí produce información falsa |
| `corregir` | 101 | 27% | Usable después de arreglar el dominio o el nombre |
| `revisar_a_mano` | 65 | 17% | Necesita ojos humanos: bloquea bots o su catálogo no es una lista |
| `observacion` | 73 | 19% | Usable, con un detalle que conviene mirar |
| `ok` | 22 | 6% | Sin observaciones |

## Por qué cada una quedó inservible

- **el dominio es de otra institución** · 55
- **duplicado de otra ficha** · 21
- **dominio muerto** · 16
- **no es una institución (agencia)** · 13
- **no es una institución (red)** · 11
- **la institución cerró** · 2
- **el convenio terminó** · 1

## Las inservibles, una por una

| Institución en la ficha | Motivo | Detalle |
|---|---|---|
| 4Life College | dominio muerto | DOMINIO MUERTO · hay que re-localizar la institucion |
| ABC School of English | dominio muerto | SERVIDOR CAIDO · puertos 80 y 443 rechazan · dominio abandonado |
| ALI | dominio muerto | DOMINIO MUERTO · DNS publico apunta a loopback |
| AMET Education | no es una institución (agencia) | NO ES INSTITUCION: agencia de reclutamiento + servicios migratorios. No dicta programas |
| Ability - MEGT | dominio muerto | DOMINIO MUERTO: NXDOMAIN, el dominio ya no existe |
| Academies Australasia | no es una institución (red) | ES UNA RED DE 18 COLLEGES, no una escuela |
| Academies Australasia Polytechnic | duplicado de otra ficha | DUPLICADO exacto con la ficha siguiente |
| Academies Australasia Polytechnic (AAPOLY) | duplicado de otra ficha | DUPLICADO de la anterior · fusionar |
| Albright | el dominio es de otra institución | ciudades mal (dice Perth, no aparece); categoria subestima: es mayoritariamente VET |
| Amerigo | no es una institución (agencia) | NO ES UN COLEGIO: red que ubica en 32+ colegios socios. Venderla como institucion es incorrecto |
| Ascent College of technology | el dominio es de otra institución | INSTITUCION DISTINTA: el sitio no menciona Ascent. Ficha dice publico y es privado |
| AIBT - International | duplicado de otra ficha | DUPLICADO de la ficha anterior: mismo dominio, el sitio nunca menciona una entidad separada |
| Australian College of Dance | el dominio es de otra institución | INSTITUCION FANTASMA: ALG no tiene NI UN curso de danza y nunca menciona este nombre. Candidata a eliminar |
| Australian College of Sport & Fitness | el dominio es de otra institución | El dominio es de ALG; el nombre no aparece en el sitio. Si hay cursos de fitness pero bajo marca ALG |
| Australian International High School | dominio muerto | DOMINIO MUERTO: academies.nsw.edu.au no resuelve DNS |
| Australian Learning Group (ALG) | el dominio es de otra institución | Es la institucion real detras de las 2 fichas fantasma (Dance y Sport & Fitness) |
| Fleming College | el dominio es de otra institución | Ficha dice "College Privado" pero es un colegio PUBLICO de Ontario; partner_group=GUS no aparece en el sitio ( |
| Munich Business School | dominio muerto | El campo `sitio` dice literalmente "nait" — no es un dominio. "NAIT" es el acronimo del Northern Alberta Insti |
| Royal Greenhill Institute of Technology | dominio muerto | DOMINIO MUERTO confirmado contra DNS publico 8.8.8.8: NXDOMAIN tanto en www.rgit.edu.au como en el apex rgit.e |
| New England College | no es una institución (agencia) | El dominio de la ficha NO es el de la institucion (nec.edu) sino el micrositio del partner INTO. Lo que se ext |
| SCEI | el dominio es de otra institución | `puede_vender` INCONSISTENTE: la ficha lo clasifica como "Instituto Idiomas" y habilita "Idiomas", pero el sit |
| CCEL - Canadian College of English Language | duplicado de otra ficha | los diplomas vocacionales que aparecen son de PARTNERS (Canadian College, Stenberg College), NO los otorga CCE |
| Union College | el dominio es de otra institución | "American Honors Program" y "American Success Program" de puede_vender NO APARECEN en el sitio · ficha dice ci |
| ICP - University of Portsmouth | el dominio es de otra institución | 🔴 FICHA FANTASMA: el dominio apunta al holding Navitas, no al college. En navitas.com "ICP" solo aparece como  |
| New College Group - ncg | duplicado de otra ficha | es un GRUPO multi-campus, no una escuela · ficha dice "Manchester, Liverpool" pero el sitio tambien lista Ches |
| Browns English Language | duplicado de otra ficha | ficha dice solo Brisbane; el sitio lista Brisbane, Gold Coast y Melbourne · RTO 31998 / CRICOS 02663M (es RTO, |
| Gold Coast Learning Centre | duplicado de otra ficha | puede_vender inconsistente: ficha marcada solo ["Idiomas","Idiomas"] (valor DUPLICADO) y category "Instituto I |
| LTL language school | no es una institución (red) | Es una RED de escuelas propias en 4 idiomas (mandarin, japones, coreano, vietnamita) y ~16 ciudades, no una es |
| Supreme Business College | no es una institución (red) | DOMINIO PARAGUAS: el sitio es del grupo, no de esta escuela. Supreme Business College SI figura como uno de su |
| DID deutsch-institut worldwide | duplicado de otra ficha | El nombre real no lleva "worldwide" (es did deutsch-institut GmbH). Las sedes de adultos si coinciden con la f |
| High School Otawa Carleton SD | no es una institución (red) | NO es un high school: es un distrito escolar publico con 120+ colegios. El nombre de la ficha esta mal escrito |
| Ulster University | el dominio es de otra institución | PAIS MAL EN LA FICHA: es Irlanda del Norte (UK), no Ireland · campus actuales del sitio: Belfast, Coleraine, D |
| University of Waikato College | el dominio es de otra institución | FANTASMA: el dominio de la ficha es el del GRUPO Navitas, no el del college · el sitio no es la institucion ·  |
| IES College | la institución cerró | INSTITUCION CERRADA: el sitio solo sirve el aviso "ceased operations on 31st January 2026" + formulario para p |
| Swansea College and University (TCSU) | el dominio es de otra institución | FANTASMA + DUPLICADO DE DOMINIO: apunta al grupo Navitas igual que la ficha de Waikato College · el dominio pr |
| NYLC | duplicado de otra ficha | ficha usa la sigla NYLC · 3 sedes (Upper West Side, Jackson Heights Queens, Bronx), no solo "New York" generic |
| University of Exeter | el dominio es de otra institución | ficha marca partner_group INTO pero el dominio es el de la universidad y NO menciona INTO · los Foundation/Yea |
| Lipscomb University | el convenio terminó | CONVENIO TERMINADO: la pagina dice "our contract with the university has ended" y remite a lipscomb.edu · el p |
| Navitas Professional Institute | el dominio es de otra institución | FANTASMA + MUERTO EFECTIVO: la marca ya no opera · el dominio de la ficha tiene certificado TLS EXPIRADO desde |
| Encompass | no es una institución (agencia) | NO ES INSTITUCION: es una agencia de colocacion e intercambio en EEUU/Canada, no imparte nada propio · la fich |
| International House | el dominio es de otra institución | FANTASMA: la ficha dice Sydney, Australia y el directorio oficial NO lista ninguna escuela en Australia (si Va |
| Brisbane School of Beauty | el dominio es de otra institución | FANTASMA PARCIAL: la marca "Brisbane School of Beauty" NO existe en el sitio; lo que opera es PELUQUERIA y BAR |
| Azurlingua | el dominio es de otra institución | La URL EXACTA de la ficha (https://www.azurlingua.com/) NO carga: el certificado sólo cubre azurlingua.com, el |
| FIC - Simon Fraser University | el dominio es de otra institución | FANTASMA: el dominio es el de la universidad, no el de FIC (Fraser International College, pathway de Navitas,  |
| Gedu Globlal Education | no es una institución (red) | NO ES UNA INSTITUCIÓN: es un grupo paraguas UK (Greenford) que agrupa Global Banking School, English Path, Aus |
| Education Queensland International (EQI) | no es una institución (red) | NO ES UNA INSTITUCIÓN: es el brazo internacional del gobierno de Queensland que coordina la red de colegios pú |
| ICRGU - Robert Gordon University | no es una institución (red) | DOMINIO EQUIVOCADO/COMPARTIDO: la ficha apunta al grupo Navitas, no a ICRGU ni a Robert Gordon University. "In |
| Global Village English Centres | el dominio es de otra institución | El nombre de la ficha, "Global Village English Centres", NO aparece en el sitio: hoy se presenta como "Global  |
| La Trobe University Sydney | duplicado de otra ficha | Cloudflare challenge confirmado (HTTP 403 + header `Cf-Mitigated: challenge` + body "Just a moment...") inclus |
| Liverpool John Moores University | no es una institución (agencia) | El dominio NO es el de la universidad (ljmu.ac.uk) sino el centro pathway operado por Study Group. Coherente c |
| Nacel Espana | no es una institución (agencia) | NO ES UNA INSTITUCION EDUCATIVA: es una agencia de viajes linguisticos, es decir el mismo tipo de negocio que  |
| Georgian English | el dominio es de otra institución | FICHA FANTASMA: "Georgian English" no existe como marca ni como programa en el sitio. El dominio es el del Geo |
| Oxford Royale | no es una institución (agencia) | El propio sitio declara que "does not operate under the aegis of the University of Oxford or those other insti |
| TAFE Queensland | no es una institución (red) | Es una RED de 60+ sedes agrupadas en 6 regiones (Greater Brisbane, Gold Coast, Sunshine Coast, Wide Bay Burnet |
| QS | no es una institución (agencia) | NO ES UNA INSTITUCION Y NO TIENE CATALOGO. La URL de la ficha es la pantalla de LOGIN de un SaaS de admisiones |
| Intensive English Language Institute (IELI) | dominio muerto | DOMINIO MUERTO confirmado contra DNS publico 8.8.8.8: NXDOMAIN tanto en www.ieli.com.au como en el apex ieli.c |
| La Trobe University | duplicado de otra ficha | Mismo Cloudflare challenge que la ficha de Sydney (403 + `Cf-Mitigated: challenge` con UA de Chrome). Sitio vi |
| Whitecliffe University of Applied Sciences | no es una institución (agencia) | PAIS Y CIUDAD ERRADOS: la ficha dice UK / Belfast y la universidad esta en BERLIN, ALEMANIA (Charlottenburg),  |
| The University of Oklahoma | no es una institución (agencia) | El dominio de la ficha NO es el de la universidad (ou.edu) sino el micrositio del partner INTO. Lo que se extr |
| iEdu.Study | dominio muerto | FICHA ROTA + FANTASMA. `sitio`="www.iedu.study.com" es NXDOMAIN confirmado contra 8.8.8.8 — el dominio esta MA |
| University of Kent | el dominio es de otra institución | CATALOGO NO ENUMERABLE: /courses es un buscador dinamico ("Search all available courses" por nombre, materia o |
| New Jersey Institute of Technology | el dominio es de otra institución | `partner_group`="Study Group" NO aparece en ningun lado de njit.edu (ni Study Group, ni pathway, ni Navitas, n |
| Central Australian College CAC | la institución cerró | La ciudad de la ficha esta mal: dice "Tasmania, Melbourne" y los campus reales son Melbourne CBD, West Footscr |
| Performance education | no es una institución (agencia) | ALERTA GRAVE · `puede_vender` FALSO. La ficha lo clasifica "College Privado" y habilita "Pregrado & Postgrado" |
| North Sydney English College NSEC | dominio muerto | DOMINIO MUERTO / PARQUEADO, confirmado contra DNS publico 8.8.8.8: northsydneycollege.com.au y su www resuelve |
| High Schools International Ireland | no es una institución (agencia) | ALERTA GRAVE · NO ES UNA INSTITUCION EDUCATIVA. Es una agencia de colocacion y guardianship con sede en Dublin |
| OHLA - Open Hearts Language Academy | el dominio es de otra institución | CIUDAD DESACTUALIZADA: la ficha lista "Miami, Boca Raton, Orlando, Tampa" y el sitio solo muestra Miami, Orlan |
| International House - LSI PORTSMOUTH | el dominio es de otra institución | FANTASMA + DOMINIO EQUIVOCADO: la ficha apunta al paraguas IH World, no a la escuela · el dominio propio es ls |
| International House - London | el dominio es de otra institución | FANTASMA + DUPLICADO DE DOMINIO: mismo ihworld.com que la ficha de LSI Portsmouth · el dominio propio de la es |
| Nova Southeastern University | el dominio es de otra institución | CATALOGO NO ENUMERABLE: selector con filtro dinamico por tipo de grado, no lista plana · la ficha marca partne |
| BCUIC - Birmingham City University | duplicado de otra ficha | EL DOMINIO NAVITAS DE LA FICHA YA NO ES EL VIGENTE: redirige al dominio de la universidad · category "Universi |
| International House - Brisbane | el dominio es de otra institución | FANTASMA: el dominio es el de la RED IH (130+ escuelas afiliadas en 45+ paises, "privately owned and operated" |
| BPP University | el dominio es de otra institución | el dominio es el del GRUPO, no el de la universidad: aloja Firebrand, StaySharp, Buttercups, Estio, Digital Ma |
| The University of Adelaide College | dominio muerto | CAMBIO DE MARCA + HOST MUERTO: el subdominio exacto de la ficha (www.) NO RESUELVE en DNS publico · el apex re |
| EP English Path / GBS Group | el dominio es de otra institución | CIUDADES MAL: la ficha dice Londres/Manchester/Birmingham/Leeds y el sitio NO lista Manchester · si lista 11 c |
| The Language Gallery - TLG | el dominio es de otra institución | DOS ERRORES GRAVES: (1) PAIS FALSO - la ficha dice Canada / Toronto y Vancouver y el sitio NO menciona Canada  |
| Victorian Government Schools | no es una institución (red) | Cloudflare "Just a moment..." devuelve 403 incluso con UA de Chrome; NO es dominio muerto (DNS resuelve contra |
| ILSC | no es una institución (red) | Dominio de GRUPO paraguas: 5 paises (Canada, Australia, Irlanda, India, USA/ELS) + Greystone College. La ficha |
| BLI | duplicado de otra ficha | `puede_vender` trae "Idiomas" duplicado dos veces. Sedes reales Montreal y Quebec City (Canada) + Ciudad de Me |
| University of Massachusetts Amherst | el dominio es de otra institución | FICHA FANTASMA: el dominio es del holding INTO, no de UMass · ADEMAS los links internos de /degrees y /search  |
| Southern Illinois Universiy | el dominio es de otra institución | FICHA FANTASMA: el dominio es del holding INTO, no de SIU · TYPO en el nombre de la ficha ("Universiy") · los  |
| Institut Europeen de Francais | dominio muerto | DOMINIO MUERTO + MARCA ABSORBIDA: el TLD .es es imposible para una escuela en Montpellier (contaminacion o typ |
| BWS - Germanlingua | duplicado de otra ficha | CATALOGO NO ENUMERABLE desde un solo sitio: la oferta esta partida en 3 paginas por ciudad (Munich, Berlin, Co |
| Universal English | duplicado de otra ficha | partner_group DESACTUALIZADO: la ficha dice "Universal Learning Group" pero desde julio 2024 pertenece al OXFO |
| SERO Institute | dominio muerto | DOMINIO EQUIVOCADO: le falta el `.au`, y ademas viene SIN protocolo · CORREGIR sitio a https://seroinstitute.c |
| Loyola University New Orleans | el dominio es de otra institución | partner_group "Wellspring" NO aparece en ningun lado del sitio oficial — no verificable desde el dominio, conf |
| Wilfrid Laurier University | el dominio es de otra institución | puede_vender promete "Idiomas" y "Foundation & Pre master" que NO aparecen en el buscador de programas del sit |
| John Paul College | el dominio es de otra institución | FICHA FANTASMA PARCIAL: el dominio NO es el del colegio. John Paul College vive en jpc.qld.edu.au (responde 20 |
| MTA Institute | dominio muerto | DOMINIO SIN WEB: mtai-international.edu.au tiene SOA/NS en netregistry pero CERO registros A/AAAA en 8.8.8.8 y |
| The university of Manchester | el dominio es de otra institución | catalogo es BUSCADOR dinamico por nivel y año de entrada, no lista plana · puede_vender incluye "Pathway" pero |
| YMCA | el dominio es de otra institución | FICHA FANTASMA: ymca.ca dice textualmente que NO ofrece programas ni servicios al publico, solo apoya a las as |
| Australian Technical And Management College (ATMC) | dominio muerto | SUBDOMINIO DE LA FICHA MUERTO: vet.atmc.edu.au da NXDOMAIN en 8.8.8.8 (el apex atmc.edu.au resuelve a 154.210. |
| TAFE Western Australia | el dominio es de otra institución | NO es una institucion sino la oficina que comercializa y matricula internacionales para la red TAFE WA (Albany |
| Cork English Academy | duplicado de otra ficha | acreditada ACELS y miembro de MEI · puede_vender trae "Idiomas" DUPLICADO · catalogo pequeño y enumerable, sin |
| TLA The Language Academy | dominio muerto | SITIO CAIDO POR ERROR DE SERVIDOR: HTTP 500 Internal Server Error consistente en apex, www, http->https y ruta |
| Study Group | no es una institución (agencia) | NO ES UNA INSTITUCION: es un proveedor de pathways / red que co-disena programas con universidades (la ficha l |
| University of Sussex | el dominio es de otra institución | CATALOGO NO ENUMERABLE: /study/ es un buscador dinamico con dropdown de nivel/materia, no una lista estatica — |
| Milan Polytechnic University - MIP - POLIMI | el dominio es de otra institución | FICHA FANTASMA MIXTA (patron a): el nombre es el de MIP —la escuela de negocios— pero el `sitio` es el dominio |
| Clarendon Business College | el dominio es de otra institución | FANTASMA CONFIRMADO (patron a): el `sitio` es el dominio del HOLDING Academies Australasia, que alberga 18 col |
| Nova Southeastern University's Barry and Judy Silverman College of Pharmacy | el dominio es de otra institución | 🔴 FANTASMA TOTAL. El dominio es una cadena de escuelas de idioma japones EN JAPON. Ni "Nova Southeastern Unive |
| UEC Business (previously known as Ambridge Institute) | el dominio es de otra institución | 🔴 Sitio caido funcionalmente: devuelve 200 pero sirve la pagina de mantenimiento de WordPress; imagen de fondo |
| Cambrian College | el dominio es de otra institución | La ficha dice ciudad "Sudbury, Vancouver". El sitio SOLO lista Sudbury, Ontario (1400 Barry Downe Rd, P3A 3V8) |
| Durham University | el dominio es de otra institución | Patron (b) en version suave: devuelve 403 a fetchers sin UA de navegador y 200 con UA de Chrome (Server: Apach |
| UNIVERSITY ACADEMY 92 (UA92) | el dominio es de otra institución | ⚠️ `partner_group` dice "Navitas", pero el sitio se declara "founded by the Class of 92 and Lancaster Universi |
| GISMA University of applied Sciences | el dominio es de otra institución | ⚠️ La ficha dice Hannover. El sitio lista Potsdam (sede principal), Berlin y Londres. Hannover NO aparece: Gis |
| Missouri State University - MSU | duplicado de otra ficha | CIUDAD MAL EN LA FICHA: "Missouri" es el estado; la ciudad es Springfield MO · puede_vender trae "Idiomas" DUP |
| University of Greenwich | el dominio es de otra institución | LO QUE LA FICHA PERMITE VENDER NO VIVE EN ESTE DOMINIO: puede_vender es "Foundation & Pre master / Solo pathwa |
| GISMA Business School | el dominio es de otra institución | CAMBIO DE NOMBRE Y DE CIUDAD: ya no se llama "GISMA Business School" sino "Gisma University of Applied Science |
| IT Step Academy | el dominio es de otra institución | FANTASMA POR PAIS: la ficha dice BULGARIA y el dominio es el de la sede de MEXICO (Tijuana) · CERO menciones a |
| DePaul University | duplicado de otra ficha | GRAVE: el dominio de la ficha ya no pertenece a DePaul. El modelo cambio de pathway center on-campus ("Global  |
| UP International College New Zealand- AUT Certificate in Foundation Studies | el dominio es de otra institución | GRAVE · INSTITUCION FANTASMA: el dominio es de ACG Schools (grupo K-12 del holding Inspired). CERO menciones d |
| CIC Higher Education | el dominio es de otra institución | GRAVE · INSTITUCION FANTASMA: el nombre "CIC Higher Education" NO aparece en ninguna parte del sitio destino.  |
| International House Malta | no es una institución (red) | El `sitio` apunta a la RED mundial IH, no a la escuela de Malta. El sitio si lista "IH Malta" (St Julian's) de |
| Colorado State University | el dominio es de otra institución | GRAVE: el `partner_group` "INTO" parece TERMINADO — `into.colostate.edu` responde NXDOMAIN contra DNS publico  |
| Toronto School of Management | el dominio es de otra institución | El sitio NO menciona pertenencia a GUS (Global University Systems): el `partner_group: GUS` de la ficha no se  |
| Excel English Institute | duplicado de otra ficha | Ficha dice `ciudad: "Texas"` que es el estado, no la ciudad: real es Dallas TX con dos campus (Richardson y Ar |
| Oregon State University | el dominio es de otra institución | `partner_group: INTO` NO VERIFICABLE en el dominio oficial: la home no menciona INTO y el subdominio `into.ore |
| New Brunswick International Student Program NBISP | duplicado de otra ficha | CRITICO: el `sitio` apunta a CAPS-I, una ASOCIACION paraguas de distritos escolares publicos canadienses, no a |
| Scots English College | duplicado de otra ficha | `sitio` sin esquema en la ficha. `ciudad: "Nueva Gales del Sur"` es el estado, no la ciudad: real es Sydney co |

---

El detalle completo, institución por institución, está en `auditoria_consolidada.csv`.
