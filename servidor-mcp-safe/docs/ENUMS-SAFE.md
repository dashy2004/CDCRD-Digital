# ENUMS SAFE 23 — corte 2026-09-25 [codex]

Confirmación viva: `docs/OAPI-SAFE-real.md` §7.1 y buzón `claude-212`. Los valores de eSlabType 0–6, ShellThin/Thick y NonlinearOption3 0–2 fueron verificados en vivo por Claude el 2026-09-25. Las correcciones v0.2.1 ya estaban en el árbol; Codex las conserva y agrega tests de regresión. Los demás miembros siguientes son evidencia de typelib [T], no prueba de implementación SAFE.

## Origen estático (sin cargar COM)

Wrapper **W**: `C:\Users\emilg\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\comtypes\gen\_2406CB05_79B9_49C2_8684_CC7A67F5B12E_0_1_0.py`.
SHA-256 W: `d53ead5e47d40843e971a8963fa30812a9b05358c47b5bea0aac17fad1b04ea2`.
W:16 declara `C:\Program Files\Computers and Structures\SAFE 23\NativeAPI\x64\SAFEv1.tlb`. El alias `comtypes/gen/SAFEv1.py` importa W. Las líneas siguientes son del archivo generado local, no de una copia ETABS.

| Tipo | Miembro | Valor | Origen |
|---|---|---:|---|
| `eFileTypeIO` | `TextFile` | 1 | W:33 |
| `eFileTypeIO` | `DBTablesExcel` | 2 | W:34 |
| `eFileTypeIO` | `DBTablesAccess` | 3 | W:35 |
| `eFileTypeIO` | `DBTablesText` | 4 | W:36 |
| `eFileTypeIO` | `DBTablesXML` | 5 | W:37 |
| `eItemType` | `Objects` | 0 | W:41 |
| `eItemType` | `Group` | 1 | W:42 |
| `eItemType` | `SelectedObjects` | 2 | W:43 |
| `eShellType` | `ShellThin` | 1 | W:71 |
| `eShellType` | `ShellThick` | 2 | W:72 |
| `eShellType` | `Membrane` | 3 | W:73 |
| `eShellType` | `PlateThin_DO_NOT_USE` | 4 | W:74 |
| `eShellType` | `PlateThick_DO_NOT_USE` | 5 | W:75 |
| `eShellType` | `Layered` | 6 | W:76 |
| `eSlabType` | `Slab` | 0 | W:80 |
| `eSlabType` | `Drop` | 1 | W:81 |
| `eSlabType` | `Stiff_DO_NOT_USE` | 2 | W:82 |
| `eSlabType` | `Ribbed` | 3 | W:83 |
| `eSlabType` | `Waffle` | 4 | W:84 |
| `eSlabType` | `Mat` | 5 | W:85 |
| `eSlabType` | `Footing` | 6 | W:86 |

`Stiff_DO_NOT_USE=2` es el nombre del wrapper compartido: Claude comprobó que SAFE lo interpreta como **Stiff**. `Layered=6`; 4 y 5 son PlateThin/PlateThick_DO_NOT_USE, no Layered. No usar esos tipos como si estuvieran verificados para SAFE.

## Tipos solicitados que el wrapper no declara

| Nombre solicitado | Lo que realmente declara W | Dominio confirmado | Fuente |
|---|---|---|---|
| `eAreaSpringNonlinearOption` | No existe como enum; `NonlinearOption3` es `c_int` | 0 None/lineal; 1 Compression Only; 2 Tension Only [H] | W:22042 (setter), W:22016 (getter); OAPI-SAFE-real.md §7.1; claude-212 |
| `eImportType` | No existe como enum; `ImportType` es arreglo de `c_int` | 0, 1, 2, 3, documentados abajo [T] | W:24579; CHM ETABS 23, GetAvailableTables |

No se encontró ninguno de esos dos símbolos en los wrappers disponibles de `comtypes/gen/`. Ausencia de símbolo no implica ausencia del parámetro. No confundir `ImportType[]` de tablas con el argumento `Type` de `File.ImportFile`: son contratos diferentes.

