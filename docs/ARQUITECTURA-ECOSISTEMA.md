# Arquitectura del ecosistema CAD → BIM → cálculo → planos

Fecha: 2026-08-10. Estado: diseño, no implementado.

## Hallazgo que cambia el planteamiento

El ecosistema no se construye desde cero. Cinco de las siete capas ya tienen
una pieza construida y, en varios casos, probada en un proyecto real. El
trabajo no es "hacer el pipeline", es **conectar piezas existentes y cerrar
tres huecos concretos**.

Inventario verificado (BRAIN + repos + sondeo en vivo de la OAPI el
2026-08-10):

| Pieza | Estado | Evidencia |
|---|---|---|
| `motor-fea` (Python 3.11) — losas por FEM, reparto 45°, descenso de cargas, zapatas ACI 318-19, columnas P-M, vigas continuas | Construido. CLI `motor-fea --serve modelo.json` en `127.0.0.1:8000` | `BRAIN/03_APPS/EstructurasRD/` |
| Puente Dynamo → Revit | **Parcial.** Losas (657) y muros (168) creados OK en Torre Evolution. El nodo de barras nunca corrió con éxito. Estado de la nota: `modelo-revit-parcial-etabs-pendiente`. Solo cubre el sentido de *creación*; el detallado de vuelta no tiene ninguna evidencia. | `2026-08-07 Torre Evolution-RD...md` |
| Revit → ETABS end-to-end | **Geometría sí, diseño no verificable.** Modelo RESTAURANTE corrido, equilibrio cerrado (−0.46% constante, explicado por solape en nudos). Estado: `modelo-corrido-diseno-no-verificable`. | `2026-08-07 FEA-MCP - modelo RESTAURANTE end-to-end Revit a ETABS.md` |
| FEA-MCP (ETABS) | 54 herramientas, ETABS 23.3.0 / OAPI 2.016 | `servidor-mcp/`, protocolo `revision/R01`–`R10` |
| SAFE MCP | v0.1.0, conectado hoy, 4 firmas verificadas y 3 bugs corregidos | `servidor-mcp-safe/` |
| CDCRD digitalizado | 3,492 artículos, doble capa legal + `machine` | `datos/titulos/`, `datos/machine/` |
| Plantilla Excel de losas | Fórmulas descifradas (no el archivo) | `validacion/2026-08-06-excel-plantilla-profesional.md` |
| Programa LOSA (F. Perdomo v5.21) | Formato `.DL` entrada / `.TXT` salida descifrado | `BRAIN/99_META/archivo-migracion/proyecto-estructurasrd-stub/` |

Nota terminológica: el software que llamás "DIGSET" se identifica a sí mismo
en sus propios archivos como *Diseño de Sistemas de Losas, F. Perdomo Ver.
5.21*. En todo este documento se lo llama **PROGRAMA-LOSA** para no arrastrar
un nombre que no aparece en ninguna fuente.

## Los tres huecos reales

1. **Entrada**: no existe nada que convierta un DWG en datos estructurales.
   Es el hueco más grande y el de mayor retorno.
2. **`eFileType`**: el valor numérico para F2K y DXF en la OAPI de SAFE.
   Bloquea la automatización ETABS→SAFE y SAFE→AutoCAD. Sale de la ayuda
   oficial de la OAPI, no de introspección.
3. **Escritura de detalle en Revit**: los MCP de Revit conectados son de solo
   lectura. La vía es Dynamo — la nota de Torre Evolution lo dice sin rodeos:
   *"el MCP no sirve, Dynamo sí"*. Pero **eso está probado solo en el sentido
   de creación de geometría** (losas y muros), no en el de detallado. Escribir
   armadura o parámetros de acero sobre elementos existentes no se ha
   intentado nunca. El camino está identificado, no recorrido.

Corrección respecto a la versión anterior de este documento (2026-08-10,
primera redacción): se afirmó que el puente Dynamo estaba "probado en
producción". Al leer la bitácora completa, el estado real es
`modelo-revit-parcial-etabs-pendiente` — el nodo de barras nunca corrió con
éxito y el detallado de vuelta no existe. La afirmación era demasiado fuerte.

## Las siete capas

```
  [DWG]  ──┐
           ├─→ C0 capas ─→ C1 extractor ─→ proyecto.json ─┐
  [PDF]  ──┘   (AutoCAD)     (ezdxf)                       │
                                                            ▼
                                                    C2 Dynamo → Revit
                                                            │
                                            ┌───────────────┴─────────┐
                                            ▼                         ▼
                                    C3 Revit → ETABS          C5 losas
                                    (FEA-MCP)                 (motor-fea
                                            │                  o PROGRAMA-LOSA)
                                            ▼                         │
                                    C4 ETABS → SAFE                   │
                                    (F2K)                             │
                                            │                         │
                                            └────────┬────────────────┘
                                                     ▼
                                          C6 detallado en Revit
                                             (Dynamo, vuelta)
                                                     │
                                                     ▼
                                          C7 planos + presupuesto
```

