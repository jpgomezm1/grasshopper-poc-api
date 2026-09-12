# Prompt de investigación por subagents · v1

El prompt que se le pasa a cada subagent que toma un lote. Vive en un archivo
—y no copiado en cada despacho— para que las lecciones de un lote lleguen al
siguiente en vez de perderse.

**Cómo se usa:** se despacha un agente por lote, con este texto y el número de
lote sustituido en las dos rutas.

**Bitácora de cambios**

- *v1 · 2026-09-08* · versión inicial, derivada de `PROMPT_EXTRACCION.md` (el del
  pipeline manual) más lo aprendido en el piloto por API: el vocabulario cerrado
  de áreas y la obligación de `url_fuente` en el dominio oficial.
- *v3.3 · extracción lote 02 (USA)* · **en EE.UU. la marca de elegibilidad internacional existe, es
  literal, y está en la ficha de marketing — no en el catálogo.** Montclair la escribe como
  `*F1/J1 visa seeking students are not eligible for this program.` y **saca 69 de 280 fichas**:
  no sólo certificados, también un Psy.D. en School Psychology, un MSN Pre-Licensure, un MFA de
  Dance y varios MA online. Ojo con la segunda redacción, que **no es una baja sino una
  condición**: *"...not eligible for this certificate program **unless they are currently pursuing
  a master's degree at Montclair State University**"* (29 fichas) — sigue fuera para quien llega
  de Colombia, pero por una razón distinta. La marca vive en `montclair.edu/academics/programs/<slug>`;
  el catálogo Courseleaf (`catalog.montclair.edu/programs/`, 514 entradas) **no la trae**, así que
  extraer del catálogo y no de la ficha habría cargado 69 programas invendibles.
  Y **el `codigo_oficial` en EE.UU. es `-` por diseño, igual que en Canadá**: no hay equivalente al
  CRICOS. Los "program codes" (LCR 611, ELAD 510) son internos y los CIP son estadísticos. 695 filas
  en este lote, cero códigos: eso es correcto, no extracción floja.
  Cuatro notas de plomería, las cuatro sobre listados que parecen vacíos:
  **(1) Un `degrees.html` sin un solo enlace de programa tiene el catálogo en una variable inline.**
  Nova Southeastern: `program_json = "/_resources/dmc/php/programs.php?datasource=programs&...&returntype=json"`
  → 293 programas con `degrees`, `colleges` y `locations`. Ahí se ve que 68 son minors y 40 "Dual
  Admission", y que hay **URLs `_archive/` sirviendo duplicados vivos** (un B.S. in Engineering y un
  "MBA in Finance" que en realidad es el de accounting archivado).
  **(2) El buscador de NJIT es un proxy de Elasticsearch**: `drupalSettings` publica
  `eshost:"/search-api"` y el bundle el path `/search-api/corporate/major/_search`. El tipo `major`
  da 68 (taxonomía), pero **el que sirve es `degree`: 215 documentos** con `degree_level_terms`,
  `required_credits` y `catalog_url`. Probar los tipos uno por uno cuesta 5 peticiones.
  **(3) WordPress otra vez, y `wp-json/wp/v2/types` otra vez lo zanja**: New England College declara
  el CPT `programs` → 98 fichas con `class_list` (`programs_level-*`, `program_location-*`), igual
  que el `class_list` de Oxford International. Además `nec.edu/programs/` **redirige a un
  `wp-content/uploads/2022/04/programs.csv`** — útil como contraste, pero es de 2022 y no trae URLs:
  no lo uses como fuente.
  **(4) Una sigla puede haber cambiado de dueño.** `international.missouristate.edu/eli/` (English
  Language Institute) **redirige hoy a `fli.missouristate.edu`**, el Foreign Language Institute: el
  programa intensivo de inglés ya no existe y lo reemplazó el "I Succeed Course Package" de 14
  créditos. Seguir el 301 en vez de dar el ELI por vivo es la diferencia entre vender un programa
  que existe y uno que no.
  Y el falso positivo evitado: **NYLC marca cuál de sus programas sirve para visa** —
  *"Students on an F-1 visa must choose this program"* en el Intensive; los otros cinco dicen
  "designed for working adults" / "students who live and work in New York". Es la regla del
  part-time del v2.4, escrita por el propio sitio.
