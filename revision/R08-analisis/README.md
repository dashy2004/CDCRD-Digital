# R08 — Ejecución del análisis

## Herramientas
`save_model()` → `run_analysis()`

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-antes-analisis.jpg` | Modelo completo antes de correr | **PENDIENTE** |
| `02-ventana-analisis.jpg` | Ventana de progreso del análisis de ETABS | **PENDIENTE** |
| `03-deformada.jpg` | Deformada bajo Ex (Display > Deformed Shape) | **PENDIENTE** |
| `04-modos.jpg` | Primer modo de vibración con su periodo | **PENDIENTE** |

## Criterio de aceptación
- El análisis termina sin errores ni advertencias de inestabilidad.
- La deformada bajo Ex es un desplazamiento lateral coherente, sin nodos sueltos.
- Periodo fundamental en un rango plausible para un pórtico de 3 niveles de
  hormigón (orden de 0.3–0.6 s). Un periodo muy alto indica que faltan
  diafragmas o que las secciones no se asignaron.

## Resultado

**Estado: OK.** El análisis corrió sin errores y los resultados modales son
coherentes. Capturas pendientes.

| Punto del criterio | Valor | Criterio | Veredicto |
|---|---|---|---|
| Ejecución | `run_analysis()` sin error | sin errores ni inestabilidad | **OK** |
| Periodo fundamental | **T₁ = 0.358 s** | 0.3–0.6 s (pórtico de 3 niveles) | **OK** |
| Deformada bajo Ex | — | lateral coherente | **PENDIENTE** (captura) |

### Resultados modales — 12 modos

| Modo | T (s) | Naturaleza | UX | UY | RZ |
|---|---|---|---|---|---|
| 1 | 0.358 | traslación Y | 0.0024 | 0.8397 | 0 |
| 2 | 0.358 | traslación X | 0.8397 | 0.0024 | 0 |
| 3 | 0.289 | **torsión** | 0 | 0 | 0.8411 |
| 4-5 | 0.107 | segundo modo traslacional | 0.118 | 0.118 | 0 |
| 6 | 0.087 | segunda torsión | 0 | 0 | 0.1232 |
| 7-8 | 0.059 | tercer traslacional | 0.0339 | 0.0339 | 0 |
| 9 | 0.047 | tercera torsión | 0 | 0 | 0.0358 |
| 10-12 | 0.007 | modos locales | 0 | 0 | 0 |

Tres lecturas que validan el modelo más allá del criterio literal:

**Los modos 1 y 2 tienen el mismo periodo (0.358 s) y participaciones espejadas**
(0.8397 en Y y en X respectivamente). Es exactamente lo que corresponde a una
planta cuadrada de 2×2 crujías iguales con columnas C50x50: la rigidez lateral es
idéntica en ambas direcciones. Si hubieran salido distintos, algo estaría asimétrico.

**El tercer modo es torsional puro** (RZ = 0.8411) y su periodo, 0.289 s, es
**menor** que el de los dos traslacionales. Ese orden —traslación antes que
torsión— es el deseable en diseño sismorresistente; el caso inverso indicaría un
problema de rigidez torsional.

**La masa participante llega a 1.0000 en UX y UY en el modo 8**, con 0.842
acumulado ya en los dos primeros modos. Esto confirma indirectamente que **el peso
propio existe**: si `H28` hubiera quedado sin peso por unidad de volumen —el
defecto silencioso corregido en R03— no habría masa que participar y los periodos
carecerían de sentido físico. Es la validación cruzada de aquel parche.

UZ = 0 en todos los modos porque los diafragmas rígidos de R04 restringen la
losa en su plano y no hay masa vertical movilizada; es lo esperado.

### Ejecutado

```
save_model(path=".../edificio_oficinas_SD.EDB")
run_analysis()          -> "Analisis ejecutado."
save_model()
```

### Nota sobre el archivo del modelo

`get_model_info` reporta la ruta como `edificio_oficinas_SD.$et` en vez de `.EDB`.
Es el archivo de trabajo interno de ETABS; no indica pérdida de datos. Se forzó un
`save_model(path=...)` explícito al `.EDB` y el archivo en disco quedó actualizado
(192 KB). `GetModelFilename` sigue devolviendo el `.$et` mientras el modelo está
abierto, lo cual es cosmético.

### Lo que este bloque cierra de bloques anteriores

- **R03:** el peso propio funciona (masa participante = 1.0).
- **R04:** los diafragmas funcionan (UZ nulo, modos traslacionales limpios).
- **R06:** los casos `Ex`/`Ey` no impidieron el análisis, y `ZZ_TEST_FUNC` no lo
  hizo fallar.
- **El fix de `get_table_data` sirve para resultados**: `Modal Periods And
  Frequencies` y `Modal Participating Mass Ratios` se leyeron completas, con 12
  filas cada una. Ese era el canal que R09 y R10 necesitan.
