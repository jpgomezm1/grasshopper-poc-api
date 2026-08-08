# Prompt de auditoría · v2

Versión endurecida con lo aprendido en los primeros 4 lotes (60 instituciones,
sólo 7 sin observaciones). Cada agente escribe su propio archivo de salida.

---

AUDITORÍA de catálogo de instituciones educativas de una agencia de estudios en el exterior.
NO es extracción de programas — es verificar que la ficha que tenemos sea correcta.

**Lee el lote:** `backend/data/catalogo/lotes/lote_NN.json` (16 instituciones)

Cada ficha trae: `institucion` (el nombre que tenemos), `pais`, `ciudad`, `sitio` (el dominio
que tenemos), `category`, `partner_group`, `puede_vender`.

## Para CADA institución, visitando SÓLO su dominio oficial

1. ¿El dominio responde? Si redirige, ¿a cuál?
2. ¿Cómo se llama la institución **según su propio sitio**? (nombre completo, textual)
3. ¿El nombre que tenemos corresponde a esa institución?
4. ¿Tiene página que liste sus programas? URL.
5. ¿Cuántos programas, aproximadamente, y de qué niveles? (**sólo el conteo**, no la lista)
6. ¿Es una institución educativa, o una **agencia / red / grupo paraguas**?

## Lo que ya nos mordió · revisar explícitamente

- **403 de Cloudflare ≠ sitio muerto.** Dos sitios devolvieron 403 a fetchers sin
  User-Agent de navegador y con UA de Chrome respondieron 200. Antes de declarar un sitio
  caído, reintenta con UA de navegador.
- **Dominio muerto: confírmalo contra DNS público** (8.8.8.8) antes de reportarlo. Ya
  encontramos NXDOMAIN reales, servidores que rechazan conexión, y uno que apunta a
  127.0.0.1.
- **Instituciones fantasma.** Encontramos 4 fichas cuyo dominio pertenece a **otra** escuela
  que no ofrece nada del área prometida ("Australian College of Dance" → dominio de un grupo
  sin ni un curso de danza). Si el nombre de la ficha no aparece en el sitio, **dilo**.
- **Sitios paraguas y dominios compartidos.** Un dominio albergaba 5 escuelas internas; otro
  aparecía en 3 fichas distintas. Si el dominio es de un grupo y no de esta escuela, márcalo.
- **Duplicados.** Dos fichas del mismo lote con el mismo dominio y la misma institución.
- **Catálogos no enumerables.** Algunos sitios son un buscador dinámico o un configurador, no
  una lista. Márcalo: la extracción posterior necesita otro tratamiento.
- **Cursos cerrados.** Un sitio marcaba muchos como "Currently Not Accepting Enrolments".
- **`puede_vender` inconsistente.** Fichas marcadas "Vocacionales" que otorgan bachelor, o
  "Idiomas" que sólo tienen grados. Si lo que ves contradice la ficha, dilo.

## Reglas

- **Sólo el dominio oficial de cada ficha.** Nada de búsquedas genéricas: hay instituciones
  con nombres parecidos y se confunden (ya pasó).
- **NO extraigas la lista de programas.** Esta pasada es sólo auditoría.
- **NO reportes precios.**
- Si no puedes determinar algo, escribe `?`. **No adivines.**
- "No accesible" es un resultado válido y útil.

## Salida

**Escribe el resultado con la herramienta Write** en:
`backend/data/catalogo/auditoria/lote_NN.txt`

Formato: una línea por institución, campos separados por ` | `, en este orden exacto:

```
institucion_en_ficha | dominio_responde(si/no/redirige/bloquea) | dominio_real | nombre_real_en_el_sitio | nombre_coincide(si/no/parcial) | url_de_programas | cantidad_aprox | niveles | tipo(institucion/agencia/red) | alerta
```

En `alerta`: una frase corta con lo que quien revise deba saber, o `-` si no hay nada.
Empieza el archivo con una línea de comentario `# Lote NN · fecha`.

Termina el archivo con:
```
# RESUMEN: ok=N muertos=N redirigen=N nombre_distinto=N no_institucion=N duplicados=N fantasmas=N
```

Y en tu respuesta final devuelve **sólo** ese RESUMEN más las 3 alertas más graves. El detalle
ya quedó en el archivo.
