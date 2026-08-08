# Enriquecimiento del catálogo · `A8` / §4

**Qué resuelve.** El catálogo de producción son **2.511 filas y las 2.511 son instituciones,
no programas** (`name == institution` en el 100%). Costo, duración, área de estudio, requisito
de idioma y beca están en **0%**. Sin eso, la IA no puede recomendar un programa concreto —
que es literalmente lo que pidió la clienta:

> *"la IA debería ir a la institución a buscar qué foundations, pregrados y maestrías tiene
> que le puedan servir a esa persona según su perfil"*

`programs_offered` (23% de cobertura) **no es una lista de programas**: es el *nivel que la
agencia está autorizada a vender* ahí (`"Idiomas"`, `"Pregrado & Postgrado"`, `"Todos los
programas"`). Sirve para no proponer una maestría donde sólo se venden cursos de idioma, y ya
se usa para eso. No dice qué programas existen.

---

## La regla que lo gobierna todo

Este catálogo le dice a un estudiante —muchos de ellos menores— **qué estudiar, dónde y cuánto
cuesta**, y la agencia después tiene que poder entregarlo. Por eso:

| Dato | Origen |
|---|---|
| Nombre del programa · nivel · área · duración | ✅ Investigable en el sitio oficial |
| **Precio** | ❌ **Nunca.** Cambia por intake y nacionalidad, y la agencia tiene tarifas negociadas |
| **Qué puede vender la agencia** | ❌ Es un contrato. Sólo la clienta |
| Becas · fechas de inicio | ❌ Cambian constantemente |

Todo lo investigado se guarda con `origen = 'investigado'` y su fuente, **separado** de lo que
la clienta confirmó, y se muestra marcado como referencia — mismo criterio con el que este
sprint quitó los percentiles inventados y el "encaja en tu presupuesto".

---

## Por qué se ancla al dominio oficial

Prueba real (2026-08-07): se buscó `"Brisbane School of Beauty"` sin ancla. Los resultados
fueron **tres competidores** —Demi International, TAFE Queensland, The French Beauty Academy—
con precios entre AUD 4.500 y 19.900. **El sitio real de la institución nunca apareció.**

Si eso se ingiere automático, se le atribuye a una institución el precio de otra y un asesor
se lo dice a una familia.

Por eso: **sólo el dominio oficial de la ficha**, y el universo tratable no son 2.511 sino las
**630 con `website`** (446 de ellas con oferta conocida). Para las otras 1.881 hay que pedirle
los sitios a la clienta — un archivo mucho más barato que el catálogo completo.

## Y por qué la URL fuente no basta como prueba

Se inventó una URL de control que no existe (`burlingtonschool.co.uk/courses-for-adults,
curso-inventado-de-control.html`) y **el sitio la respondió con contenido**: sirve la portada
para cualquier ruta. Varios sitios hacen lo mismo.

⇒ **La URL no prueba que el programa exista.** El ancla verificable es el **código oficial**
del programa: `SHB30416`, CRICOS `092334E`, `BSB50120`, `TAE40122`. Esos se contrastan contra
el registro nacional — un código inventado no existe en CRICOS. Por eso la extracción lo exige.

*(Nota: el agente de Burlington detectó ese comportamiento por su cuenta y excluyó un programa
por eso. La disciplina funciona, pero no se puede depender de que siempre pase.)*

---

## Resultado del piloto (3 instituciones · 2026-08-07)

**42 programas** con nivel, área, duración y fuente.

| Institución | Programas | Nota |
|---|---|---|
| Phoenix Academy | 27 | Idiomas + certificados/diplomas de negocios, liderazgo, gestión de proyectos |
| Burlington School | 10 | Sólo idiomas y preparación de exámenes |
| Brisbane (peluquería) | 5 | Encontró 3 páginas **que no están en el menú del sitio** |

### Lo que no se esperaba: errores en el archivo de la clienta

- **Phoenix Academy** · el dominio de su Excel (`phoenix.wa.edu.au`) redirige a
  `phoenix.edu.au`.
- **"Brisbane School of Beauty"** · la institución real se llama **"Brisbane and Gold Coast
  School of Hairdressing, Barbering and Beauty"** y **no tiene un solo programa de estética**.
  Todo es peluquería, barbería y gestión de salón.

**Dos de tres instituciones con el dato mal.** Eso solo justifica la pasada de auditoría,
aparte de los programas.

### Lo que además apareció, y llena columnas hoy vacías

Requisitos de inglés publicados por programa (IELTS 4.5 / 5.0 / 5.5 / 6.0 / 7.5). La columna
`language_requirement` está en **0%** en producción y el producto ya mide el CEFR del
estudiante: es cruce directo.

---

## Estructura

```
data/catalogo/
├── instituciones_con_sitio.json   · las 630 · insumo de todo
├── lotes/lote_NN.json             · 42 lotes de 15 · unidad de trabajo de cada agente
└── auditoria/                     · salida de la pasada 1
```

## Las dos pasadas

1. **Auditoría** (barata) · dominio vigente, nombre real, si el sitio existe, si lista
   programas, y si es una institución o una agencia. Entregable útil por sí solo para la
   clienta.
2. **Extracción** (cara) · por lotes, sólo sobre las que pasaron la auditoría, **exigiendo
   código oficial por programa** y sin precio jamás.

## Antes de escalar: preguntarle a la clienta

**¿La agencia ya tiene contrato con [Studyportals](https://studyportals.com) o
[IDP Hotcourses](https://www.hotcoursesabroad.com/study/source.html)?** Es común en agencias
de este tamaño. Un feed suyo trae acreditación verificada y se actualiza mensualmente — le
gana a cualquier cosa que investiguemos y ahorra el trabajo entero.