**GetAreaSpringProp no valida el comportamiento del resorte en esta instalación:** Claude obtuvo NonlinearOption3=0 para todos los casos. Releer `Spring Property Definitions - Area Springs`, columna `NonlinOpt3`.

## ImportType de tablas — CHM ETABS 23 leído localmente

Archivo: `C:\Program Files\Computers and Structures\ETABS 23\CSI API ETABS v1.chm`; SHA-256 `0108deeb19fd054ea03a9be89244dac5c8f5995cc44865eaa508b17f675b9d88`.
Tema interno: `html/06be9356-26a5-d81b-7ddc-d758bbc000cc.htm`, título `cDatabaseTables.GetAvailableTables Method` (ETABSv1 2.16.0.0). Extraído con 7-Zip sin ejecutar ETABS. El CHM SAFE extraído por Claude (`CSI-API-SAFE-v1-chm-html.zip`, `chm/html/76164da4-beef-282b-6f92-dea24c2455be.htm`) coincide.

| Valor | Interpretación |
|---:|---|
| 0 | No importable. |
| 1 | Importable, sin edición interactiva. |
| 2 | Permite edición interactiva con modelo desbloqueado. |
| 3 | Permite edición interactiva con modelo bloqueado o desbloqueado. |

`list_tables` conserva el entero y agrega su significado. Las tres tools nuevas exigen 2 o 3; para 2 consultan GetModelIsLocked. No desbloquean el modelo ni invalidan resultados automáticamente.

## Dominios de texto: pendientes de corrida viva

XML: `C:\Program Files\Computers and Structures\SAFE 23\Table and Field Keys.xml`; SHA-256 `e8490bc0c17bca64763c2e2288e6a89b2e6ae58e4de20d07a8a678ddad8f2dc2`.
El XML declara claves/nombres (`tkey`, `tname`, `fkey`, `fname`) y versión; no declara listas de valores permitidos. Además contiene columnas de punzonamiento ausentes del esquema vivo §6.1: no se incorporaron.

- Confirmar dominios exactos de CheckPunchingShear, LocationType, Perimeter, EffDepthType, OpeningDef y RebarType mediante lectura/escritura en copia. Valores observados: Program Determined / Auto / Auto / Auto / Auto / None; no se convierten en una lista exhaustiva inventada.
- Confirmar AutoWiden=Yes; No y Layer=A/B aparecen en el esquema vivo. Si Yes recalcula los anchos, la tool informa discrepancia y exige inspección, sin repetir la escritura.
- NumSegs es de solo lectura según GetAllFieldsInTable (claude-212). Se conserva para verificar, pero se excluye de SetTableForEditingArray. El resto de campos se envía según IsImportable leído en cada llamada.
- set_strip_widths admite una fila/un segmento por nombre. Para varios segmentos falta definir el selector y su semántica; se rechaza antes de escribir.

## Advertencia sobre v0.1.0

Los modelos donde se usaron `define_slab_section(..., slab_type="Footing")` o `define_soil_spring(..., compression_only=True)` con v0.1.0 deben revisarse: el código enviaba **Ribbed=3** y **Tension Only=2**. Cambiar el servidor no corrige modelos ya guardados. Claude/ingeniero debe identificar las asignaciones y verificar cualquier corrección sobre copia. Codex no modificó modelos.

## Pilotes (claude, 2026-11-02): enums y firmas usadas, evidencia de typelib [T]

Mismo wrapper W. Valores leídos del archivo generado, no de corrida viva.

