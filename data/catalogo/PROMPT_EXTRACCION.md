# Prompt de extracción de programas · v1

Segunda pasada. Sólo corre sobre instituciones que **pasaron la auditoría** — las
189 inservibles no entran, y los dominios vienen ya **verificados y corregidos**
por esa pasada, no de la ficha original.

---

Extrae los programas de estudio de cada institución de tu lote, para el catálogo
de una agencia colombiana de estudios en el exterior.

**Lee tu lote:** `backend/data/catalogo/lotes_extraccion/ext_NN.json`

Cada institución trae:

| Campo | Qué es |
|---|---|
| `nombre_real` | El nombre **verificado en su propio sitio** |
| `dominio` | El dominio **verificado**. Úsalo, no busques otro |
| `url_programas` | La página de catálogo **ya localizada** por la auditoría |
| `cantidad_aprox` | Cuántos programas contó la auditoría · **es tu control** |
| `niveles_vistos` | Qué niveles vio la auditoría |
| `puede_vender` | Lo que la agencia está autorizada a vender ahí |
| `alerta` | Lo que la auditoría encontró raro. **Léelo antes de empezar** |

## Lo que hay que sacar de cada programa

```
institucion | nombre | nivel | area | duracion | codigo_oficial | url_fuente
```

- **nombre** · exacto como aparece en el sitio. No lo traduzcas ni lo resumas.
- **nivel** · **uno de estos**, y sólo estos (es el vocabulario que el producto
  entiende; cualquier otro valor se descarta al cargar):
  `secundaria` · `pregrado` · `bachelor` · `maestria` · `mba` · `doctorado` ·
  `posgrado` · `especializacion` · `diplomado` · `curso_corto` · `vacacional` ·
  `intercambio` · `bootcamp`

  ⚠️ **`secundaria` se agregó el 08-08** tras el primer lote. Faltaba, y por eso
  tres instituciones quedaron mal representadas: un colegio de Pre-Prep a Year 12
  aportó 2 filas, y una ficha cuyo `puede_vender` dice literalmente "High School"
  perdió su producto principal. Úsalo para programas de bachillerato completos
  (Year 7-12, boarding school, high school diploma, año Post-Graduate). Un
  semestre o año de intercambio en un colegio sigue siendo `intercambio`.
  Mapeos frecuentes: *Certificate I-IV* australiano → `curso_corto`;
  *Diploma / Advanced Diploma* → `diplomado`; *Graduate Diploma* → `posgrado`;
  *Foundation / Pre-master / Pathway* → `curso_corto`; *ELICOS / General
  English* → `curso_corto`; campamentos y cursos de verano → `vacacional`.
- **area** · el campo de estudio, en español (`Negocios`, `Ingeniería`,
  `Salud`, `Idiomas`, `Artes`, `Hospitalidad`, `Tecnología`…). Es **el dato más
  importante**: es lo que se cruza con los tests vocacionales del estudiante.
- **duracion** · como la diga el sitio (`6 meses`, `79 semanas`). Si no la dice,
  `no indicada`.
- **codigo_oficial** · CRICOS, RTO, código nacional del programa (`SHB30416`,
  `BSB50120`, `TAE40122`). **Es lo que hace verificable el dato**: un código
  inventado no existe en el registro nacional. Si no hay, `-`.
- **url_fuente** · la URL exacta donde lo viste.

## Lo que NO se extrae, y no es negociable

**Precio · fechas de inicio · becas.** Aunque estén a la vista.

El precio cambia por intake y por nacionalidad, y la agencia tiene tarifas
negociadas propias: un precio de web puesto en el catálogo es una promesa que
un asesor no puede sostener frente a una familia. Las fechas y las becas cambian
constantemente. Eso lo pone la clienta, no nosotros.

Si ves precios, **no los reportes**; puedes anotar en NOTAS que el sitio los
publica, sin transcribirlos.

## Reglas

1. **Sólo el dominio de tu lote.** Nada de búsquedas genéricas: ya comprobamos
   que devuelven competidores con nombres parecidos.
2. **La URL fuente no prueba nada por sí sola.** Varios sitios devuelven 200 con
   la portada para rutas inventadas. Si una página no describe el programa que
   dices, no lo incluyas.
3. **No inventes ni completes por analogía.** Si el sitio no lista programas,
   devuelve lista vacía y dilo. "No encontrado" es un resultado correcto.
4. **Filtra lo que no se puede cursar:** cursos marcados *"Currently Not
   Accepting Enrolments"*, programas sólo para residentes locales
   (*apprenticeships* australianos), y servicios que no son programas
   (consultoría, capacitación in-company, alquiler de salas).
5. **Contrasta con `cantidad_aprox`.** Si la auditoría contó ~40 y tú encuentras
   4, algo falló: dilo en NOTAS en vez de entregar una lista corta como si fuera
   completa.
6. **403 no es sitio muerto.** Reintenta con User-Agent de navegador. Y ojo:
   `curl` en esta máquina devuelve `000` por un MITM de TLS local — no significa
   nada.

## Salida

**Escribe con Write** en `backend/data/catalogo/programas/ext_NN.txt`:

```
# Lote NN · fecha
institucion | nombre | nivel | area | duracion | codigo_oficial | url_fuente
...
# RESUMEN: instituciones=N con_programas=N total_programas=N sin_catalogo=N
# NOTAS: (una línea por institución con algo que el revisor deba saber)
```

En tu respuesta final devuelve **sólo** el RESUMEN y las 3 notas más
importantes. El detalle ya quedó en el archivo.
