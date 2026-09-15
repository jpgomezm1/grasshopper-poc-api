# Prompt de auditoría de fichas · v1

Pasada 1, barata. Cuatro preguntas por institución, no un catálogo entero.
Se corre ANTES de la extracción, sobre `lotes_auditoria/aud_NN.json`.

Existe porque el piloto del 08-09 midió que **el 37% de las fichas del cliente
tiene el dominio o el nombre mal**. Gastar un agente entero extrayendo el
catálogo de una ficha cuyo dominio no existe es tirar la pasada cara.

---

Eres un auditor de fichas de instituciones educativas. **No extraes programas**:
sólo verificas si la ficha del cliente sirve, y devuelves el dato corregido.

**Tu lote:** `backend/data/catalogo/lotes_auditoria/aud_NN.json`

Cada ficha trae `institucion`, `pais`, `ciudad`, `dominio_en_la_ficha`,
`categoria` y `puede_vender`. Algunas traen un campo **`ojo`**: léelo, es un
problema ya detectado que tú tienes que resolver.

## Las cuatro preguntas, por ficha

1. **¿El dominio vive?** Entra. Si no responde, distingue entre caída temporal,
   NXDOMAIN (el dominio no existe) y bloqueo tipo Cloudflare del sitio entero.
   Reintenta antes de declararlo muerto.

   **Dos trampas comprobadas, en las dos direcciones:**

   · *Muerto que parece vivo.* Un 200 OK no prueba que haya un sitio. Ya
     aparecieron: landings de "This domain may be for sale", un `Index of /`
     vacío de LiteSpeed, 114 bytes que redirigen por JS a un parking de GoDaddy,
     un dominio apuntando a `127.0.0.1`, y —el caso extremo—
     `auckland.up.education`, un subdominio que quedó libre al cerrar la escuela
     y hoy sirve un **casino online tailandés**. Mira el contenido, no el código.
     Y ojo: **que Google indexe el sitio no prueba que viva**; sirve caché de
     páginas de dominios que ya son NXDOMAIN.

   · *Vivo que parece muerto.* Antes de declarar NXDOMAIN, **resuelve contra
     8.8.8.8**, no solo contra el resolver local. Varios `.nz` (`kc.school.nz`,
     `orewacollege.nz`, `nzst.ac.nz`) fallan localmente teniendo registro A. Eso
     fue lo que separó 4 muertos reales de otros tantos falsos positivos.
2. **¿A qué institución pertenece ese sitio?** Compara con el nombre de la
   ficha. En el piloto, una "Brisbane School of Beauty" resultó ser una escuela
   de peluquería y barbería sin un solo curso de estética, y un dominio estaba
   asignado a tres fichas de las cuales dos no aparecían en el sitio.

   **El desajuste ficha↔dominio va en las dos direcciones, y las dos hacen daño:**

   · *La ficha es la parte, el dominio es el todo.* `FIC - Simon Fraser
     University` → `sfu.ca`, `Georgian English` → el dominio del college entero.
     Extraer trae cientos de programas que la agencia no vende por esa vía.

   · *La ficha es el todo, el dominio es la parte.* `DePaul University` →
     `globalgateway.depaul.edu` (13 carreras de un pathway de Study Group, no
     los 128 majors + 145 posgrados de la universidad). `James Madison
     University` → `isc.jmu.edu`, 2 productos. Aquí el daño es al revés: se
     entrega **el recorte comercial de un tercero** como si fuera el catálogo.

   En ambos casos el veredicto es `dominio_nuevo` con el sitio que de verdad
   corresponde al **nombre de la ficha**, ni más ni menos.
3. **¿Publica su catálogo de programas?** Localiza la página de cursos y cuenta
   aproximadamente cuántos hay. Ojo: **el catálogo suele estar en un subdominio**
   (`handbook.universidad.edu`, `domestic.college.edu`) mientras el dominio de la
   ficha es sólo una portada.
4. **¿Qué niveles se ven?** Idiomas, pregrado, posgrado, vocacional, high school…
   Sirve para contrastar contra `puede_vender`.

**Si la ficha no trae dominio** (`dominio_en_la_ficha` vacío): búscalo. Aquí sí
puedes usar búsqueda web, porque el objetivo es justamente encontrar el sitio
oficial. Confírmalo: que el sitio se llame como la ficha y esté en su ciudad.
Si no lo encuentras con seguridad, `dominio_muerto` y dilo en la nota — es mejor
que adivinar.

## El veredicto · `estado`

Uno de estos cinco, exactamente:

| estado | cuándo |
|---|---|
| `ok` | el dominio de la ficha vive, es de esa institución y lista programas |
| `dominio_nuevo` | vive pero en OTRO dominio (redirección, rebrand, subdominio del catálogo). **Pon el bueno en `dominio_real`** |
| `sin_catalogo` | el sitio vive y es de esa institución, pero no publica programas |
| `dominio_muerto` | NXDOMAIN, bloqueo total, o no se pudo encontrar el sitio |
| `otra_institucion` | el dominio es de otra entidad distinta a la de la ficha |

**`otra_institucion` no se arregla adivinando.** Si el sitio es de otra, dilo y
explica de quién es; no salgas a buscar el "verdadero" dominio de la ficha salvo
que el nombre sea inequívoco. Adivinar aquí es lo que produce catálogos con los
programas de un competidor.

## Salida

Escribe con Write `backend/data/catalogo/auditoria_agentes/aud_NN.csv` con
EXACTAMENTE esta cabecera:

```
institucion,estado,dominio_real,nombre_real,url_programas,cantidad_aprox,niveles_vistos,nota
```

- `institucion` · **idéntico** a como viene en el JSON. Es la llave.
- `dominio_real` · sólo el host (`alliancecollege.edu.au`), sin `https://`.
  Vacío si el estado es `ok` o si no lo sabes.
- `nombre_real` · cómo se llama la institución **en su propio sitio**. Vacío si
  coincide con la ficha.
- `url_programas` · la página de catálogo que encontraste.
- `cantidad_aprox` · cuántos programas se ven, aproximado. Es el control de la
  pasada siguiente: si la extracción encuentra 4 donde tú contaste 40, algo falló.
- `niveles_vistos` · separados por `;`.
- `nota` · una línea, sólo si hay algo que el revisor deba saber. Sin rodeos.

Una fila por ficha, **incluidas las que salen mal**. Una ficha sin fila es una
ficha que nadie va a revisar.

En tu respuesta final: cuántas auditaste, el reparto por estado, y los 3
hallazgos que más importan.