### C0 — Convención de capas en AutoCAD (el contrato)

Tu intuición de que "configurar el AutoCAD es lo más rentable" es correcta y
esta arquitectura la adopta como cimiento. Razón técnica: un DWG sin
convención es un montón de líneas sin semántica; ningún parser ni modelo de
visión recupera de forma confiable qué línea es una viga y cuál es una cota.
Con capas nombradas, la extracción se vuelve determinista — código que se
puede testear, no heurística que falla en silencio.

El SOP ya define una convención por **color** (vigas morado, muros y columnas
rojo, dinteles morado con eje rosado, losas cyan con `L1`/`H=0.16`). El color
es una clave frágil: se hereda de bloques, se cambia sin querer, y AutoCAD lo
resuelve por ByLayer/ByBlock. La propuesta migra esa misma semántica a
**capas nombradas**, conservando los colores para que el dibujo se siga viendo
igual y el equipo no tenga que reaprender nada visualmente.

Detalle completo en `CONVENCION-CAPAS-CAD.md`.

**Camino PDF**: es un camino degradado, no un camino paralelo. Un PDF vectorial
puede convertirse a DWG y luego seguir el camino normal; un PDF raster solo
sirve como *underlay* para redibujar encima con la convención de capas. No hay
extracción confiable directa desde PDF raster. EstructurasRD ya tiene un
importador CAD desde DXF y experimentos con Qwen2.5-VL para generar modelo
desde foto — eso puede acelerar el redibujado, pero el resultado sigue
requiriendo revisión humana antes de calcular.

### C1 — Extractor DXF → `proyecto.json`

Script Python con `ezdxf`. Lee el DXF exportado de AutoCAD, recorre entidades
por capa, y emite geometría estructural con semántica:

- Ejes (`E-EJE-*`) → grid, con etiquetas.
- Columnas y muros (`E-COL`, `E-MUR`) → polilíneas cerradas → sección y punto
  de inserción.
- Vigas y dinteles (`E-VIG`, `E-DIN`) → líneas de eje + ancho.
  La regla del SOP se codifica acá: **luz libre > 2 m → viga; ≤ 2 m con
  puerta/ventana → dintel**.
- Losas (`E-LOS`) → contorno cerrado + texto de etiqueta (`L1`, `H=0.16`) →
  número, espesor, tipo (maciza / aligerada 1D / aligerada 2D según la
  convención de leyenda del SOP).

Por qué DXF y no leer el DWG desde Dynamo: el extractor queda como código
Python testeable, sin dependencia de Revit para correr, y reutiliza el
importador CAD que EstructurasRD ya tiene. Además permite validar el dibujo
*antes* de abrir Revit, que es donde el error sale barato.

**Salida canónica**: `proyecto.json`. Ver `ESQUEMA-PROYECTO.md`.

### C2 — `proyecto.json` → Revit vía Dynamo

Capa parcialmente probada: en Torre Evolution los nodos de losas y muros
crearon 657 y 168 elementos correctamente; el nodo de barras no ha llegado a
correr con las familias cargadas. El patrón se reutiliza y su lección más
importante se conserva como regla de diseño:

> Los nodos se encadenan **por dato**, no por posición. Dynamo no garantiza
> orden de ejecución entre ramas que no tienen dependencia de datos.

El código Python vive en `py_v2/*.py` como fuente de verdad y el `.dyn` se
genera con `_generar_dyn_v2.py`. Mantener esa disciplina: el grafo es un
artefacto compilado, no el original que se edita a mano.

Errores ya registrados a no repetir (`BRAIN/99_META/ERRORES-IA.md`): E-025
(nodo de losas con `List[CurveLoop]` sin `from System.Collections.Generic
import List`), E-026 (afirmar cuál es el documento activo de Revit sin leer
`activeDocument.name`).

### C3 — Revit → ETABS

Vía FEA-MCP, ya probado end-to-end con el modelo RESTAURANTE. Los pasos 1–25
del SOP (sección ETABS de `Pasos.pdf`) se automatizan con las herramientas
existentes más las tres que faltan, cuya existencia se confirmó hoy en la
OAPI real:

