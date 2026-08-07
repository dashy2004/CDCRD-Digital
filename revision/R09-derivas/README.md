# R09 — Derivas y verificación CDCRD

## Herramientas
`get_story_drifts(cases=["Ex","Ey"])`

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-tabla-derivas-etabs.jpg` | Display > Story Response Plots, o tabla de Story Drifts | **hecha** — `R09-derivas/01-tabla-derivas-etabs.jpg` |
| `02-grafico-derivas.jpg` | Gráfico de deriva por nivel | **hecha** — `R09-derivas/02-grafico-derivas.jpg` (Story Response Plots, Display Type = Max story drifts, Case = Ex; máximo 0.002748 en Story2, coincide con la tabla de abajo) |
| `03-comparacion.jpg` | Captura de la respuesta de la API junto a la tabla de ETABS | **hecha, con salvedad** — `R09-derivas/03-comparacion.jpg`. Reutiliza la captura de la tabla `Story Drifts` de ETABS (01); la conexión OAPI se perdió al abrir ETABS por escritorio en esta sesión (ver resumen), así que el lado "API" es el cotejo ya documentado más abajo (2026-08-07), no una llamada `get_story_drifts` fresca de esta noche. |

## Cálculo de verificación
```
Δ_diseño = δ_elástica · Cd / Ie      con Cd = 4.25, Ie = 1.0
Δ_admisible = 0.020 · hpx / ρ        con hpx = 3.0 m
```

| ρ | Δ admisible | δ elástica admisible |
|---|---|---|
| 1.0 | 60.0 mm | 14.12 mm |
| 1.3 | 46.2 mm | 10.87 mm |

## Punto abierto — resolver aquí
Cl. 2.10.11.1 (T1 p.95-96) obliga a dividir el límite entre ρ en CDS D con
pórticos a momento exclusivamente. Cl. 2.10.5.1.2 (T1 p.70) fija ρ = 1.3 salvo
que se cumplan dos condiciones:

1. Al menos dos vanos de pórtico a momento a cada lado del centro de masas en
   cada dirección. **Este edificio: 3 líneas x 2 vanos, planta simétrica → cumple.**
2. Que articular ambos extremos de una viga no pierda más del 35% de la
   resistencia lateral ni genere irregularidad torsional extrema.
   **Verificable solo con el modelo analizado.**

Procedimiento para cerrar el punto 2:
- `set_frame_releases(frame_id=..., start=["M3"], end=["M3"])` en una viga.
- Volver a correr y comparar el cortante basal / rigidez lateral.
- Si la pérdida < 35%, ρ = 1.0 y el límite es 60.0 mm.

Reportar ambos escenarios en la memoria hasta cerrar la verificación.

## Criterio de aceptación
- La API y la tabla de ETABS devuelven las mismas derivas.
- La columna de dirección dice X/Y, no etiquetas de punto
  (valida la corrección del parser por contenido).
- Orden de magnitud esperable de la deriva elástica: 0.001–0.005.

## Resultado

**Estado: OK. La estructura cumple en los DOS escenarios de ρ**, así que el punto
abierto del bloque no condiciona la verificación de derivas. Capturas pendientes.

### Criterio de aceptación

| Punto | Valor | Veredicto |
|---|---|---|
| API vs tabla de ETABS | coinciden en los 6 resultados | **OK** |
| Columna de dirección | dice `X` / `Y`, no etiquetas de punto | **OK** |
| Orden de magnitud | 0.00189 a 0.00275 | **OK** (esperado 0.001–0.005) |

Cotejo directo, API contra `Story Drifts` de ETABS:

| Nivel | API | ETABS | 1/n |
|---|---|---|---|
| Story3 | 0.00189 | 0.001893 | 1/528 |
| Story2 | 0.00275 | 0.002748 | 1/364 |
| Story1 | 0.00197 | 0.001969 | 1/508 |

Idénticas. Y la columna de dirección se resuelve por contenido, no por posición:
eso valida el `pick_direction` de `oapi.py` contra un resultado real.

Ex y Ey dan exactamente lo mismo en cada nivel, coherente con la simetría que ya
mostraron los modos 1 y 2 en R08.

### Verificación normativa

`Δ_diseño = δ_elástica · Cd / Ie` con Cd = 4.25, Ie = 1.0, hpx = 3.0 m.

| Nivel | deriva | δ elástica | Δ diseño | % de 60.0 mm (ρ=1.0) | % de 46.15 mm (ρ=1.3) |
|---|---|---|---|---|---|
| Story3 | 0.001893 | 5.68 mm | 24.14 mm | 40.2 % | 52.3 % |
| Story2 | 0.002748 | 8.24 mm | **35.04 mm** | **58.4 %** | **75.9 %** |
| Story1 | 0.001969 | 5.91 mm | 25.11 mm | 41.8 % | 54.4 % |

**Δ de diseño máxima: 35.04 mm en Story2.**

| ρ | Δ admisible | Veredicto |
|---|---|---|
| 1.0 | 60.00 mm | **CUMPLE** (58.4 %) |
| 1.3 | 46.15 mm | **CUMPLE** (75.9 %) |

Control por la vía inversa, como plantea la tabla del bloque: la deriva elástica
máxima obtenida es 8.24 mm, contra 14.12 mm admisibles con ρ = 1.0 y 10.86 mm con
ρ = 1.3. Consistente.

### Punto abierto de ρ: resuelto para derivas, ABIERTO para las combinaciones

**Para este bloque queda cerrado:** como la estructura cumple incluso con ρ = 1.3,
que es el valor conservador, no hace falta ejecutar el procedimiento de liberación
de extremos de viga (`set_frame_releases` + recorrer y comparar rigidez lateral)
para validar la condición 2 de cl. 2.10.5.1.2. El resultado no cambia.

**Pero ρ sigue importando en otro lado, y esto hay que resolverlo.** El factor de
redundancia no solo divide el límite de deriva: también amplifica la acción sísmica
en las combinaciones, `E = ρ·QE ± 0.2·SDS·D`. Las combinaciones creadas en R07 usan
**`Ex` y `Ey` con factor 1.0**, lo que equivale a asumir **ρ = 1.0**:

```
C4x = 1.2975 D + 1.2975 SDL + 1.0 L + 1.0 Ex
C5x = 0.8025 D + 0.8025 SDL + 1.0 Ex
```

Si ρ resulta ser 1.3, esos términos deben ser `1.3·Ex` y `1.3·Ey`, y las
combinaciones de R07 quedan **del lado inseguro para el diseño** — no para las
derivas, donde el CDCRD trata ρ dividiendo el límite en vez de amplificar la
acción.

Consecuencia práctica: **las reacciones de R10 y cualquier diseño posterior están
calculados con ρ = 1.0.** Antes de usar esos resultados para dimensionar hay que
cerrar la condición 2 de cl. 2.10.5.1.2, o adoptar ρ = 1.3 por conservadurismo y
rehacer las cuatro combinaciones sísmicas.

Este punto no lo detecta ningún criterio de aceptación del protocolo; surge de
cruzar R07 con R09.

### Ejecutado

```
get_story_drifts(cases=["Ex","Ey"])
get_table_data("Story Drifts")     # cotejo independiente
```