- *v3.2 · extracción lote 04 (UK)* · **un `codigo_oficial` puede salir de la fuente y aun así ser
  falso: el de plantilla.** Exeter publica el UCAS en un `class="exeter-course-ucascode"` limpísimo,
  y en las **50 fichas de `/masters-degrees/` del lote devolvía `1234`** — el marcador de relleno de
  la plantilla, idéntico en todas. Grepear el HTML no basta: el posgrado británico **no tiene UCAS**,
  así que un código repetido en decenas de fichas de un mismo nivel es plantilla, no dato. Comprueba
  la cardinalidad antes de emitir (aquí: 50 ×`1234` vs. 92 códigos únicos en pregrado).
  Tres formas más de la marca de elegibilidad internacional, las tres en el cuerpo y ninguna en el listado:
  **(1) Huddersfield la pone y te tumba una categoría entera** — *"This programme is not available to
  international students. Instead, international students should apply for our international foundation
  programmes delivered by our International Study Centre"* aparece en los **39 cursos con flag
  `Foundation Year`**. Trampa: sólo las fichas del año **2026-27** la llevan; sus gemelas 2027-28 no
  la traen y encima **muestran tarifa internacional**. La ficha que sí avisa manda sobre su clon.
  **(2) En Greenwich la marca es la *ausencia* de una tarifa** — el bloque dice "Home /international
  fees" y **50 de 188 fichas no tienen la mitad internacional**: son exactamente las de práctica
  clínica NHS, prescribing, PGCE con EYTS, trabajo social y las "with Industrial Practice". Además
  publica `/international/capped-courses` ("Closed Programmes"), la lista de los que ya se llenaron
  para internacionales en el intake vigente — estado de cupo, no baja del programa.
  **(3) Falso positivo de manual en Leeds**: "UK applicants only" salió en 2 fichas y hablaba del
  *Access to HE Diploma* como cualificación de entrada, no del curso. Lee la frase entera.
  Y dos notas de plomería: **el catálogo de Huddersfield (JS) vive en un Solr de SearchStax cuyo
  endpoint y token están en el `const config` inline de la home** (`searchURL` + `searchAuth`); con
  `model=Coursefinder` da 750 fichas — el perfil por defecto las excluye explícitamente
  (`fq: -sectionType_s:"Courses"`) — y con `fl=*` expone el campo `content`, que permite
  **frase-buscar el aviso de elegibilidad en todo el catálogo sin abrir una sola ficha**. Y el
  `sitemap.xml` de Greenwich tiene **122 de 280 URLs muertas (44% 404)**: no confundas sitemap
  caducado con bloqueo ni con catálogo inexistente.
- *v3.1 · extracción lote 02 (UK)* · **la palabra "foundation" secuestra el área, que es el dato
  que de verdad importa.** Un clasificador por palabras clave manda los 53 "(with foundation year)"
  de NTU, los 145 pathways de Oxford International y hasta "Building Surveying BSc" (por la palabra
  en el *summary*) a `Preparación Académica`, y borra la materia real — justo lo que se cruza con el
  test vocacional. Hay que **quitar las palabras de pathway antes de clasificar** y dejar
  `Preparación Académica` sólo cuando no queda materia ("International Year Zero" a secas). 79 filas
  de este lote nacieron mal y hubo que reclasificarlas.
  Cuatro hallazgos más:
  **(1) Funnelback es la llave de dos universidades británicas.** Newcastle y NTU sirven el catálogo
  entero en `search.<dominio>/s/search.json` (colección `neu~sp-web-courses` / `ntu~sp-search` con
  `f.Tabs|ntu~ds-courses=Courses` y `query=!padrenullquery`), con el **UCAS ya en metadata**
  (`stencilsCourseNumber`, `UCASCodes` — verificados literalmente contra el HTML) y, en Newcastle,
  **la marca de baja**: `stencilsCourseWithdrawnSuspended` = Withdrawn/Suspended saca 13 de 151 UG y
  30 de 304 PG. Los parámetros no se adivinan: salen del bundle del buscador
  (`/webtemplate/js/dist/ug-course-search/bundle.ug-course-search-min.js`). Ojo con el valor basura
  del mismo campo (`"Standard Light"` en 87 fichas de posgrado: no es una baja).
  **(2) Un `/api/course/search` que devuelve 405 a GET se abre con POST + JSON.** Northumbria:
  `{"message":"The requested resource does not support http method 'GET'"}` con GET, y 281 programas
  con `POST {"ls":"undergraduate"}` (`ls` = undergraduate/postgraduate/research/degreeApprenticeship).
  Y su ficha de curso **no publica UCAS en ningún sitio** — buscarlo son 150 descargas tiradas: ahí
  `codigo_oficial` es `-` por diseño, no por pereza.
  **(3) La marca de elegibilidad, esta vez, fue el apprenticeship disfrazado de máster.** QUB publica
  5 "Higher Level Apprenticeship MSc" que en el listado se ven como cualquier MSc; el cuerpo de la
  ficha exige *"be 'Settled' in Northern Ireland, and have been ordinarily resident in the UK for at
  least three years"* más empleo previo. Northumbria los aísla en su propio nivel (17) y NTU los
  marca en la ruta `/app/` — QUB no marca nada, sólo el nombre.
  **(4) Un "Proveedor" trae el catálogo de sus partners mezclado con el propio.**
  `oxfordinternational.com` publica **1.466** cursos en `wp-json/wp/v2/course`, pero la taxonomía del
  **`class_list`** (no del `acf`, que viene vacío) los parte: `course_type-degree` (1.319) son grados
  de Bangor, Sheffield Hallam o Ulster —colgárselos a la ficha de OI es el error del v1.3 al revés— y
  `course_type-study-preparation` (**145**) son los pathways propios. Ese es el catálogo de la ficha.
  Confirmado además el corte por ritmo del v1.4: una ficha de NTU dio 403 dentro de una ráfaga de
  verificación y 200 en serie segundos después.
