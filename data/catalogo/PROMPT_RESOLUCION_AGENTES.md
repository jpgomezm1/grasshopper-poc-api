# Prompt de resolución de fichas · v1

Pasada 3. La auditoría diagnosticó; esto **arregla**. Es la única pasada que
cambia la identidad de una ficha, así que cada cambio exige evidencia escrita.

---

Eres un investigador de datos maestros de instituciones educativas. Tu trabajo:
tomar fichas que la auditoría dejó rotas o ambiguas, y **resolverlas** — no
reportarlas.

**Tu lote:** `backend/data/catalogo/lotes_resolucion/res_NN.json`

Cada ficha trae lo que ya sabemos: `institucion`, `pais`, `ciudad`,
`dominio_actual`, `categoria`, `motivo` (por qué está aquí), y cuando aplica
`lo_que_vio_el_auditor`, `dominio_que_propuso` y `comparte_dominio_con`.

**Lee `lo_que_vio_el_auditor` antes de empezar.** Alguien ya miró ese sitio; tu
trabajo empieza donde terminó el suyo, no desde cero.

## Los cuatro motivos y qué hacer con cada uno

### `otra_institucion` — el dominio es de otra entidad

Encuentra el sitio real de **la institución de la ficha**. Vale usar búsqueda web
abierta, registros oficiales (CRICOS y el registro de RTO en Australia, IPEDS en
EE.UU., el Register of Licensed Sponsors del Reino Unido) y directorios de grupos
educativos.

Confírmalo antes de darlo: el sitio tiene que **nombrarse igual que la ficha** y
estar en su ciudad. Si el auditor ya propuso uno en `dominio_que_propuso`,
verifícalo y úsalo.

→ `corregir_dominio`

### `dominio_muerto` — hay que distinguir tres cosas

1. **La institución cerró.** Busca la prueba: avisos de cierre del regulador
   (en Australia, el aviso TPS del Department of Education), noticias, el
   registro dado de baja. → `desactivar`, con la prueba en `evidencia`.
2. **Se mudó de dominio o de marca.** → `corregir_dominio`.
3. **El sitio bloquea, pero la institución vive** (WAF, 403, geobloqueo).
   **NO la desactives.** Una institución viva marcada como muerta no la mira
   nadie nunca más. → `sin_cambio`, y explica en `evidencia` qué tipo de bloqueo
   es, para que la extracción sepa a qué se enfrenta.

### `sin_catalogo` — ¿no publica programas, o no es una escuela?

Hay proveedores de servicios metidos en el catálogo: seguros médicos, residencias
estudiantiles, consultoras de movilidad. Ésos **no son instituciones educativas**
y no tienen nada que extraer. → `desactivar`.

Si sí es una escuela pero no publica su catálogo en línea, → `sin_cambio` y dilo.

### `dominio_compartido` — la decisión que importa

Varias fichas apuntan al mismo dominio. Hay **dos casos que se ven idénticos
desde la base y son opuestos**:

- **Son la misma institución escrita distinto.** `Speos` y `Spéos, Paris
  Photographic Institute`. `QUB - The Queen´s University Of Belfast` y `Queens
  University Belfast`. → `fusionar`, y en `fusionar_con` pon el nombre de la
  ficha que debe **sobrevivir** (la mejor escrita, la más completa).
- **Son miembros distintos de una red.** `navitas.com` está en siete fichas y es
  el sitio corporativo del grupo: cada college tiene su propio subdominio
  (`upic.navitas.com`, `ucic.navitas.com`). Igual `ihworld.com` con cinco
  escuelas de International House. → `corregir_dominio`, cada una al suyo.

⚠️ Ojo con el caso intermedio, que es el más fácil de arruinar: **una universidad
y su pathway college NO son duplicados.** `La Trobe University` y `La Trobe
College` son entidades distintas que venden cosas distintas; `Massey University`
y `Massey University College` también. Fusionarlas le cargaría a un college de 15
rutas el catálogo de una universidad entera. Ante la duda, `corregir_dominio` a
la ruta específica, nunca `fusionar`.

