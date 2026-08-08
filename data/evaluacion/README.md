# Casos de evaluación · cómo saber si el buscador recomienda bien

Hoy el sistema puede comprobarse solo en lo que es **error objetivo**: ofrecerle
una maestría a alguien que está en el colegio, devolver un programa de otro país
del que pidió, mostrar una institución dada de baja. Eso corre en cada cambio con
`python scripts/evaluar_recomendaciones.py` y no necesita a nadie.

Lo que **no** puede comprobarse solo es lo importante: *¿esta recomendación es
buena para esta persona?* Eso no lo decide una regla, lo decide alguien que ha
sentado a cien familias a decidir dónde estudiar.

Sin este archivo, cada cambio al buscador es una corazonada: no se puede
responder si mejoró o empeoró.

---

## Qué hay que llenar

Copia `casos.ejemplo.json` a `casos.json` y agrega casos reales.

```json
{
  "casos": [
    {
      "nombre": "Mariana · 11° · quiere trabajar con animales",
      "etapa_de_vida": "high_school",
      "paises": ["Australia"],
      "riasec": ["R", "I"],
      "esperados": [
        "Bachelor of Veterinary Science",
        "Certificate III in Wildlife and Exhibited Animal Care"
      ]
    }
  ]
}
```

| Campo | Qué poner |
|---|---|
| `nombre` | Para leer el informe · un perfil reconocible |
| `etapa_de_vida` | `high_school_early` · `high_school` · `university` · `recent_grad` · `working` |
| `paises` | Los que pidió, o vacío |
| `riasec` | Su código Holland · `R` `I` `A` `S` `E` `C` |
| `esperados` | **Los programas que un asesor esperaría ver.** Nombre exacto |

## Dos reglas para que esto sirva

**No copies lo que el sistema devuelve hoy.** Sería medirse contra uno mismo:
todo daría 100% y no detectaría ninguna regresión. Los `esperados` se escriben
pensando en el estudiante, no mirando la pantalla.

**Incluye casos difíciles.** Un perfil que mezcla dos mundos ("me gustan los
animales pero también dibujar"), alguien con un presupuesto que aprieta, alguien
cuyo test dice una cosa y sus palabras dicen otra. Los casos fáciles ya pasan;
los que enseñan algo son los otros.

## Cuántos

Con **20 casos bien escogidos** ya se detecta una regresión seria. Con 50 se
puede comparar dos versiones del buscador con alguna confianza. Más de 100 no
aporta mucho hasta que haya señal real de asesores.

## De dónde sacarlos

Lo más barato: **estudiantes que la agencia ya colocó**. Se sabe qué perfil
tenían y dónde terminaron, así que el `esperado` no hay que imaginarlo — es lo
que efectivamente les sirvió.
