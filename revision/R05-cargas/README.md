# R05 — Patrones y asignación de cargas

## Herramientas
```
add_load_pattern(name="D",  pattern_type="muerta",     self_weight_multiplier=1.0)
add_load_pattern(name="SDL",pattern_type="supermuerta",self_weight_multiplier=0.0)
add_load_pattern(name="L",  pattern_type="viva",       self_weight_multiplier=0.0)
add_load_pattern(name="Lr", pattern_type="viva_techo", self_weight_multiplier=0.0)
assign_area_uniform_load(load_pattern="SDL", value=2.5)
assign_area_uniform_load(load_pattern="L",   value=2.40, elevations=[3.0, 6.0])
assign_area_uniform_load(load_pattern="Lr",  value=0.96, elevation=9.0)
```

Salida esperada:
- SDL → 12 de 12 áreas (sin filtro)
- L   → 8 de 12 áreas (Z = 3, 6)
- Lr  → 4 de 12 áreas (Z = 9)

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-patrones.jpg` | Define > Load Patterns con los 4 patrones | **hecha** — `R05-cargas/01-patrones.jpg` |
| `02-carga-viva-planta.jpg` | Display > Load Assigns > Shell, patrón L, mostrando 2.40 | **hecha** — `R05-cargas/02-carga-viva-planta.jpg` |
| `03-carga-techo.jpg` | Planta del techo con Lr = 0.96 | **hecha** — `R05-cargas/03-carga-techo.jpg` |

Las tres capturas se tomaron en la sesión de captura del 2026-08-08. La
etiqueta de `Lr = 0.96` en la planta del techo resultó ilegible por tamaño de
fuente; se confirmó el valor por la vía alterna del diálogo "Slab Information
> Loads" (clic derecho sobre un área del techo), documentado en el resumen de
la sesión.

## Criterio de aceptación
- 4 patrones. Solo D tiene multiplicador de peso propio = 1.
- L = 2.40 kN/m² (Tabla 4, oficinas). Lr = 0.96 kN/m² (Tabla 4, techos).

## Limitación resuelta
`assign_area_uniform_load` y `assign_frame_distributed_load` aceptan ahora
`elevation` (una cota) o `elevations` (varias). Solo cargan los objetos cuyos
vértices estén todos en la(s) cota(s) indicada(s). Sin el parámetro, el
comportamiento previo se mantiene: cargar todo.

Si el conteo de áreas cargadas no es 8 / 4, el filtro por cota falló.

## Resultado

**Estado: OK por API**, tras corregir un peso propio duplicado que el criterio
detectó. Capturas pendientes.

| Punto del criterio | Valor API | Criterio | Veredicto |
|---|---|---|---|
| Cantidad de patrones | 4 (D, SDL, L, Lr) | 4 | **OK** tras limpieza |
| Peso propio | solo `D` con SelfWtMult = 1 | solo D | **OK** tras limpieza |
| SDL en áreas | 12 de 12 | 12 | **OK** |
| L en áreas | 8 de 12 (Z = 3, 6) | 8 | **OK** |
| Lr en áreas | 4 de 12 (Z = 9) | 4 | **OK** |
| L = 2.40 kN/m² | 2.4, Gravity | Tabla 4, oficinas | **OK** |
| Lr = 0.96 kN/m² | 0.96, Gravity | Tabla 4, techos | **OK** |

El filtro por cota funciona: `Area Load Assignments - Uniform` tiene 24 filas —
12 de SDL repartidas en Story1/2/3, 8 de L solo en Story1 y Story2, y 4 de Lr solo
en Story3. Ninguna carga viva de oficina cayó en el techo ni al revés.

### Incidencia: ETABS traía `Dead` y `Live` por defecto, y `Dead` con peso propio = 1

Después de crear los cuatro patrones, `Load Pattern Definitions` mostraba **seis**:
los cuatro nuevos más `Dead` y `Live`, que ETABS crea al generar el modelo desde
plantilla. El problema no era el conteo sino que **`Dead` también tenía
`SelfWtMult = 1`**, igual que `D`.

Consecuencia si no se corrige: cualquier combinación o fuente de masa que incluya
`Dead` suma el peso propio **una segunda vez**. Las combinaciones de R07 usan
`D`, así que no se habría duplicado ahí, pero la fuente de masa sísmica por
defecto de ETABS sí puede referenciar `Dead` — y en R06/R08 eso habría inflado el
cortante basal sin ningún error visible.

Eliminados los dos por edición de tabla, dejando solo `D`, `SDL`, `L`, `Lr`.
Verificado releyendo la tabla.

Este es el segundo caso de la sesión en que **ETABS aporta objetos por defecto que
colisionan con los del protocolo** (el primero fue el diafragma `D1` en R04). Vale
como regla: antes de dar por buena una definición, leer la tabla correspondiente y
contar, no confiar en el mensaje de retorno de la herramienta, que solo informa lo
que ella creó y no lo que ya estaba.

### Ejecutado

```
add_load_pattern("D",   "muerta",      1.0)
add_load_pattern("SDL", "supermuerta", 0.0)
add_load_pattern("L",   "viva",        0.0)
add_load_pattern("Lr",  "viva_techo",  0.0)
[edición de tabla: eliminar los patrones Dead y Live de la plantilla]
assign_area_uniform_load("SDL", 2.5)                      -> 12 de 12
assign_area_uniform_load("L",   2.40, elevations=[3, 6])  ->  8 de 12
assign_area_uniform_load("Lr",  0.96, elevation=9)        ->  4 de 12
save_model()
```

### Nota sobre la no-idempotencia esperada

La auditoría anticipaba que `add_load_pattern` fallaría con nombres existentes
(secciones 7.1 y 7.2 de `servidor-mcp\AUDITORIA-2026-08-07.md`). No se manifestó
porque `D`, `SDL`, `L` y `Lr` estaban libres — los de la plantilla se llaman
`Dead` y `Live`. La deuda sigue abierta: **reejecutar este bloque tal cual va a
fallar** en el primer `add_load_pattern`, igual que pasó con el diafragma `D1`
en R04.
