# Huecos de ETABS y SAFE — especificación para implementar

Fecha: 2026-08-10. Firmas sondeadas en vivo contra ETABS 23.3.0 / SAFE 23.3.0,
OAPI 2.016, con `describe_oapi`. Todo lo que aparece acá como firma es
**transcripción literal del typelib de esta instalación**, no conjetura.

Este documento existe para que la implementación no tenga que adivinar nada.
Cada hueco trae: qué paso del SOP cubre, la firma exacta, y las trampas
conocidas.

---

## Hallazgo que reordena las prioridades

La bitácora del RESTAURANTE registra como *"el hueco funcional más grande del
servidor hoy"* que las tablas de diseño no se leen: `Concrete Beam Design
Summary`, `Design Forces - Columns` y `Joint Design Reactions` fallan con
`ret=1`, y la conclusión fue que **`run_concrete_design` corre a ciegas**.

Eso es cierto **por la vía de tablas**. Por la vía de métodos directos, no:
`SapModel.DesignConcrete` expone cuatro lectores de resultados que devuelven
exactamente lo que hacía falta, incluyendo área requerida, mínima y provista.
El diagnóstico anterior probó una sola puerta.

Consecuencia práctica: el hueco que bloqueaba el detallado en Revit (C6 de la
arquitectura) **no requiere desarrollo nuevo de ETABS, solo envolver métodos
que ya existen**. Es el primer ítem de la lista.

---

# ETABS — huecos

## H-1. Lectores de diseño de concreto  ⬅ prioridad máxima

Cubre: paso 26 del SOP (chequear columnas por PMM, joint shear y refuerzo
longitudinal) y todo el insumo de acero para C6.

Namespace: `SapModel.DesignConcrete`. Los cuatro métodos aceptan `Name` =
nombre de frame o de grupo, e `ItemType` opcional (0 = objeto, 1 = grupo,
2 = selección). Pasar `Name=""` con `ItemType=2` para toda la selección.

### `get_concrete_design_beam` → `GetSummaryResultsBeam_2`

Usar la variante `_2`, no la original: la `_2` agrega `AreaReq`, `AreaMin` y
`AreaProvided`, que es la diferencia entre saber el acero y saber si cumple.

```
GetSummaryResultsBeam_2(Name, ItemType=0) -> (
  NumberItems, FrameName[], Location[],
  TopCombo[], TopArea[], TopAreaReq[], TopAreaMin[], TopAreaProvided[],
  BotCombo[], BotArea[], BotAreaReq[], BotAreaMin[], BotAreaProvided[],
  VMajorCombo[], VMajorArea[], VmajorAreaReq[], VmajorAreaMin[],
  VmajorAreaProvided[],
  TLCombo[], TLArea[], TTCombo[], TTArea[],
  ErrorSummary[], WarningSummary[], ret)
```

`TL`/`TT` son torsión longitudinal y transversal. `ErrorSummary` y
`WarningSummary` vienen por ítem: hay que devolverlos, no descartarlos —
son la forma en que ETABS reporta que una sección no cumple.

### `get_concrete_design_column` → `GetSummaryResultsColumn`

```
GetSummaryResultsColumn(Name, ItemType=0) -> (
  NumberItems, FrameName[], MyOption[], Location[],
  PMMCombo[], PMMArea[], PMMRatio[],
  VMajorCombo[], AVMajor[], VMinorCombo[], AVMinor[],
  ErrorSummary[], WarningSummary[], ret)
```

`PMMRatio` es el ratio de interacción P-M-M. La regla del SOP *"si falla en
flexión en más de un 5%, aumentar el acero"* se codifica como
`PMMRatio > 1.05`.

### `get_concrete_design_joint` → `GetSummaryResultsJoint`

```
GetSummaryResultsJoint(Name, ItemType=0) -> (
  NumberItems, FrameName[],
  LCJSRatioMajor[], JSRatioMajor[], LCJSRatioMinor[], JSRatioMinor[],
  LCBCCRatioMajor[], BCCRatioMajor[], LCBCCRatioMinor[], BCCRatioMinor[],
  ErrorSummary[], WarningSummary[], ret)
