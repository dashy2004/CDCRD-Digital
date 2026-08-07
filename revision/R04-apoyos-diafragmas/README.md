# R04 — Apoyos y diafragmas

## Herramientas
```
set_base_restraints(elevation=0, restraint="empotrado")
set_rigid_diaphragm(name="D1", elevation=3)
set_rigid_diaphragm(name="D2", elevation=6)
set_rigid_diaphragm(name="D3", elevation=9)
```

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-apoyos-3d.jpg` | Vista 3D mostrando los símbolos de empotramiento en la base | **hecha** — `R04-apoyos-diafragmas/01-apoyos-3d.jpg` |
| `02-apoyos-elevacion.jpg` | Elevación con los 9 apoyos visibles | **hecha** — `R04-apoyos-diafragmas/02-apoyos-elevacion.jpg` |
| `03-diafragmas.jpg` | Define > Diaphragms, listando D1/D2/D3 | **hecha** — `R04-apoyos-diafragmas/03-diafragmas.jpg` |
| `04-diafragma-planta.jpg` | Planta de un nivel con la asignación de diafragma visible | **hecha** — `R04-apoyos-diafragmas/04-diafragma-planta.jpg` |

Las cuatro capturas se tomaron en la sesión de captura del 2026-08-08.

## Criterio de aceptación
- 9 puntos empotrados en Z=0 (los 9 de la base, no 36).
- 3 diafragmas rígidos, cada uno con 9 puntos asignados.
- Si `set_base_restraints` reporta 36 puntos, el filtro por elevación falló.

## Resultado

**Estado: OK por API.** Los dos criterios verificables se cumplen. Capturas pendientes.

| Punto del criterio | Valor API | Criterio | Veredicto |
|---|---|---|---|
| Apoyos empotrados | 9 puntos en Z=0 | 9, no 36 | **OK** |
| Diafragmas rígidos | D1, D2, D3 — 9 puntos cada uno | 3 × 9 puntos | **OK** |

Verificado además leyendo de vuelta las tablas del modelo, no solo por el mensaje
de retorno de la herramienta:

- `Joint Assignments - Restraints`: 9 filas, todas en `Story = Base`, con
  UX/UY/UZ/RX/RY/RZ en `Yes`. Los nodos son 1, 8, 11, 15, 18, 21, 25, 29, 33 —
  exactamente los 9 de cota 0.
- `Diaphragm Definitions`: 3 filas, `D1`/`D2`/`D3`, todas `Rigid`.

### Ejecutado

```
set_base_restraints(elevation=0, restraint="empotrado")   -> 9 puntos
set_rigid_diaphragm(name="D1", elevation=3)               -> 9 puntos
set_rigid_diaphragm(name="D2", elevation=6)               -> 9 puntos
set_rigid_diaphragm(name="D3", elevation=9)               -> 9 puntos
save_model()
```

### Incidencia: `D1` ya existía y `SetDiaphragm` no sobrescribe

El primer `set_rigid_diaphragm(name="D1", ...)` falló con
`SetDiaphragm(2 args): ret=1`. La firma era correcta —verificada con
`describe_oapi`, dispid 5, `SetDiaphragm(Name: BSTR, SemiRigid: bool)`—: la causa
es que **ETABS ya había creado un diafragma llamado `D1`** al definir los niveles
en la interfaz, y `Diaphragm.SetDiaphragm` **no actúa como un `Set` idempotente**:
rechaza el nombre existente en vez de sobrescribirlo.

Se aisló la causa probando con un nombre libre (`DIAF_PRUEBA`), que funcionó al
primer intento. Confirmado después leyendo `Diaphragm Definitions`, que mostraba
`D1` preexistente.

Rodeo aplicado, sin tocar código ni reiniciar:

1. Escribir `Diaphragm Definitions` dejando solo `DIAF_PRUEBA` → libera el nombre `D1`.
2. `set_rigid_diaphragm("D1", 3)` → ahora crea y asigna.
3. `D2` y `D3`, que no existían, directo.
4. Escribir la tabla con `D1`/`D2`/`D3` → elimina `DIAF_PRUEBA`.

La tabla final confirma los tres, sin residuos.

**Deuda de código derivada:** `set_rigid_diaphragm` debería tolerar un diafragma
preexistente (envolver el `SetDiaphragm` en `try/except` y continuar con la
asignación de puntos). Es el mismo patrón de no-idempotencia que la auditoría
señaló para `add_load_pattern` y `add_load_combo` (secciones 7.1 y 7.2 de
`servidor-mcp\AUDITORIA-2026-08-07.md`), que va a morder igual en R05 y R07.

### Nota sobre `get_table_data` con tablas de pocas filas

Antes de definir nada, `Diaphragm Definitions` se leyó como "3 celdas, estructura
no reconocible". En realidad tenía **una fila** (`D1`) y el parser no pudo
distinguirla del encabezado: su heurística separa campos de datos por longitud y
falla cuando la tabla tiene una sola fila. Esa lectura ambigua casi hace concluir
que no había diafragmas. Deuda del servidor, ya anotada en R03.
