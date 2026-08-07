# R10 — Reacciones y chequeo de equilibrio

## Herramientas
`get_joint_reactions(cases=["C2"])`   # C2 = 1.2(D+SDL) + 1.6L + 0.5Lr

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-reacciones-etabs.jpg` | Display > Joint Reactions bajo C2 | **PENDIENTE** |
| `02-tabla-reacciones.jpg` | Tabla de reacciones de ETABS | **PENDIENTE** |
| `03-suma-verificacion.jpg` | Respuesta de la API junto al total de ETABS | **PENDIENTE** |

## Chequeo de equilibrio
ΣFz de las 9 reacciones debe cerrar con la carga total mayorada aplicada.

Con espesor de losa t = 0.15 m, la carga total bajo 1.2D+1.6L se estimó en
**5785 kN**. Valores paramétricos calculados previamente:

| t (m) | ΣFz esperada (kN) |
|---|---|
| 0.12 | 5411 |
| 0.15 | 5785 |
| 0.20 | 6407 |

Criterio: error < 1% respecto al valor correspondiente al espesor real usado.
Una diferencia mayor indica cargas no aplicadas o peso propio mal contabilizado.

## Criterio de aceptación
- 9 reacciones (una por columna de la base).
- ΣFz coincide con la carga aplicada dentro del 1%.
- ΣFx y ΣFy ≈ 0 bajo carga puramente gravitacional.

## Resultado

**Estado: OK, con un hallazgo.** El equilibrio cierra dentro del 1%, pero **contra
el espesor de losa de 0.20 m, no contra los 0.15 m que el protocolo asumía**. Es
exactamente el tipo de discrepancia que este chequeo existe para detectar.

### Criterio de aceptación

| Punto | Valor | Veredicto |
|---|---|---|
| Cantidad de reacciones | 9, una por columna de la base | **OK** |
| ΣFz vs carga aplicada | error −0.65 % contra t = 0.20 m | **OK** (<1%) |
| ΣFx, ΣFy bajo gravedad | **0.000 y 0.000** kN | **OK** |

### Reacciones bajo C2 = 1.2(D+SDL) + 1.6L + 0.5Lr

| Posición | Nodos | Fz (kN) |
|---|---|---|
| Esquinas | 1, 11, 25, 33 | 404.706 |
| Bordes | 8, 15, 21, 29 | 786.128 |
| Centro | 18 | 1602.186 |
| | **ΣFz** | **6365.522** |

El reparto es el de un pórtico regular de 2×2 crujías: la columna central toma
aproximadamente 4 veces la de esquina (1602 / 405 = 3.96) y las de borde, el doble
(786 / 405 = 1.94). Coherente con áreas tributarias de 1 : 2 : 4.

ΣFx y ΣFy dan **exactamente cero**, con las reacciones horizontales cancelándose
por pares opuestos (±17.418 y ±34.075). Bajo carga puramente gravitacional en una
planta simétrica es el resultado correcto, y confirma que no hay cargas laterales
espurias en C2.

### El hallazgo: el espesor de losa nunca se definió

| t (m) | ΣFz esperada | Error respecto a 6365.5 kN |
|---|---|---|
| 0.12 | 5411 | +17.64 % |
| 0.15 | 5785 | +10.03 % |
| **0.20** | **6407** | **−0.65 %** ← cumple |

Resolviendo el espesor implícito desde las reacciones y las cargas conocidas
(columnas 477.2 kN, vigas 763.4 kN, SDL 1080.0 kN, L 691.2 kN, Lr 138.2 kN):

**t implícito = 0.1969 m**

Causa: **el protocolo nunca definió una propiedad de losa.** R03 creó materiales y
secciones de frame (`C50x50`, `V30x50`) pero ninguna sección de área. Las 12 áreas
quedaron con `Slab1`, la propiedad que ETABS genera por defecto al crear el modelo
desde plantilla — de espesor ≈ 0.20 m (8 in del template en unidades imperiales),
no los 0.15 m que `INSTRUCCIONES.md` declara como "valor de trabajo".

Consecuencia: **todos los resultados de R08, R09 y R10 corresponden a losas de
≈0.197 m**, no de 0.15 m. Las derivas de R09 cumplen igual (y con más masa son más
exigentes, así que el margen es conservador respecto al supuesto documentado), pero
la memoria no puede citar 0.15 m.

Dos vías para cerrarlo, según si 0.15 m es un requisito real o un supuesto:

1. **Actualizar la documentación a ≈0.20 m** y dejar el modelo como está. Es lo
   coherente si 0.15 m era solo un valor tentativo, que es lo que la propia tabla de
   `INSTRUCCIONES.md` dice ("Sin dato del proyecto").
2. **Definir una losa de 0.15 m**, reasignarla a las 12 áreas y rehacer R08–R10. No
   hay herramienta MCP para definir secciones de área (solo frame), así que habría
   que hacerlo por la tabla `Slab Property Definitions` o en la interfaz.

No se pudo leer el espesor exacto por API en la corrida original. **Cerrado el
2026-08-07 con `get_area_sections`** (Tanda 1), que lee `PropArea.GetSlab`:

```
Slab1: losa, espesor 0.2032, material '4000Psi'
```

**t real = 0.2032 m** (8 pulgadas — dato de plantilla imperial) con material
**`4000Psi`** (f'c = 27 579 kN/m² = 27.6 MPa), **no H28**. La deducción por
reacciones (0.1969 m) quedó a 3 % del valor real; la diferencia viene de las
simplificaciones del desglose de cargas. Ambas sospechas del acta —espesor de
plantilla y material distinto de H28— quedaron confirmadas por lectura directa.

### Nota sobre el material de la losa

`Slab1` es una propiedad por defecto de ETABS, así que su material probablemente
**no es `H28`** sino el hormigón por defecto de la plantilla. Para el peso propio la
diferencia es despreciable (ambos rondan 23.56 kN/m³), pero para rigidez y diseño
importa: el f'c puede no ser 28 MPa. Verificar antes de cualquier diseño de losa.

### Validación del parche de columnas

Este bloque confirma la corrección aplicada a `get_joint_reactions`: la salida
etiqueta correctamente `F1, F2, F3, M1, M2, M3` y los valores de F3 son
verticales y del orden esperado. Con el código anterior —que tomaba las **seis
primeras** columnas numéricas— la primera habría sido `StepNum` y todo el reporte
habría salido corrido una posición, con M3 perdido. El chequeo de equilibrio no
habría cerrado y el diagnóstico habría apuntado, erróneamente, a las cargas.

### Ejecutado

```
get_joint_reactions(point_ids=[los 9 de la base], cases=["C2"])
save_model()
```