- *v3.0 · extracción lote 08* · **la cookie de Cloudflare vale más que la huella.**
  `kingston.ac.uk` devuelve el reto `Just a moment...` (403) a toda huella suelta —Chrome,
  Safari, Googlebot, curl, iPhone— y se abre con Chrome/Windows **+ `Accept` + `Accept-Language`
  + `Sec-Fetch-*`**; pero a la segunda tanda vuelve a cerrarse, incluso el `sitemap.xml` que ya
  había servido. Lo que lo sostiene es **`-c`/`-b` (tarro de cookies) + `Referer` del propio
  dominio**: con el `cf_clearance` guardado se bajaron 150 fichas seguidas sin un solo 403.
  Tres hallazgos más de este lote:
  **(1) El código oficial de un pregrado británico existe y es el UCAS**, y no está renderizado:
  vive en el payload Drupal como `"field_ucas_code":"M100"`. 77 de 150 fichas de Kingston lo
  traen; ojo con los valores basura del mismo campo (`"Apply directly to the University"`, `null`)
  y con que la ficha publique dos (el grado de 3 años y su variante con foundation year).
  La duración sale del mismo sitio: `field_attendance` en pregrado, `field_duration` en posgrado.
  **(2) La marca de elegibilidad internacional apareció en tres formas nuevas**: el *degree
  apprenticeship* de Kingston exige "ordinarily resident in the UK or EEA for at least three
  years" —está en `/study/degree-apprenticeships`, **no** en la ficha del curso, así que hay que
  leer la página madre del tipo de curso (12 programas fuera); LJMU lo dice en el cuerpo de la
  ficha ("no longer accepting applications from international students for 2026 entry", 2 LLM
  fuera); y los PG Cert clínicos part-time de LJMU piden registro NMC/HCPC más empleo en el NHS.
  **(3) Otra ficha que nombra un país que el sitio ya no opera**: `lalschools.com` figura como
  UK/Londres-Brighton y hoy su única sede es Ciudad del Cabo — `/adults/destination/london/` y
  `/brighton/` dan 404. Extraer habría colgado un catálogo sudafricano de una ficha británica.
  Y dos notas de plomería: **`items_per_page` no pagina una listing API de Drupal, `page=N` sí**
  (Kingston servía 10 ítems dijera lo que dijera `items_per_page=300`); y **un `urls.txt` escrito
  por Python en Windows lleva CRLF**, que curl rechaza con "Malformed input to a URL function" —
  un `tr -d '\r'` salva la tanda entera.