```

`JSRatio` = joint shear capacity ratio, exactamente el chequeo del paso 26.
`BCCRatio` = beam/column capacity ratio (columna fuerte-viga débil).

Regla del SOP a codificar: *"las columnas de techo que fallan por joint,
omitir el comentario porque al no tener continuidad la rigidez es menor"* —
o sea, filtrar por nivel superior antes de reportar como falla.

## H-2. Modificadores de rigidez

Cubre: paso 5 del SOP (reducir inercias).

```
PropFrame.SetModifiers(Name, Value[8]) -> (Value, ret)
PropArea.SetModifiers(Name, Value[10]) -> (Value, ret)
```

Ambas reciben un `SAFEARRAY(double)`. **`Value` es `[in,out]`**: comtypes lo
devuelve además de `ret`, así que el desempaquetado es de 2 valores, no 1.
Es la misma clase de error que produjo los tres bugs de tablas del SAFE MCP.

Orden de los 8 modificadores de frame (documentado por CSI, estable en la
línea ETABS/SAP2000): área, corte 2, corte 3, torsión, momento 2, momento 3,
masa, peso. Los 10 de área: f11, f22, f12, m11, m22, m12, v13, v23, masa,
peso.

Valores del SOP: columnas y muros de HA → momento 2 y 3 (o m11/m22) = 0.80;
vigas → 0.60; muros de mampostería → 0.60.

Conviene exponer una herramienta de alto nivel además de la cruda —
`set_stiffness_modifiers(section, i22, i33)` que rellene el resto en 1.0 —
porque pasar un array de 8 posiciones a mano es una fuente de error silencioso.

## H-3. Masa modal

Cubre: paso 8 del SOP.

Namespace real: **`SapModel.SourceMass`** (la interfaz interna se llama
`cMassSource`; el atributo bajo `SapModel` es `SourceMass`).

```
SourceMass.SetMassSource(Name, MassFromElements, MassFromMasses,
                         MassFromLoads, IsDefault, NumberLoads,
                         LoadPat[], SF[]) -> (LoadPat, SF, ret)
```

El SOP exige seleccionar **solamente** patrones de carga especificados: eso es
`MassFromElements=False, MassFromMasses=False, MassFromLoads=True`. Carga
muerta con SF 1; carga viva según Tabla A-2 del R-001 (los coeficientes Øi:
0.15 residencial, 0.20 oficinas/hoteles, 0.25 escuelas y almacenaje, 0.30
hospitales, 0.10 techos).

`LoadPat` y `SF` son `[in,out]` — mismo cuidado que en H-2.

No hay opción de "include vertical mass" en esta firma, así que el "NO
seleccionar include Vertical Mass" del SOP se cumple por omisión.

## H-4. Panel zone

Cubre: paso 19 del SOP.

```
PointObj.SetPanelZone(Name, PropType, Thickness, K1, K2, LinkProp,
                      Connectivity, LocalAxisFrom, LocalAxisAngle,
                      ItemType=0) -> ret
```

Complementarios: `GetPanelZone`, `DeletePanelZone`, `CountPanelZone`.

`PropType` es un enum no expuesto por nombre en el typelib. El SOP solo dice
"seleccionar Panel Zone" sin especificar tipo, lo que sugiere el valor por
defecto. Verificar creando uno por interfaz y leyéndolo con `GetPanelZone`
antes de fijar el valor en código.

## H-5. Diseño de muros de corte

Cubre: paso 27 del SOP.

Namespace: `SapModel.DesignShearWall`. Los lectores no reciben argumentos —
devuelven el modelo entero, ya filtrado por lo que tenga pier labels.

```
GetPierSummaryResults() -> (
  Story[], PierLabel[], Station[], DesignType[], PierSecType[],
  EdgeBar[], EndBar[], BarSpacing[], ReinfPercent[], CurrPercent[],
  DCRatio[], PierLeg[], LegX1[], LegY1[], LegX2[], LegY2[],
  EdgeLeft[], EdgeRight[], AsLeft[], AsRight[], ShearAv[],
  StressCompLeft[], StressCompRight[], StressLimitLeft[], StressLimitRight[],
  CDepthLeft[], CLimitLeft[], CDepthRight[], CLimitRight[],
  InelasticRotDemand[], InelasticRotCapacity[],
  NormCompStress[], NormCompStressLimit[], CDepth[],
  BZoneL[], BZoneR[], BZoneLength[], WarnMsg[], ErrMsg[], ret)