| Paso SOP | Herramienta | Estado |
|---|---|---|
| 5 — reducir inercias (col 0.80, viga 0.60, muro m11/m22) | `PropFrame.SetModifiers`, `PropArea.SetModifiers` | Existe en OAPI, **falta exponer** |
| 8 — masa modal por patrón de carga | `SapModel.SourceMass` | Existe (el namespace es `SourceMass`, no `MassSource`), **falta exponer** |
| 19 — panel zone en nodos | `PointObj.SetPanelZone(Name, PropType, Thickness, K1, K2, LinkProp, Connectivity, LocalAxisFrom, LocalAxisAngle)` | Firma verificada hoy, **falta exponer** |
| 27 — diseño de muros de corte | `SapModel.DesignShearWall` | Existe, **falta exponer** |
| resto | 54 herramientas ya operativas | Listo |

### C4 — ETABS → SAFE

`File > Export > Story as SAFE V12 .F2K` en ETABS, `File > Import > SAFE .f2k
Text File` en SAFE. Automatizable con `export_file`/`import_file` del SAFE MCP
**en cuanto se conozca el `eFileType`**. Hoy es el bloqueo #2.

Después del import, el SAFE MCP ya cubre: materiales, secciones de losa y
zapata (`Slab`/`Drop`/`Stiff`/`Footing`), resorte de suelo `k = 1.2·σadm` con
compresión únicamente, combinaciones (Art. 58 del R-033), análisis, diseño de
losa (`StartSlabDesign`) y lectura del acero resultante por franja
(`get_slab_design_summary`). Presión de contacto y punzonamiento se leen por
`list_tables` + `get_table_data`.

### C5 — Losas: dos motores, misma interfaz

Rama independiente que puede correr en paralelo a C3/C4. Dos opciones con
trade-offs distintos:

**(a) `motor-fea` de EstructurasRD.** Ya calcula losas por FEM y reparto a 45°.
Ventaja decisiva: expone `--serve` en `127.0.0.1:8000`, o sea que **ya es un
servicio HTTP** — envolverlo en un MCP es trabajo menor comparado con
construir un motor. Contra: es tuyo, así que la responsabilidad de validarlo
contra el código es tuya también.

**(b) PROGRAMA-LOSA (F. Perdomo v5.21).** Es lo que la firma usa hoy y lo que
el SOP documenta. Formato `.DL` de entrada (columnas fijas, comentarios `$`)
y `.TXT` de salida — ambos ya descifrados, y EstructurasRD ya tiene vistas
para diagnosticarlos (`DLDoctorWindow`, `TxtTablaView`). Se automatiza
generando el `.DL` desde `proyecto.json` y parseando el `.TXT` de vuelta.
Ventaja: cero cambio metodológico, resultados idénticos a los que el equipo
ya revisa. Contra: diseña según ACI 318-08 (el `.TXT` lo dice), no 318-19 ni
CDCRD 2026.

Ambas rutas escriben el mismo bloque `losas[].armado` de `proyecto.json`, así
que la decisión no contamina el resto del pipeline y se puede cambiar después.

**Hallazgo normativo que corresponde señalar**: la validación cruzada ya hecha
(`validacion/2026-08-06-excel-plantilla-profesional.md`) encontró que la plantilla usa
CV de escaleras 0.40 t/m² = 3.92 kN/m² contra 4.79 kN/m² del CDCRD 2026 —
déficit del 18%. Es un incumplimiento normativo verificable, no una opinión
de criterio. Cualquier automatización que copie la plantilla sin corregir
propaga ese déficit a todos los proyectos, en silencio y a escala. La capa
`datos/machine/` del CDCRD digitalizado existe justamente para que los valores
normativos vengan del código y no de una celda heredada.

### C6 — Detallado del modelo de Revit (la vuelta)

Dynamo lee `proyecto.json` ya enriquecido con resultados (secciones finales,
acero longitudinal y transversal, espesores, armado de losas, zapatas) y
escribe en Revit. Esto es lo que pedís cuando decís que el modelo tenga las
distancias correctas, el ángulo correcto y los aceros camellados correctos.

Precisión importante sobre alcance: Dynamo **puede** colocar `Rebar` real en
Revit (elemento de armadura con geometría, recubrimiento, ganchos, traslapes).
Es considerablemente más trabajo que escribir parámetros de texto. Hay dos
niveles y conviene elegirlo a conciencia:

- **Nivel A — parámetros**: cada elemento lleva su armado como parámetro
  compartido (`As_sup_X`, `As_inf_Y`, `Estribos`, etc.). Los planos se anotan
  por etiqueta y las tablas salen directo. Rápido de implementar, cubre planos
  y presupuesto.