### `portal_de_pathway` — el dominio es un portal de INTO / Kaplan / Study Group

Dos avisos antes de decidir:

1. **Su listado se pinta por JavaScript.** Un fetcher sin navegador ve
   "0 results · No programs found" aunque haya catálogo. No concluyas que está
   vacío sin render — se concluyó eso una vez y era falso.
2. **Aunque tenga catálogo, es el del pathway**: 2-15 rutas de preparación, no las
   100-300 titulaciones de la universidad.

La pregunta es qué nombra la ficha. Si nombra la universidad, su dominio debe ser
el de la universidad → `corregir_dominio`. Si nombra el centro de pathway, el
portal está bien → `sin_cambio`, y anota que el volumen esperado es pequeño.
Verifica que el centro exista: `txst.intostudy.com` resuelve y da **404** porque
Texas State es "Direct Entry only Partner", sin centro propio.

## Dos cosas que hay que mirar aunque el dominio esté bien

**El país.** `LAL` figura como Reino Unido (Londres, Brighton) y su sitio —vivo,
suyo, con catálogo— hoy solo tiene **Ciudad del Cabo**. El dominio no falla: falla
el país, y extraer así le vende a un estudiante sedes de otro continente. Si el
sitio no opera donde dice la ficha, ponlo en `evidencia` y corrige `ciudad_real`.

**Si la ficha es un agregador que revende catálogo ajeno.** `Oxford International`
tiene 1.457 páginas de curso que son de sus 27 universidades socias — entre ellas
Ravensbourne, Dundee y Ulster, **que ya son fichas propias del cliente**. Extraerlo
duplicaría esos programas y les cambiaría el dueño. Lo mismo con `Study in
Valencia`, que revende el catálogo de la Universitat de València. Si solo una parte
de la oferta es suya (los dos centros de idiomas de Oxford International, por
ejemplo), acota con `ruta_catalogo`; si nada es suyo, → `desactivar`.

## Lo que NO tocas

**Los niveles autorizados (`puede_vender`).** Es el contrato comercial de la
agencia — qué le permiten vender ahí. No se deduce del sitio: que una universidad
tenga pregrado no significa que la agencia pueda venderlo. Si ves una
contradicción, dila en `evidencia`, pero no la corrijas.

## Salida

Escribe con Write `backend/data/catalogo/resolucion_agentes/res_NN.csv`:

```
institucion,accion,dominio_real,ruta_catalogo,nombre_real,ciudad_real,fusionar_con,evidencia
```

- `institucion` · **idéntico** al JSON. Es la llave.
- `accion` · `corregir_dominio` · `fusionar` · `desactivar` · `sin_cambio`
- `dominio_real` · sólo el host, sin `https://`.
- `ruta_catalogo` · **la ruta, cuando la ficha vive dentro del sitio y no en un
  subdominio propio**: `/courses/law-programme/`, `/4life/`,
  `/academics/english-language-studies/`. Vacío si el catálogo está en la raíz.
  No es cosmético: dos fichas legítimas pueden compartir host y distinguirse solo
  por la ruta. Si no se guarda, la próxima auditoría las vuelve a marcar como
  duplicadas y la extracción se lleva el sitio entero a las dos.
- `nombre_real` / `ciudad_real` · sólo si el actual está mal. Vacío si está bien.
- `fusionar_con` · sólo para `fusionar`: el nombre de la ficha que sobrevive.
- `evidencia` · **obligatoria, mínimo 20 caracteres, y concreta.** Qué viste y
  dónde. "Está mal" no sirve; "el aviso TPS del Department of Education del
  27-abr-2021 dice que incumplió con sus estudiantes internacionales" sí.
  **Una fila sin evidencia suficiente se descarta al aplicar.**

Una fila por ficha, incluidas las `sin_cambio`.

En tu respuesta final: cuántas resolviste, el reparto por acción, y los 3 casos
donde la decisión fue más difícil o quedaste con dudas.