| Enum / método | Valor o firma py-> | Fuente |
|---|---|---|
| `eFramePropType_Circle` | 9 (I=1, Channel=2, T=3, Angle=4, DblAngle=5, Box=6, Pipe=7, Rectangular=8, Circle=9, General=10) | W:231-262 |
| `eItemTypeElm_ObjectElm` | 0 (Element=1, GroupElm=2, SelectionElm=3) | W:130-135 |
| `FrameObj.GetAllFrames()` | (n, Name[], PropName[], StoryName[], P1[], P2[], X1[], Y1[], Z1[], X2[], Y2[], Z2[], Angle[], Offset1X..Offset2Z[6], CardinalPoint[], ret); `CSys` opcional "Global" | W:20420 |
| `PropFrame.GetNameList(n, names, PropType=0)` | (n, names, ret); PropType opcional | W:7491 |
| `PropFrame.GetTypeOAPI(Name)` | (PropType, ret) | W:7643 |
| `PropFrame.GetCircle(Name)` | (FileName, MatProp, T3, Color, notes, GUID, ret); T3 = diámetro | W:7361 |
| `Results.JointReact(Name, ItemTypeElm)` | (n, Obj, Elm, LoadCase, StepType, StepNum, F1, F2, F3, M1, M2, M3, ret) | W:21399 |
| `Results.FrameForce(Name, ItemTypeElm)` | (n, Obj, ObjSta, Elm, ElmSta, LoadCase, StepType, StepNum, P, V2, V3, T, M2, M3, ret) | W:21262 |
| `Results.Setup.DeselectAllCasesAndCombosForOutput()` / `SetComboSelectedForOutput(Name, Selected=True)` / `SetCaseSelectedForOutput(Name, Selected=True)` | (ret) | W:1855-1960 |
| `RespCombo.GetNameList()` (cCombo) | (n, names, ret) | W:17713+ |

Convención de signo de `JointReact.F3` (positivo = compresión en el pilote si la reacción apunta hacia arriba) y de `FrameForce.P` (negativo = compresión, convención CSI) pendientes de confirmar en corrida viva con un caso gravitatorio.

**Corrida viva 2026-11-02 [claude, Fable local], SAFE 23.3.0:** `FrameObj.GetAllFrames`, `PropFrame.GetNameList(0,[],9)` (filtra por tipo: con modelo en blanco devuelve `(0, [])` ret=0; con modelo real solo la circular), `GetTypeOAPI` (=9) y `GetCircle` (T3 = diámetro) pasan a **[H]**; `eFramePropType_Circle = 9` confirmado. Con el análisis corrido (autorizado por Emil el mismo día): `Results.Setup.DeselectAllCasesAndCombosForOutput`, `SetCaseSelectedForOutput`, `SetComboSelectedForOutput`, `Results.JointReact(Name, 0)`, `Results.FrameForce(Name, 0)`, `RespCombo.GetNameList` y `Analyze.GetCaseStatus` pasan a **[H]**. Signo confirmado con el caso Dead: `JointReact.F3 > 0` = compresión en el pilote y `FrameForce.P < 0` = compresión (misma cifra por las dos vías); `StepType` "Single Value" en casos y "Max"/"Min" en combos. Detalle en `PRUEBA-VIVA-PILOTES.md`.

Para `export_pile_check_xlsx` (mismo día, [H]): `RespCombo.GetCaseList(Name)` py-> (n, CNameType[] 0=caso/1=combo, CName[], SF[], ret) y `LoadCases.GetTypeOAPI_1(Name)` py-> (CaseType, SubType, DesignType, DesignTypeOption, Auto, ret). `eLoadCaseType`: 1 LinearStatic, 2 NonlinearStatic, 3 Modal, 4 ResponseSpectrum, 5 LinearHistory, 6 NonlinearHistory, 7 LinearDynamic, 8 NonlinearDynamic, 12 PSD, 13 LinearStaticMultiStep (W:772-786). `eLoadPatternType`: 1 Dead, 2 SuperDead, 3 Live, 4 ReduceLive, 5 Quake, 6 Wind, 7 Snow, 8 Other (W:166-180). Observado en vivo: los casos `Qx(1/2)`… son CaseType 1 con DesignType 5 (sismo estático equivalente); `~LLRF` es DesignType 8 con Auto 5.

Para `trial_pile_changes` (mismo día, [H] en copia): `FrameObj.Delete(Name, ItemType=0)`, `FrameObj.AddByCoord(XI, YI, ZI, XJ, YJ, ZJ, Name, PropName, UserName, CSys)` py-> (Name, ret), `PointObj.GetRestraint(Name)` py-> (Value[6], ret), `PointObj.SetRestraint(Name, Value[6], ItemType)`, `PointObj.GetSpring` / `GetSpringAssignment` y `FrameObj.GetSpringAssignment`: **devuelven ret=1 cuando no hay asignación** (no es error). `Analyze.RunAnalysis` **guarda el modelo activo en disco** antes de analizar.