- **Nivel B — `Rebar` real**: armadura modelada, con interferencias reales y
  cantidades exactas por despiece. Mucho más costoso, y solo rinde si los
  planos de detalle van a salir del modelo 3D y no de detalles 2D típicos.

La regla del SOP sobre solape (*"a ¾ de la losa principal, cruzando a ¾ de la
losa continua"*) y el camellado (macizas sí, aligeradas no) son reglas
codificables en cualquiera de los dos niveles.

### C7 — Planos y presupuesto

Con el modelo detallado, las cantidades salen de *schedules* de Revit. El MCP
de Revit conectado **sí** puede exportar schedules a CSV (`export_views` con
`fileFormat: "CSV"`) — eso ya funciona hoy, sin desarrollo. De ahí a la
plantilla de presupuesto es una transformación de datos.

## El archivo de proyecto como bus

Pediste que un Excel en la carpeta del proyecto sea "la vía de ir hablando
entre proyectos". Ese archivo cumple dos funciones que conviene no mezclar:

1. **Superficie de entrada humana**: donde el ingeniero escribe uso de cada
   losa, σadm del suelo, f'c, alturas. Excel es correcto acá: el equipo ya
   trabaja así y la plantilla existe.
2. **Estado canónico entre etapas**: lo que el extractor escribe y Dynamo lee.
   Acá Excel tiene un problema concreto: no es diffable, no se versiona bien
   en git, y un formato de celda mal puesto rompe el parseo sin avisar.

Alternativas, con sus trade-offs:

| Opción | A favor | En contra |
|---|---|---|
| **Excel único** (todo en `.xlsx`) | Una sola cosa que aprender. Cero fricción con el equipo actual. | Frágil como formato de intercambio. Difícil de versionar y de auditar qué cambió entre corridas. |
| **JSON único** (todo en `proyecto.json`) | Diffable, versionable, validable con esquema, testeable. | El ingeniero no lo va a editar a mano. Requiere una UI o formularios. |
| **Excel entrada + JSON canónico**, con sincronización en un sentido (Excel → JSON al inicio, JSON → Excel de reporte al final) | Cada formato hace lo que hace bien. El Excel sigue siendo la cara visible. | Dos artefactos que mantener sincronizados; hay que ser disciplinado sobre cuál manda. |

Esta decisión condiciona todo lo que se implemente después, así que conviene
tomarla antes de escribir el extractor. El esquema propuesto en
`ESQUEMA-PROYECTO.md` está escrito para funcionar con cualquiera de las tres.

## Orden de implementación sugerido

El criterio es: primero lo que desbloquea más, y dentro de eso primero lo
barato de descubrir.

1. **Convención de capas + un DWG piloto redibujado.** Sin esto no hay
   entrada. Barato: es una decisión y una plantilla `.dwt`, no código.
2. **`eFileType` de SAFE.** Una tarde de buscar en la ayuda de la OAPI o de
   prueba y error. Desbloquea toda la rama C4.
3. **Extractor DXF → JSON** contra el DWG piloto. Acá se descubre qué tan
   limpia está la convención en la práctica.
4. **Exponer las 4 herramientas de ETABS ya identificadas** (`SetModifiers`,
   `SourceMass`, `SetPanelZone`, `DesignShearWall`). Trabajo mecánico, firmas
   ya conocidas.
5. **Envolver `motor-fea` en un MCP** (o generar `.DL` para PROGRAMA-LOSA,
   según la opción que elijas en C5).
6. **Dynamo de ida** (JSON → Revit), reutilizando el patrón de Torre Evolution.
7. **Dynamo de vuelta** (detallado), nivel A primero.
8. **Schedules → presupuesto.**

Los pasos 1–2 son independientes entre sí y pueden ir en paralelo. El 4 no
bloquea a nadie y puede hacerse en cualquier hueco.

## Lo que esta arquitectura no resuelve

- **Autonomía total.** El SOP tiene cuatro puntos de juicio de ingeniero que
  no conviene automatizar: aprobación de la configuración estructural (paso
  5.5), decisión de aumentar acero vs. aumentar sección cuando falla el joint
  (paso 26), ampliar zapata cuando no cumple presión (3.12), y engrosar
  cuando falla punzonamiento (3.13). La arquitectura debe *presentar* esas
  decisiones con los datos listos, no tomarlas.
- **Modelos sucios.** Si el DWG no respeta la convención, el extractor falla
  ruidosamente — eso es deseable. Lo que no puede hacer es adivinar.
- **Validación del `motor-fea`.** Que el motor exista no significa que esté
  verificado contra casos de referencia. Si va a producir armado que se
  construye, necesita su propia campaña de validación, separada de esto.
