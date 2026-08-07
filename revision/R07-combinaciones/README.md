# R07 — Combinaciones LRFD

## Base normativa
Cl. 2.4.2, T1 p.28-29. Ev = 0.2·SDS·D = 0.2·0.4877·D = 0.0975·D
(cl. 2.10.6.3, Ec. 17, T1 p.71-72).

## Herramientas
```
add_load_combo("C1",  {"D":1.4, "SDL":1.4})
add_load_combo("C2",  {"D":1.2, "SDL":1.2, "L":1.6, "Lr":0.5})
add_load_combo("C3",  {"D":1.2, "SDL":1.2, "Lr":1.6, "L":1.0})
add_load_combo("C4x", {"D":1.2975, "SDL":1.2975, "L":1.0, "Ex":1.0})
add_load_combo("C4y", {"D":1.2975, "SDL":1.2975, "L":1.0, "Ey":1.0})
add_load_combo("C5x", {"D":0.8025, "SDL":0.8025, "Ex":1.0})
add_load_combo("C5y", {"D":0.8025, "SDL":0.8025, "Ey":1.0})
```

Derivación de los factores sísmicos:
- 1.2 + Ev = 1.2 + 0.0975 = **1.2975**
- 0.9 − Ev = 0.9 − 0.0975 = **0.8025**

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-lista-combos.jpg` | Define > Load Combinations, lista completa | **PENDIENTE** |
| `02-combo-sismica.jpg` | Detalle de C4x mostrando los factores 1.2975 y 1.0 | **PENDIENTE** |

## Criterio de aceptación
- 7 combinaciones creadas.
- Los factores de C4/C5 reflejan Ev correctamente (1.2975 / 0.8025), no 1.2 / 0.9.
- Sin combinaciones de viento (fuera del alcance) ni de fluidos.

## Resultado

**Estado: OK, verificado contra el modelo.** Cerrado el 2026-08-07 con la
herramienta `get_load_combos` (Tanda 1 del plan de mejoras), que lee
`RespCombo.GetCaseList` directamente:

```
C1 = 1.4D + 1.4SDL
C2 = 1.2D + 1.2SDL + 1.6L + 0.5Lr
C3 = 1.2D + 1.2SDL + 1.6Lr + 1L
C4x = 1.2975D + 1.2975SDL + 1L + 1Ex
C4y = 1.2975D + 1.2975SDL + 1L + 1Ey
C5x = 0.8025D + 0.8025SDL + 1Ex
C5y = 0.8025D + 0.8025SDL + 1Ey
```

Los factores leídos del modelo coinciden con los del eco de creación, incluidos
los sísmicos 1.2975 / 0.8025. Sin términos duplicados. La captura 02 pasa de
"única verificación" a documentación.

| Punto del criterio | Valor | Criterio | Veredicto |
|---|---|---|---|
| Cantidad | 7 combinaciones | 7 | **OK** (eco de las llamadas) |
| Factor sísmico superior | 1.2975 en C4x/C4y | 1.2 + Ev, no 1.2 | **OK** |
| Factor sísmico inferior | 0.8025 en C5x/C5y | 0.9 − Ev, no 0.9 | **OK** |
| Sin viento ni fluidos | ninguna creada | — | **OK** |
| Relectura desde el modelo | tabla sin filas | — | **PENDIENTE** |

Derivación verificada antes de escribir, contra la tabla normativa de
`INSTRUCCIONES.md`: `Ev = 0.2·SDS·D = 0.2 × 0.4877 = 0.09754 ≈ 0.0975`, de donde
`1.2 + Ev = 1.2975` y `0.9 − Ev = 0.8025`.

### Combinaciones creadas

| Nombre | Composición |
|---|---|
| C1 | 1.4 D + 1.4 SDL |
| C2 | 1.2 D + 1.2 SDL + 1.6 L + 0.5 Lr |
| C3 | 1.2 D + 1.2 SDL + 1.6 Lr + 1.0 L |
| C4x | 1.2975 D + 1.2975 SDL + 1.0 L + 1.0 Ex |
| C4y | 1.2975 D + 1.2975 SDL + 1.0 L + 1.0 Ey |
| C5x | 0.8025 D + 0.8025 SDL + 1.0 Ex |
| C5y | 0.8025 D + 0.8025 SDL + 1.0 Ey |

No hubo colisión de nombres: ETABS no traía combinaciones por defecto en este
modelo (la tabla `Load Combination Definitions` ni siquiera figuraba en
`list_tables` antes de crearlas). La no-idempotencia de `SetCaseList` que
anticipaba la auditoría (sección 7.1) no llegó a manifestarse por eso, pero **sigue
latente**: reejecutar este bloque duplicaría los factores, porque `SetCaseList`
agrega términos en vez de reemplazarlos.

### Defecto encontrado y corregido: `get_table_data` pedía un campo inexistente

Al intentar verificar las combinaciones contra el modelo, la tabla devolvió solo
encabezados. Mismo síntoma que en R06 con las funciones de espectro y los casos.

Causa, leída del typelib:

```
GetTableForDisplayArray([in] TableKey, [in,out] FieldKeyList: SAFEARRAY(BSTR), [in] GroupName, ...)
```

`get_table_data` pasaba `FieldKeyList = [""]` — una lista con **un** campo cuyo
nombre es la cadena vacía. Lo correcto es una lista **vacía**, que en la OAPI
significa "todos los campos". Algunas tablas (Grid, Story, Diaphragm, Load
Pattern, y todas las de asignaciones) toleran el valor y devuelven todo igual; por
eso el defecto pasó inadvertido durante R02 a R05. Las de la familia
casos/combinaciones/funciones no lo toleran y devuelven la tabla vacía.

Corregido en `Etabs.py::get_table_data` y en la lectura de `TableVersion` de
`set_table_data`, dejando la forma anterior como variante de respaldo. **Sin
probar**: el proceso `fea` tiene el código previo en memoria.

Impacto más allá de este bloque: es el mismo canal que R08, R09 y R10 van a usar
para leer resultados. Corregirlo ahora evita repetir el diagnóstico tres veces.

### Ejecutado

```
add_load_combo("C1",  {"D":1.4, "SDL":1.4})
add_load_combo("C2",  {"D":1.2, "SDL":1.2, "L":1.6, "Lr":0.5})
add_load_combo("C3",  {"D":1.2, "SDL":1.2, "Lr":1.6, "L":1.0})
add_load_combo("C4x", {"D":1.2975, "SDL":1.2975, "L":1.0, "Ex":1.0})
add_load_combo("C4y", {"D":1.2975, "SDL":1.2975, "L":1.0, "Ey":1.0})
add_load_combo("C5x", {"D":0.8025, "SDL":0.8025, "Ex":1.0})
add_load_combo("C5y", {"D":0.8025, "SDL":0.8025, "Ey":1.0})
save_model()
```