GetSpandrelSummaryResults() -> (
  Story[], Spandrel[], Station[], TopRebar[], TopRebarRatio[], TopRebarCombo[],
  MuTop[], BotRebar[], BotRebarRatio[], BotRebarCombo[], MuBot[],
  AVert[], AHorz[], ShearCombo[], Vu[], ADiag[], ShearDiagCombo[], VuDiag[],
  WarnMsg[], ErrMsg[], ret)

GetRebar() -> (AreaObjName[], StoryName[], PierLabel[], StationLocation[],
  LegID[], LeftX1[], LeftY1[], RightX2[], RightY2[], Length[], Thickness[],
  Fc[], FY[], fys[], Flexural[], ShearAndConfinement[], ret)
```

`DCRatio` es demanda/capacidad. `BZoneLength` da la longitud de zona de borde
confinada — dato de detallado que hoy se lee en pantalla.

Faltan por sondear los métodos de *escritura* (asignar pier label, definir
sección de pier para chequeo). El namespace tiene 6 métodos y 5 son `Get`;
el sexto hay que identificarlo. La asignación de pier label vive en
`AreaObj`, no acá.

## H-6. Bugs conocidos del servidor `fea` — arreglar antes de escalar

Los tres primeros están documentados en la bitácora del RESTAURANTE con
evidencia de runtime. No son hipótesis.

| # | Síntoma | Impacto |
|---|---|---|
| **E-024** | `set_table_data` devuelve *"6 fila(s) escritas"* sobre `Load Pattern Definitions` y la relectura muestra que **no aplicó nada**. Otras tres tablas sí aplicaron. | **Falso positivo de escritura.** Es el bug más peligroso del servidor: no distingue éxito de fracaso silencioso. Toda automatización que escriba por tabla necesita relectura de verificación hasta que esto se arregle. |
| — | `delete_definition` no borra patrones de carga (`ret=1` en `Dead` y `Live`) | Queda un `Dead` residual con `SelfWtMult=1` junto al patrón propio. Una combinación futura que lo tome **duplica la masa**. |
| — | `add_load_pattern` no es idempotente: falla si el nombre existe | Rompe cualquier corrida repetida sobre el mismo modelo. |
| nuevo | Las tablas de diseño no se leen (`ret=1`) | Mitigado por H-1: usar los métodos directos en vez de tablas. La tabla de columnas devuelve solo la lista de campos, sin filas. |

Patrón que explica al menos tres de los bugs de tablas encontrados hoy en
SAFE y probablemente E-024: **desempaquetar mal la tupla de comtypes**. Los
parámetros `[in,out]` se devuelven junto al `ret`, y la cantidad cambia entre
métodos. Regla: contar los `py-> (...)` que reporta `describe_oapi` antes de
escribir el desempaquetado, siempre.

---

# SAFE — huecos

## S-1. `eFileType` para F2K y DXF  ⬅ bloqueo duro

`cFile` **no tiene** método dedicado a DXF ni a F2K. Solo genéricos:

```
File.ImportFile(FileName, FileType, ImportType) -> ret
File.ExportFile(FileName, FileType) -> ret
```

`FileType` es un entero del enum `eFileType`. Los enums COM no traen nombres
de miembro en el typelib generado por comtypes, así que **la introspección no
lo puede resolver**. Dos vías:

- Ayuda oficial de la OAPI: dentro de SAFE, `Help > CSI OAPI Documentation`,
  buscar `eFileType`. También suele venir como `.chm` en la carpeta de
  instalación.
- Prueba y error: exportar con valores 0..20 a rutas distintas y ver cuál
  produce un archivo con la extensión esperada. Barato y concluyente.

Sin esto, el paso ETABS→SAFE y el export a DXF siguen siendo manuales. Es
media hora de trabajo que desbloquea toda una rama.

## S-2. Punzonamiento y presión de contacto

Cubre: pasos 3.12 y 3.13 del SOP.

`DesignConcreteSlab` tiene solo 8 métodos y **ninguno de punzonamiento** —
sondeado, no supuesto. La vía es por tablas: `list_tables` sobre el modelo con
diseño corrido, identificar las claves reales, y leer con `get_table_data`
(ya corregido y funcional en el SAFE MCP).

Verificaciones del SOP a codificar una vez leídas:
- Presión: combo 2 contra σadm; envolvente contra ¾·σadm. Si no cumple,
  ampliar el área de la zapata.
- Punzonamiento: ratio > 1 exige engrosar el espesor.

Ambas son decisiones de ingeniero. La herramienta reporta, no corrige.

## S-3. Franjas de diseño (design strips)

Cubre: paso 3.15 del SOP.

`DesignConcreteSlab` expone `DesignStrip` como subobjeto — falta sondearlo.
Nota: el SOP (pág. 47) muestra que esta versión también soporta diseño
*Finite Element Based*, que **no requiere franjas**. Antes de construir
herramientas de franjas conviene decidir cuál de los dos métodos va a ser el
estándar de la firma, porque son caminos distintos y no complementarios.

## S-4. Confirmado, sin trabajo pendiente

Sondeado hoy y ya implementado correctamente en el servidor:

```
PropAreaSpring.SetAreaSpringProp(Name, U1, U2, U3, NonlinearOption3,
    SpringOption=1, SoilProfile='', EndLengthRatio=0.0, Period=0.0,
    Color=0, Notes='', iGUID='') -> ret