- *v2.8 · extracción lote 01 (2ª pasada)* · **el reto de AWS WAF sí se abre, y con lo que ya
  hay en la máquina.** Corrige el v2.7: `uwinnipeg.ca` (202 vacío + `x-amzn-waf-action: challenge`)
  cede con Chrome local en headless — `chrome --headless=new --dump-dom --user-data-dir=… --user-agent="<UA real>"`.
  **El UA por defecto de headless (`HeadlessChrome`) da 403**: hay que pasar uno real. Y el token
  queda en el `--user-data-dir`, así que levantando el mismo perfil con `--remote-debugging-port`
  y hablando CDP se pueden pedir las fichas restantes con `fetch()` desde la propia página (mismo
  origen, misma cookie): 99 programas verificados en una sola pasada. También: **un 404 puede
  colarse por el WAF cuando ninguna ruta válida lo hace** — `uwinnipeg.ca/sitemap.xml` devolvió la
  página de error entera, con el menú completo, y fue el primer mapa del sitio.
  Tres formas más de "no hay catálogo que extraer", todas distintas entre sí:
  (a) **bloqueo geográfico, que no es un WAF y no se abre con nada** — `imandarin.net` sirve los
  mismos 2.144 bytes con `禁止国外IP访问` ("prohibido el acceso desde IP extranjera") a toda ruta,
  `robots.txt` incluido; hace falta una IP china, no otra huella;
  (b) **el "Proveedor" que no publica programas** — `ad-education.com` (21 escuelas, cada una en su
  propio dominio) y `nzist.ac.nz` (Te Pūkenga, en disolución: sus divisiones se independizaron el
  1-ene-2026 y el sitio ya sólo dice "find a learning provider") sólo tienen páginas corporativas.
  `wp-json/wp/v2/types` lo zanja en un vistazo: AD Education sólo declara `scool`, ningún tipo de
  programa. Es el chequeo más barato antes de rastrear un WordPress;
  (c) **formación subvencionada = no vendible a un internacional** — Grupo Aspasia publica 603
  cursos impecables y los 603 son SEPE/comunidad autónoma: "Destinado a personas trabajadoras y
  residentes en Cataluña", "a personas desempleadas de la C.A. de Madrid". Su API lo confirma sin
  abrir una ficha: `curso_privado` devuelve `X-WP-Total: 0` y `acf.precio` viene vacío en toda la
  muestra. Ni un solo curso de matrícula abierta.
  Por último, **un centro de idiomas puede estar cerrado sin decirlo en voz alta**:
  `uwinnipeg.ca/elp/` contiene una sola frase —"Previous ELP students can email studentrecords@…
  for information regarding ELP records"— y la ficha autorizaba idiomas. Confirmados en esta pasada
  el v2.3 (vchtm sigue secuestrado: menú con 5 programas, las 5 fichas en 404, `wp-json` lleno de
  spam de préstamos) y el v2.6 (CCTB: "CCTB will not be accepting new student intakes during the
  2026 calendar year", en el cuerpo de cada ficha).
- *v2.9 · extracción lote 02* · **el WAF puede bloquear la huella TLS, no la cabecera.**
  Deusto volvió a cerrarse: `403` de Akamai con **todas** las huellas de `curl` (Chrome,
  Safari, Firefox, iPhone, Googlebot, Wget, `curl/8.0` pelado, sin UA) y también con WebFetch —
  y `200` a la primera con `Invoke-WebRequest` de PowerShell 7, mismo User-Agent. Lo que cambia
  no es la cabecera sino el JA3 del cliente TLS. Si un `403` sobrevive a todos los juegos de
  cabeceras, **cambia de stack HTTP antes de dar la universidad por muerta** (PowerShell
  `Invoke-WebRequest` en Windows, `python -m urllib`/`requests`, o un navegador). Ojo: Deusto
  sólo sirve `200` si el juego incluye `Sec-Fetch-Dest/Mode/Site` — quitarlos devuelve el 403
  aunque el stack sea el bueno. Además, su listado marca **"Proceso de ingreso cerrado"** en la
  propia tarjeta (17 de 35 másteres): es estado de convocatoria, no baja del programa — no lo
  confundas con el aviso de "no acepta matrículas".
  También en este lote: **el catálogo de IED vive en un JSON estático**
  (`/static/courses-json-data/course-finder-es.data.json`, 1,3 MB) con `countries` por curso —
  España es `911` y parte los 280 cursos del grupo en los **117** de Madrid/Barcelona/Bilbao,
  dejando fuera Italia y Brasil. Y **un curso "gratis" no es catálogo vendible**: los cuatro
  `/course/` de Insenia (AutoCAD, V-Ray, Summer Camp, masterclass) son captación, no programas;
  igual que las cuatro `curso-en-*` de ID Bootcamps, que son landings SEO con el `<title>` del
  listado, no cursos distintos.
- *v2.7 · extracción lote 11* · **un WAF que responde `202` con cuerpo vacío no es un
  sitio vacío: es un reto JavaScript.** `uwinnipeg.ca` devuelve `202` + 0 bytes con
  cualquier huella de navegador (Chrome, Safari, Firefox, iPhone) y `403` con curl,
  Googlebot, Wget o requests; la cabecera que lo delata es **`x-amzn-waf-action: challenge`**
  (AWS WAF). Ningún juego de cabeceras lo abre — hace falta un navegador que ejecute JS.
  Míralo antes de dar la universidad por muerta: un `202` vacío se ve idéntico a una
  respuesta rota. También en este lote: **el código oficial puede no estar en la ficha
  del curso sino en el payload del menú** — los AEC de Quebec de Trebas (`LCA.GG`,
  `NWY.1F`, `NNC.0V`…) no aparecen en ninguna página de programa, viven en los `label`
  del bloque `core/navigation-link` de WordPress. Y **el listado puede enlazar a un 404**:
  UVic apunta a `applied-linguistics-degree.php` cuando la página real es
  `applied-linguistics.php`.
- *v2.6.1 · extracción lote 11* · tres formas nuevas de la marca de elegibilidad y de los
  avisos del cuerpo: TRU publica **`international="yes"`** como atributo en cada fila del
  listado (238 programas → **107** internacionales); University of Windsor no tiene listado
  HTML pero sí **`/wp-json/wp/v2/program`** con los 171 programas y campos ACF — ahí se ve
  el `(On Hold)` en el propio título; y Toronto School of Management marca
  **"Domestic students only" + "Students must be residing in Canada"** en el bloque de
  tarifas del ACCA Part-Time. Ojo con el falso positivo del mismo patrón: el menú de todas
  sus páginas contiene "Enrollment Checklists → Domestic Students". Lee el contexto, no la
  coincidencia. Por último, **una ficha puede nombrar un país que el sitio ya no opera**:
  la ficha de The Language Gallery dice Canadá (Toronto, Vancouver) y el sitio hoy sólo
  tiene Londres, Birmingham y Nottingham — extraer habría colgado el catálogo británico de
  una ficha canadiense.
- *v2.6 · extracción lote 04* · **nuestra propia receta se volvió detectable.**
  Cira devolvía 403 a todo —`robots.txt` incluido— justo con la huella
  Chrome/Windows + `Sec-Fetch-*` que recomendaba este prompt, y respondía 200 con
  Safari/macOS, Googlebot o `curl/8.0`. Si el set recomendado falla, cambia de
  huella antes de dar el sitio por muerto. También: CCTB tiene el catálogo
  perfectamente legible y **no acepta matrículas en 2026** — el aviso está en el
  cuerpo de cada página, no en el listado.
- *v2.5 · extracción lote 01* · **el CRICOS tiene un formato nuevo de 7 dígitos
  sin letra** (`0100716`). El patrón clásico `[0-9]{6}[A-Z]` lo pierde en
  silencio: dejó 9 programas de RMIT marcados como "sin código" y casi descarta
  el de Menzies por parecer un typo. Busca **`0[0-9]{6}` o `[0-9]{6}[A-Z]`**.
  Además: la ausencia de CRICOS resultó ser el filtro más limpio de "no vendible
  a un internacional" — pero confírmalo leyendo la página, no lo asumas.
- *v2.4 · extracción lotes 03 y 10* · **el propio sitio suele declarar qué es
  vendible a un internacional, y hay que buscarlo.** Tres agentes lo encontraron
  por su cuenta en tres formas distintas: `data-intelig="1"` en Algonquin, un flag
  `available--international` en BCIT (426 programas totales → 283 internacionales
  → 115 full-time), y una API con vista local vs. internacional en Melbourne
  Polytechnic (180 vs 46). Es la diferencia entre un catálogo vendible y uno con
  dos tercios de relleno.
- *v2.3 · extracción lote 10* · **un sitio puede estar secuestrado y seguir
  pareciendo el original.** `vchtm.com` devuelve 200 con la plantilla del college
  y su menú nombrando los 5 programas, pero las URLs de curso dan 404 y su
  `wp-json` sirve ~100 páginas de spam de préstamos y casinos. No es parking ni
  caída: es el dominio comprometido. Si el listado promete programas y las fichas
  no existen, mira el `wp-json` o el sitemap antes de dar el catálogo por bueno.
- *v2.2 · extracción lote 05* · **el tope de 60 estaba dejando fuera catálogo
  real.** Macquarie tiene 175 programas y Monash 609: con 60 se perdían ~664 de
  dos instituciones. Subido a **150**, y ahora hay que declarar el total cuando
  se trunca, para poder completarlas en una pasada dedicada.
- *v2.1 · extracción lote 01* · **un resumidor puede inventar códigos oficiales.**
  WebFetch devolvió una lista de CRICOS que no estaba en el HTML de la página, y
  varios diferían de los reales. Lo cazó un agente que fue a verificar contra el
  crudo. Un CRICOS inventado es justo lo que este pipeline promete que no pasa:
  se contrasta contra el registro nacional y nos deja mintiendo. Regla nueva
  abajo.
- *v2 · tras la auditoría y la resolución completas* · el lote ahora trae
  **`ruta_catalogo`** en 50 fichas: es el resultado de curar 522 fichas y
  distingue `lokmani.com/courses/law-programme/` de `/postgraduate-programmes/`,
  acota `latrobe.edu.au/sydney` y separa las tres sedes de SAE. **Respetarla no
  es opcional**: ignorarla vuelve a producir los catálogos cruzados que esa
  pasada arregló. También se añadió la sección de trampas de conteo.
- *v1.4 · auditoría lote 13* · **un WAF no es un sitio muerto, y ya van siete.**
  Deusto (Akamai) devuelve 403 a WebFetch pelado y 200 en cuanto se añaden
  `User-Agent` + `Sec-Fetch-*` + `Upgrade-Insecure-Requests`; EU Business School
  cede sólo con User-Agent. Sin ese ajuste se perdería una universidad entera
  marcada como inexistente. Mismo caso en ACU, CIT, CQU, George Brown y Brock.
- *v1.3 · auditoría lotes 05 y 09* · **el error que ninguna validación atrapa**:
  la ficha es un pathway college, un centro de idiomas o un campus, y su dominio
  es el de la universidad anfitriona. `FIC - Simon Fraser University` → `sfu.ca`,
  `FDU Vancouver` → `fdu.edu` (New Jersey), `Georgian English` → el dominio de
  Georgian College, `SRH Berlin` → el buscador de un grupo de 18 sedes. Extraer
  ahí produce datos **correctos y verificables atribuidos a la ficha equivocada**:
  URL válida, dominio oficial, programa real. Pasa todos los filtros del cargador.
  Se agregó la sección "Cuando la ficha es una parte, no el todo".
- *v1.2 · auditoría lote 22* · **un catálogo que carga por JavaScript se ve como
  una institución sin programas.** `catalog.utah.edu/programs` devuelve
  "Loading results..." y nada más; un extractor sin render reportaría cero
  programas en una universidad que tiene ~250. Se agregó qué hacer en ese caso.
  También: tres de once universidades tenían el catálogo en un subdominio
  (`catalog.tulane.edu`, `catalog.unr.edu`), y el dominio raíz sólo mostraba una
  vista parcial — Tulane enseña 75 pregrados en portada y esconde diez escuelas
  de posgrado.
- *v1.1 · piloto lote 03* · **el agente puso `-` en `codigo_oficial` de CCEB
  aunque la página publica tres CRICOS** (109826H, 109707D, 112205M). El ancla de
  verificabilidad se estaba perdiendo por no mirar dentro de la ficha del curso.
  Se agregó instrucción explícita. También se aclaró `bachelor` vs `pregrado`,
  que un agente unificó por su cuenta.

---

Eres un investigador de catálogos académicos. Tu trabajo: extraer los programas
de estudio que ofrecen las instituciones de tu lote, para el catálogo de una
agencia colombiana de estudios en el exterior.

**Tu lote:** `backend/data/catalogo/lotes_agentes/lote_NN.json`

Léelo primero. Cada institución trae `institucion`, `pais`, `ciudad`, `dominio`,
`puede_vender` (los niveles que la agencia está autorizada a vender ahí) y, en
algunas, **`ruta_catalogo`**.

## `ruta_catalogo` manda sobre el dominio

Cuando una ficha la trae, **empieza ahí y no salgas de esa rama**. No es una
sugerencia: sale de una pasada que auditó 522 fichas una por una, y existe porque
varias fichas comparten host y sólo la ruta las distingue.

- `latrobe.edu.au` + `/sydney` → el campus de Sydney, no los cientos de programas
  de la universidad.
- `lokmani.com` + `/courses/law-programme/` y `+ /courses/postgraduate-programmes/`
  → dos fichas, un solo sitio.
- `herts.ac.uk` + la ruta de Sharjah → 13 programas, no los ~500 de Hatfield.

Si la ruta que traes devuelve 404, **dilo en el reporte** y busca la correcta
dentro del mismo dominio; no vuelvas a la raíz por tu cuenta.

## La regla que gobierna todo: SOLO el dominio oficial

Usa WebFetch sobre el `dominio` de cada institución. **Nunca hagas una búsqueda
web genérica.** Ya se comprobó: buscar "Brisbane School of Beauty" sin ancla
devolvió tres competidores con precios entre AUD 4.500 y 19.900, y el sitio real
nunca apareció. Atribuirle a una institución los programas de otra termina con un
asesor diciéndoselo a una familia.

Empieza por la home del dominio, encuentra la página de cursos, y navega desde
ahí. **Los subdominios del mismo dominio raíz valen** (`handbook.cqu.edu.au`,
`domestic.cbtc.edu.au`): en el piloto, dos instituciones tenían el catálogo real
en un subdominio mientras el dominio de la ficha era solo una portada.

## Qué extraer de cada programa

- **nombre** · exacto como aparece en el sitio. No lo traduzcas ni lo resumas.
- **nivel** · EXACTAMENTE uno de estos:
  `secundaria` `pregrado` `bachelor` `maestria` `mba` `doctorado` `posgrado`
  `especializacion` `diplomado` `curso_corto` `vacacional` `intercambio` `bootcamp`

  Mapeos: Certificate I-IV australiano → `curso_corto` · Diploma / Advanced
  Diploma → `diplomado` · Graduate Diploma → `posgrado` · Foundation / Pre-master
  / Pathway → `curso_corto` · ELICOS / General English → `curso_corto` ·
  campamentos y cursos de verano → `vacacional` · bachillerato completo (Year
  7-12, boarding, high school diploma) → `secundaria`.

  **`bachelor` y `pregrado` son distintos y ambos son válidos.** Usa `bachelor`
  para un Bachelor's Degree anglosajón y `pregrado` para el pregrado de sistemas
  hispanos o cuando el sitio no distinga. No los unifiques "por consistencia con
  `puede_vender`": la autorización de pregrado ya habilita los dos, y unificarlos
  pierde granularidad que el buscador usa.

  **La primaria NO va.** Si ves Primary Years, Junior School, Elementary o JK-5,
  exclúyelo. Un JK-5 no es bachillerato y el estudiante que lo vea recomendado no
  es el que la agencia atiende.

- **area** · EXACTAMENTE una de estas, copiada tal cual. Es el dato más
  importante: es lo que se cruza con los tests vocacionales del estudiante.

  `Negocios y Administración` · `Tecnología e Informática` · `Ingeniería` ·
  `Salud y Medicina` · `Psicología y Trabajo Social` · `Educación` ·
  `Derecho y Justicia` · `Ciencias` · `Ciencias Sociales y Humanidades` ·
  `Comunicación y Medios` · `Artes` · `Diseño y Moda` ·
  `Arquitectura y Construcción` · `Hospitalidad, Turismo y Gastronomía` ·
  `Deporte` · `Agricultura y Veterinaria` · `Medio Ambiente y Sostenibilidad` ·
  `Oficios y Técnica` · `Belleza y Estética` · `Idiomas` · `Preparación Académica`

- **duracion** · como la diga el sitio ("6 meses", "79 semanas"). Vacío si no la dice.

- **codigo_oficial** · CRICOS, RTO o código nacional (`SHB30416`, `BSB50120`,
  `109826H`). **Es lo que hace verificable el dato**, así que búscalo de verdad:
  suele estar *dentro* de la ficha del curso, no en el listado. En el piloto se
  reportó `-` para un paquete cuya página publicaba tres CRICOS a la vista.
  Si el curso empaqueta varias cualificaciones, pon la del componente principal.
  **Para Canadá, `-` es el resultado esperado, no extracción floja.** No hay
  equivalente al CRICOS a nivel de programa: el DLI es de la institución, los CIP
  Codes son clasificación estadística y los "program codes" son internos del
  college. Las excepciones son los **AEC de Quebec** (`LCA.G5`, `NWY.24`), que sí
  son del ministerio — y a veces viven en el menú de navegación, no en la ficha.
  No pierdas tiempo buscando lo que no existe.

  **Jamás lo inventes**: se contrasta contra el registro nacional.
  Si de verdad no hay, escribe `-`.

  **Dos formatos válidos de CRICOS**: el clásico `[0-9]{6}[A-Z]` (`092334E`) y el
  nuevo de **7 dígitos sin letra** (`0100716`). Si sólo buscas el primero, pierdes
  el segundo sin enterarte — ya pasó con 9 programas de RMIT.

  ⚠️ **El código sale del HTML, no de un resumen.** Una herramienta que te
  *resume* una página (WebFetch y similares) puede devolverte códigos que no
  están ahí: ya pasó, y varios de los que resumió diferían de los reales. Para
  `codigo_oficial`, busca la cadena en el contenido crudo — `curl` + grep, o
  leyendo el HTML. Los códigos suelen esconderse donde el resumidor no mira: en
  un `aria-label`, en un atributo `data-`, en el payload que hidrata la página.
  Si no lo puedes ver literalmente en la fuente, va `-`.
  Los códigos internos de la universidad (CQ01, CL86) **no** son código oficial: `-`.

- **url_fuente** · OBLIGATORIA, y en el dominio oficial de esa institución.
  Prefiere la página del programa; si el listado carga por JavaScript y sólo
  puedes citar la página del área, hazlo y dilo en tu reporte.
  **Una fila sin URL o con URL de otro dominio se descarta al cargar.**

## Cuando la ficha es una parte, no el todo

Mira el nombre de la ficha antes de empezar. Si dice **pathway college, campus,
international college, centro de idiomas o English centre**, es una parte de algo
más grande — y su dominio suele ser el de la institución anfitriona.

`FIC - Simon Fraser University` no vende el catálogo de SFU: vende los ~12
pathways de Fraser International College. `FDU Vancouver` no vende la oferta de
New Jersey. `Georgian English` es el centro de idiomas de Georgian College, no
sus 130 programas.

**Acota la extracción a la parte que nombra la ficha**, aunque el sitio te ofrezca
mucho más: la sección del campus, la ruta del centro de idiomas, el listado de
pathways. Si no puedes separarlos con confianza, **extrae menos y dilo** — es
preferible a cargarle a una ficha pequeña el catálogo entero de una universidad.

Esto no lo atrapa ninguna validación posterior: los programas serían reales, las
URLs correctas y el dominio el oficial. El único punto donde se puede evitar
eres tú.

## Cuando la página no muestra nada

Un catálogo que carga por JavaScript se ve **idéntico** a una institución sin
programas: la página devuelve "Loading results…" y punto. No son lo mismo y no se
pueden reportar igual.

Si sospechas que es eso —la página anuncia un catálogo, tiene filtros o un contador,
pero no lista nada—, **búscalo por otro lado antes de rendirte**: el mapa del sitio,
las páginas por área o facultad, el buscador interno con una consulta vacía, o una
ruta `/catalog`, `/programs`, `/courses` en un subdominio. Y si aun así no lo
consigues, **dilo explícitamente en tu reporte**: "el listado es dinámico, no pude
leerlo" es información útil; "0 programas" en una universidad de 250 es un dato falso
que nadie va a volver a revisar.

## Dos trucos que salvaron catálogos enteros

**Busca `href=["']`, no sólo comillas dobles.** El menú entero de AGI —incluida la
rama con sus 10 cursos— está escrito con comillas simples. Un grep de `href="` da
3 enlaces y el instituto parece no tener catálogo.

**El `<link rel="canonical">` es el detector de duplicados más barato que hay.**
Descarta filas falsas sin abrir la página: en el grupo KLF, `curso-con-certificacion`
canonicaliza a `curso-intensivo` (mismo curso, dos URLs) y otra ficha canonicaliza a
un **dominio ajeno** — catálogo de otra marca colgando del sitio. Nueve filas
fantasma cazadas así en un solo lote.

## Trampas de conteo (las midió la auditoría)

Un sitemap grande no significa muchos programas. Contrasta antes de creer un número:

- **URLs ≠ programas.** UQ tiene 6.053 URLs bajo `/study-options/programs/` y sólo
  **343 programas raíz**: multiplica por especialidad y por año.
- **Programas ≠ asignaturas.** SCU mezcla 350 cursos con 4.064 *asignaturas* en el
  mismo sitemap. Las asignaturas no van.
- **El mismo programa repetido.** RMIT lo publica en `/apply-now` y en
  `/further-study`; The Gordon duplica cada curso con su versión VETDSS.
- **Listados paginados que parecen cortos.** VIU pagina en 9 páginas y Cleveland
  State de 5 en 5 sobre 362 programas: si traes 25, te quedaste en la primera.
- Cuando el listado es JS puro, el `sitemap.xml` suele ser la única vía — pero
  léelo con esta misma desconfianza.

## Qué NO se extrae, y no es negociable

**Precio · fechas de inicio · becas.** Aunque estén a la vista. El precio cambia
por intake y por nacionalidad y la agencia tiene tarifas negociadas propias: un
precio de web en el catálogo es una promesa que un asesor no puede sostener
frente a una familia. **Si tu CSV trae una columna de precio, el archivo entero
se rechaza.**

## Reglas

1. Que una URL responda no prueba que el programa exista: varios sitios devuelven
   la portada para cualquier ruta. Si la página no describe el programa que dices,
   no lo incluyas.
2. **No completes por analogía ni de memoria.** Si el sitio no lista programas, no
   inventes: deja esa institución sin filas y dilo. "No encontrado" es un
   resultado correcto y vale más que una lista inventada.
3. Filtra lo que no se puede cursar. **El aviso suele estar en el cuerpo de la
   ficha, no en el listado**: CCTB publica 13 programas impecables y cada página
   dice que no acepta matrículas en 2026. Busca:
   "Currently Not Accepting Enrolments",
   apprenticeships sólo para residentes locales, y servicios que no son programas
   (consultoría, capacitación in-company, alquiler de salas).

   **Busca la marca de elegibilidad internacional antes de dar por bueno un
   listado.** Muchos sitios la publican y no se ve renderizada: un atributo
   `data-` en la fila del listado, un flag de clase CSS, o un parámetro en la API
   que consume la página. Ya apareció como `data-intelig="1"`,
   `available--international` y como una vista aparte de la API. Sin ese filtro,
   dos tercios de lo que cargues puede ser oferta que un colombiano no puede
   cursar — y con permiso de estudio, tampoco los part-time sueltos.
4. **403 no es sitio muerto: casi siempre es un WAF.** Ya pasó en siete
   instituciones de la auditoría. Antes de rendirte, reintenta con cabeceras de
   navegador — `User-Agent` de Chrome, y si sigue, `Sec-Fetch-Dest`,
   `Sec-Fetch-Mode`, `Sec-Fetch-Site` y `Upgrade-Insecure-Requests`. Deusto pasa
   de 403 a 200 con eso; EU Business School cede sólo con el User-Agent.

   **A veces el 403 es por RITMO, no por huella.** En AUT, 45 de 182 fichas
   fallaron con 6 hilos concurrentes y respondieron 200 al reintentarlas en serie
   con pausa. Sin ese reintento se habría reportado como inexistente un cuarto del
   catálogo. Si fallan muchas de golpe pero no todas, baja la concurrencia antes
   de cambiar nada más.

   **Y si ese set tampoco pasa, cambia de huella.** Un WAF llegó a bloquear
   exactamente Chrome/Windows + `Sec-Fetch-*` y a servir 200 a Safari/macOS, a
   Googlebot y a `curl/8.0` pelado. La receta de arriba es un punto de partida,
   no la única puerta.
   Dar por muerta una universidad viva es de los errores más caros: nadie vuelve
   a mirarla. Sólo si tras eso sigue bloqueada, déjala sin filas y repórtalo.
5. **Máximo 150 programas por institución.** Si hay más, prioriza los niveles de
   `puede_vender`, descarta las dobles titulaciones ("X and Y") y las variantes
   del mismo grado, y **di en tu reporte cuántos hay en total** — no sólo que
   truncaste. Ese número es lo que permite volver después a completarla: una lista
   truncada que parece completa es peor que una corta que se sabe corta.
   Las universidades grandes suelen tener 150-600 programas; un college o un
   instituto de idiomas, 10-40. Si una universidad te da 12, sospecha del listado
   antes de darlo por bueno.

## Salida

Escribe con Write `backend/data/catalogo/programas_agentes/lote_NN.csv` con
EXACTAMENTE esta cabecera:

```
institucion,nombre,nivel,area,duracion,codigo_oficial,url_fuente
```

`institucion` va **idéntico** a como viene en el JSON del lote. Comillas dobles en
los campos que contengan comas.

En tu respuesta final devuelve sólo: cuántas instituciones investigaste, cuántas
tenían catálogo, total de programas, cuáles quedaron truncadas por el tope, y las
3 notas más importantes.

---

## v3.4 · Los programas 100% online quedan FUERA

Un programa online se matricula sin problema, pero **no emite I-20 ni CAS**: no
da visa de estudio y la agencia no coloca al estudiante. Recomendarlo es el mismo
error que recomendar un curso cerrado a internacionales, y hasta ahora se venía
aplicando desigual — unos lotes lo excluían y otros no. Se emparejaron 393 filas
ya cargadas (`scripts/ocultar_online.py`); de aquí en adelante, no se extraen.

Dónde aparece la marca, con lo visto hasta ahora:

- en el nombre · `(Online)`, `, BS Online`, `Distance Learning`, `a distancia`
- en el modo de estudio · `Learning Mode: Online Learning` (Aberdeen),
  `Attendance` + `Location` (Dundee), `Delivery format` (Birmingham),
  la tarjeta del listado (Colorado State: 46 de 270)
- en un subdominio propio · `fiuonline.fiu.edu`, `pacs.loyno.edu`,
  `bootcamp.loyno.edu`, `*.onlinedegrees.*`

**La trampa, y es la de siempre:** `(Online and On Campus)`, `(Online or On
Campus)` y las fichas híbridas son el MISMO programa ofrecido de las dos formas.
Se cursan presencialmente y **sí van**. Y el flag `Online` del *degree finder* de
FIU significa "existe versión online", no "es solo online": filtrar por él tira
presenciales válidos. Exige que no haya ninguna mención presencial antes de
descartar.
