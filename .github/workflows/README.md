# GitHub Actions · Backend Grasshopper

## verify-fix-claim.yml

### Qué hace

Cuando se abre o actualiza un Pull Request, este workflow busca en el titulo del PR, el body y los mensajes de commits cualquier ID de tarea o audit del proyecto:

- `QA-AUD-NNN` (items del audit de seguridad/QA)
- `GH-SN-TYPE-NN` (tareas de sprint, ej. `GH-S3-BE-02`)
- `GH-SN.N-TYPE-NN` (tareas de sub-sprint, ej. `GH-S11.5-BE-01`)
- `FN-TYPE-NN` (tareas de remediation, ej. `F2-BE-03`)

Por cada ID encontrado, infiere la zona de codigo que deberia haber cambiado:

| Tipo (`TYPE`) | Zona esperada (este repo: backend) |
|---|---|
| `BE` | `app/` |
| `DB` | `app/` |
| `INFRA` | `.github/` |
| `QA` | `tests/` |
| `DOC` | `docs/` |
| `QA-AUD-*` | `app/` |
| `FN-BE-*` | `app/` |
| `FN-INFRA-*` | `.github/` |

Si un ID esta declarado pero no hay ningun archivo de esa zona en el `git diff` del PR, el check falla con mensaje explicito.

### Cuándo falla

El workflow falla cuando:
1. El PR/commit menciona un ID (ej. "resuelve QA-AUD-042")
2. Pero `git diff base..HEAD` no muestra cambios en la zona correspondiente

Ejemplo de mensaje de falla:
```
FALLA [QA-AUD-042]: se declara que este ID fue resuelto, pero no hay
  cambios en la zona esperada: 'app/'
  Archivos modificados en este PR que empiezan con 'app/':
  (ninguno)
```

### Cómo bypassearlo (legítimamente)

Hay casos válidos donde el fix no toca código fuente:

- Corrección exclusiva de docs o comentarios
- Tarea de tipo TRAIN o DOC sin correlato en `app/`
- Hotfix de emergencia que se documenta post-merge
- Falso positivo donde el ID aparece mencionado como referencia, no como claim de cierre

En esos casos: agregar la etiqueta **`skip-fix-verification`** al PR. El check pasará automáticamente y quedará el label como registro de la excepción.

Siempre dejar en el body del PR la justificacion de por que se salta la verificacion.

### Limitaciones conocidas (v1)

1. **Inferencia por tipo, no por archivo especifico**: el check valida que la zona correcta tenga cambios, pero no verifica que el archivo exacto mencionado en `TASKS.md` o `QA_AUDIT.md` fue tocado. Mejora planeada para v2.

2. **IDs de tipo FE y DESIGN fallan siempre en el backend repo**: son ignorados (zona no mapeada). Correcto porque esos cambios viven en el repo frontend.

3. **No lee `TASKS.md` ni `QA_AUDIT.md` directamente**: los docs de planning estan en el repo `irrelevant-board`, no en este repo. Para v2 se puede agregar un `actions/checkout` secundario del repo board y cruzar el archivo especifico declarado.

### Mejoras v2 sugeridas

- Checkout secundario del repo `irrelevant-board` para leer `TASKS.md` y `QA_AUDIT.md` y validar el archivo exacto en lugar de la zona
- Comentario automático en el PR listando los IDs encontrados y su estado (OK / FALLA)
- Soporte para `FE`/`DESIGN` IDs en el backend repo (ignorarlos explícitamente con log, no fallar)
- Matrix de repos: un solo workflow en el repo board que valida ambos repos