AreaObj.SetSpringAssignment(Name, SpringProp, ItemType=0) -> ret
DesignConcreteSlab.StartSlabDesign() -> ret
DesignConcreteSlab.GetSummaryResultsFlexureAndShear(...)
```

Queda una sola incógnita menor: el orden del enum `NonlinearOption3`. Se
asumió `0=None, 1=TensionOnly, 2=CompressionOnly, 3=ElastoPlastic` por el
orden de los radio-botones del diálogo. Verificable en un minuto: definir un
resorte por interfaz con "Compression Only" y leerlo con `GetAreaSpringProp`.

---

# Estado de implementación — 2026-08-10, misma sesión

| Hueco | Estado | Herramientas nuevas |
|---|---|---|
| H-1 lectores de diseño | **PROBADO contra diseño corrido 2026-08-10** (TORRE A, reconexión tras E-035): `get_concrete_design_column` (764 estaciones, 252 columnas, PMM máx sin superar 1.05) y `get_concrete_design_joint` (201 juntas, JS máx sin superar 1) funcionan bien. `get_concrete_design_beam` fallaba con `len(int)`: **la llamada pasaba 22 arrays de los 23 de la firma** (E-037, corregido 2026-08-10 en `Etabs.py`; verificar tras reiniciar los servidores). Vía alterna que quedó probada: tabla `Concrete Beam Design Summary - ACI 318-19` (12287 filas, 134 vigas, 0 errores/avisos). Mejoras del mismo día: `get_table_data` paginado (`offset`/`max_rows`, fea y safe) y `get_analysis_status` nuevo en ambos servidores (Analyze.GetCaseStatus, sondeo post-timeout, E-035) | `get_concrete_design_beam` (usa `_2`), `get_concrete_design_column` (marca PMM>1.05), `get_concrete_design_joint` (marca falla de joint, filtro de nivel de techo) |
| H-2 modificadores | **Implementado** | `set_frame_modifiers`, `set_area_modifiers` |
| H-3 masa modal | **Implementado** | `set_mass_source` (SourceMass, solo patrones especificados) |
| H-4 panel zone | **Implementado** (PropType=0 sin confirmar contra la interfaz) | `set_panel_zone` |
| H-5 muros | **Implementado** | `set_pier_label` (AreaObj.SetPier, sondeado esta sesión), `get_shearwall_design`, `get_shearwall_rebar` |
| H-6 bugs | **Pendiente** — E-024 requiere sesión de depuración propia | — |
| S-1 eFileType | **CERRADO 2026-08-10 (DXF en negativo)** | Identificado empíricamente: **1 = SAFE .f2k** (verificado leyendo el archivo producido: formato TABLE de CSI), 2 = Excel, 3 = Access, 4 = tablas a texto, 5 = XML. El orden calca el menú File > Export. `import_file` ya tiene 1 como default. **DXF: NO EXISTE por esta vía.** Re-sondeado 6–20 con modelo poblado, analizado y diseñado (TORRE A): ret=0 sin archivo en todos. `cFile` no tiene método DXF (13 métodos sondeados). ret=0 fuera de rango es falso éxito (E-036). SAFE→AutoCAD queda manual o por interfaz. |
| S-2 punzonamiento/presión | **Probado en vivo 2026-08-10** (TORRE A: 13 puntos, 1 falla ratio 1.029). Presión: la tabla nodal (1.38M filas) agota el timeout MCP — leerla vía `export_file` tipo 4 y parsear el texto (E-035) | `get_punching_check`, `get_soil_pressure` |
| S-3 franjas | **Probados en vivo 2026-08-10** (22 franjas, 186 posiciones OK, 396 estaciones) | `get_design_strips`, `get_slab_design_detail`, `get_span_definitions`. Hallazgo de la sonda: `cDesignStrip` **no tiene método de creación** (solo ChangeName/Delete/Get) — las franjas se dibujan en la interfaz o vía tablas. Refuerza la opción Finite Element Based como estándar. |

Hallazgo adicional de la sonda de `DesignConcreteSlab`: expone los
subnamespaces `ACI318_14`, `ACI318_19` y `ACI318_25` (preferencias de diseño
por código, incluida una versión más nueva que la que usa el PROGRAMA-LOSA).
Sin sondear todavía; ahí viven los overwrites de recubrimiento y código del
paso 3.7 del SOP.

Actualización 2026-08-10 (tarde): tanto SAFE como ETABS ya corrieron contra el
diseño real de TORRE A (ver bitácora en BRAIN/03_APPS). Columnas y joints OK
por el método directo; vigas requiere la vía de tabla por el bug E-037. Sismo
queda parcial: 90% de masa participativa confirmado en modo 24/80, falta sondear
espectro de respuesta y cortante dinámico/estático. La prueba de fuego es correr el ciclo completo sobre
un modelo con diseño: `run_concrete_design` → los tres lectores en ETABS;
`run_slab_design` → los lectores de SAFE. Reiniciar Claude Desktop desde la
bandeja para que los servidores recarguen el código nuevo.

# Orden sugerido

| # | Ítem | Desbloquea | Costo |
|---|---|---|---|
| 1 | H-1 lectores de diseño | El detallado en Revit (C6) y la verificación del cálculo | Bajo — firmas ya transcritas |
| 2 | H-6 bug E-024 | Confiabilidad de toda escritura por tabla | Medio — hay que entender por qué una tabla aplica y otra no |
| 3 | S-1 `eFileType` | La rama ETABS→SAFE completa | Muy bajo — es buscar un número |
| 4 | H-2, H-3, H-4 | Pasos 5, 8 y 19 del SOP | Bajo — mecánico |
| 5 | H-5 muros | Paso 27 | Medio — falta sondear la escritura |
| 6 | S-2 punzonamiento | Pasos 3.12-3.13 | Bajo, una vez identificadas las tablas |
| 7 | S-3 franjas | Paso 3.15 | Requiere decidir método primero |

Los ítems 1, 3 y 4 son independientes entre sí y pueden hacerse en paralelo.

# Regla de implementación

Antes de escribir el desempaquetado de cualquier llamada, correr
`describe_oapi` sobre su namespace y **contar los valores del `py-> (...)`**.
Los tres bugs corregidos hoy en el SAFE MCP y probablemente E-024 son todos
la misma causa: asumir cuántos valores devuelve comtypes en vez de leerlo.
