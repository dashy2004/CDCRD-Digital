# OAPI de SAFE 23 — lo real, no lo conjeturado

Fuente: sesión viva de Claude 2026-09-25 contra SAFE 23.3.0 (OAPI 2.016, ProgID `CSI.SAFE.API.ETABSObject`),
`describe_oapi` del servidor `servidor-mcp-safe`, más el CHM oficial `C:\Program Files\Computers and Structures\SAFE 23\CSI API SAFE v1.chm`
(extraído en `docs\CSI-API-SAFE-v1-chm-html.zip`, TOC en `docs\CSI-API-SAFE-v1-TOC.md`).

Firma: [claude] 2026-09-25. Append-only; Codex agrega abajo con firma `[codex]`.

## 1. Hallazgo central: dos capas distintas

**Capa A — API documentada por CSI para SAFE (CHM, 192 entradas).** Es pequeña. Solo cubre:

| Interfaz | Métodos documentados |
|---|---|
| `cSapModel` | GetDatabaseUnits/_2, GetMergeTol, GetModelFilename, GetModelFilepath, GetModelIsLocked, GetPresentCoordSystem, GetPresentUnits/_2, GetProgramInfo, GetProjectInfo, GetVersion, InitializeNewModel, SetMergeTol, SetModelIsLocked, SetPresentUnits/_2, SetProjectInfo, TreeSuspendUpdateData / TreeResumeUpdateData / TreeIsUpdateSuspended |
| `cSapModel` propiedades | Analyze, DatabaseTables, DesignCompositeBeam, DesignConcrete, DesignSteel, File, Results, View |
| `cAnalyze` | CreateAnalysisModel, DeleteResults, RunAnalysis, Get/SetActiveDOF, GetCaseStatus, Get/SetRunCaseFlag, Get/SetSolverOption(_1/_2/_3), Get/SetDesignResponseOption, MergeAnalysisResults, ModifyUndeformedGeometry(+ModeShape) |
| `cDatabaseTables` | GetAvailableTables, GetAllTables, GetAllFieldsInTable, GetTableForDisplayArray / CSVFile / CSVString / XMLString, **GetTableForEditingArray / CSVFile / CSVString, SetTableForEditingArray / CSVFile / CSVString, ApplyEditedTables, CancelTableEditing**, Get/SetLoadCasesSelectedForDisplay, Get/SetLoadCombinationsSelectedForDisplay, Get/SetLoadPatternsSelectedForDisplay, Get/SetOutputOptionsForDisplay, GetObsoleteTableKeyList, ShowTablesInExcel |
| `cDesignConcreteSlab` | **StartSlabDesign** (único documentado) |
| `cDesignConcrete` / `cDesignSteel` / `cDesignCompositeBeam` | StartDesign, DeleteResults |
| `cFile` | OpenFile, Save, NewBlank, NewGridOnly, NewSteelDeck, GetFilePath, **ImportFile(FileName, eFileTypeIO, Type)**, **ExportFile(FileName, eFileTypeIO)** |
| `cAnalysisResults` + `Setup` | (solo Setup documentado: DeselectAllCasesAndCombosForOutput, Set/GetCaseSelectedForOutput, Set/GetComboSelectedForOutput, opciones NLStatic/MultiStep/ModeShape/etc.) |
| `cSelect` | All, ClearSelection, GetSelected, Group, InvertSelection, PreviousSelection |
| `cView` | RefreshView, RefreshWindow |
| `cOAPI` / `cHelper` | ApplicationStart/Exit, Hide/Unhide/Visible, SapModel, CreateObject/GetObject/CreateObjectProgID/GetObjectProcess |
| Enums | `eFileTypeIO` = TextFile 1, DBTablesExcel 2, DBTablesAccess 3, DBTablesText 4, DBTablesXML 5. `eUnits`, `eForce`, `eLength`, `eTemperature`, `eItemType`, `eReturnCode` |

Consecuencia: **CSI no documenta para SAFE ningún método de objeto (AreaObj, PointObj, PropArea…), ni de edición geométrica, ni de punzonamiento, ni de franjas.** La vía oficial para todo eso es `DatabaseTables` (Interactive Database Editing) o el archivo `.F2K`/`.$fb`.

Breaking change v22: la API es .NET Standard 2.0 AnyCPU; el Remote API (CreateObjectHost*) está deshabilitado; late binding VBA puede fallar. Conectar por `cHelper.GetObject("CSI.SAFE.API.ETABSObject")` como ya hace `Safe.py`.

**Capa B — lo que expone el typelib compartido `CSiAPIv1.dll` (103 miembros en SapModel).** Es el mismo typelib de ETABS. `describe_oapi` lo lista completo, pero **que aparezca no significa que SAFE lo implemente**: muchos son de ETABS/SAP2000 (Story, Tower, PierLabel, BridgeObj, DesignShearWall…). Cada método de esta capa se considera "conjetura" hasta que una llamada en vivo devuelva `ret = 0` y el efecto se verifique releyendo el modelo.

Miembros de SapModel expuestos (typelib): Analyze, AreaElm, AreaObj, Bridge*, CableObj, ConstraintDef, CoordSys, DatabaseTables, DesignAluminum, DesignColdFormed, DesignCompositeBeam, DesignCompositeColumn, DesignConcrete, DesignConcreteShell, **DesignConcreteSlab**, DesignResults, DesignShearWall, DesignSteel, Detailing, Diaphragm, **EditArea, EditFrame, EditGeneral, EditPoint**, EditSolid, ExternalAnalysisResults, File, FrameObj, Func, GDispl, GenRefLine, GridSys, GroupDef, LineElm, LinkElm, LinkObj, LoadCases, LoadPatterns, NamedAssign, NamedDisplay, NamedSet, Options, PatternDef, PierLabel, PlaneElm, PointElm, **PointObj, PropArea, PropAreaSpring**, PropCable, PropFrame, PropLineSpring, PropLink, PropMaterial, PropPointSpring, PropRebar, PropSolid, PropTendon, RespCombo, Results, Scheduler, SectCut, SelectObj, SolidElm, SolidObj, SourceMass, SpandrelLabel, Story, TendonObj, Tower, View. Métodos directos: GetDatabaseUnits(_2), GetMergeTol, GetModelFilename, GetModelFilepath, GetModelIsLocked, GetPresentCoordSystem, GetPresentUnits(_2), GetProgramInfo, GetProjectInfo, GetUserComment, GetVersion, InitializeNewModel, SetMergeTol, SetModelIsLocked, SetPresentCoordSystem, SetPresentUnits(_2), SetProjectInfo, SetUserComment, Get/SetStringsExtendedEntityData, TreeSuspend/Resume/IsUpdateSuspended.

## 2. Namespaces que importan para el backlog — firma real (typelib) y estado

Notación: `py-> (...)` es lo que devuelve comtypes en Python (los `[in,out]` más `pRetVal`). Estado: **[H]** verificado en vivo con efecto releído · **[T]** solo typelib, sin probar · **[X]** probado y falla en SAFE.

### 2.1 Geometría / objetos de área — `AreaObj` (97 métodos, [T] salvo indicado)

- `AddByCoord(NumberPoints, X[], Y[], Z[], Name, PropName='Default', UserName='', CSys='Global')` py-> (X, Y, Z, Name, ret). **[H]** ya lo usa `create_area_by_coordinates`.
- `AddByPoint(NumberPoints, Point[], Name, PropName, UserName)`.
- `Delete(Name, ItemType=0)` — ItemType 0 objeto, 1 grupo, 2 selección.
- `ChangeName(Name, NewName)`, `Count()`, `GetNameList()`, `GetAllAreas()` py-> (n, names, DesignOrientation, nBoundaryPts, PointDelimiter, PointNames, X, Y, Z, ret) **[H]** lo usa `get_areas`.
- `GetPoints(Name)` py-> (n, Point[], ret). `GetProperty(Name)` / `SetProperty(Name, PropName, ItemType)`.
- `GetThickness / SetThickness(Name, ThicknessType, ThicknessPattern, SF, Thickness[], ItemType)`.
- `GetOffsets / SetOffsets(Name, OffsetType, OffsetPattern, SF, Offset[], ItemType)`, `GetOffsets3`.
- `GetOpening / SetOpening(Name, IsOpening, ItemType)`.
- `GetSpring / SetSpring(...)` (resorte de área directo) y `GetSpringAssignment / SetSpringAssignment(Name, SpringProp, ItemType)` (por propiedad de `PropAreaSpring`). **[H parcial]** `assign_area_spring` existe en el MCP; confirmar cuál de los dos usa.
- Cargas: `SetLoadUniform(Name, LoadPat, Value, Dir, Replace=True, CSys='Global', ItemType)`, `GetLoadUniform`, `DeleteLoadUniform`; `SetLoadUniformToFrame`; `SetLoadSurfacePressure`; `SetLoadTemperature`; `SetLoadGravity`. **[H]** `assign_area_uniform_load`-equivalente ya corre en ETABS con la misma firma.
- Malla: `GetAutoMesh / SetAutoMesh(_1)`; `SetEdgeConstraint`.
- `SetSelected(Name, Selected, ItemType)`, `GetSelected`, `SetGroupAssign(Name, GroupName, Remove, ItemType)`.
- `SetLocalAxes(Name, Ang)`, `SetModifiers(Name, Value[10])`, `SetMaterialOverwrite`.
- De ETABS, seguramente inertes en SAFE: SetPier, SetSpandrel, SetDiaphragm, GetRebarDataPier/Spandrel, GetLabelFromName/GetNameFromLabel (Story).

### 2.2 Edición geométrica — `EditGeneral` (11) · `EditArea` (8) · `EditPoint` (6)

Todos operan sobre la **selección actual** (no reciben nombre) salvo donde se indica. Patrón para "mover objeto X": `SelectObj.ClearSelection()` → `AreaObj.SetSelected(X, True)` → `EditGeneral.Move(DX, DY, DZ)` → `ClearSelection()`. Es el mismo patrón de `move_objects` del MCP de ETABS.

- `EditGeneral.Move(DX, DY, DZ)` py-> (ret).
- `EditGeneral.ReplicateLinear(DX, DY, DZ, Number, Remove=False)` py-> (nObj, ObjectName[], ObjectType[], ret).
- `EditGeneral.ReplicateMirror(Plane, X1,Y1,Z1, X2,Y2,Z2, X3,Y3,Z3, Remove)`, `ReplicateRadial(RotateAxis, X1,Y1,Z1, X2,Y2,Z2, Number, Ang, Remove)`.
- `EditGeneral.ExtrudePointToFrameLinear/Radial`, `ExtrudeFrameToAreaLinear/Radial`, `ExtrudeAreaToSolid*` (irrelevantes para SAFE).
- `EditArea.ChangeConnectivity(Name, NumberPoints, Point[])` — redefine los vértices de UN área por nombre. Es la vía para "editar el contorno de la zapata".
- `EditArea.Divide(Name, MeshType, N1, N2, MaxSize1, MaxSize2, ...)` py-> (nAreas, AreaName[], ret); `Divide_1` añade QuadsOnlyGeneral.
- `EditArea.Merge()` sobre selección py-> (n, names, ret). `ExpandShrink(OffsetType, Offset)` sobre selección. `PointAdd()` / `PointRemove()` sobre selección. `MergeToCreateUserMesh()`.
- `EditPoint.ChangeCoordinates(Name, X, Y, Z)` y `ChangeCoordinates_1(..., NoRefresh)` — mueve UN punto por nombre; arrastra las áreas que lo comparten. Vía más limpia para ajustar una esquina.
- `EditPoint.Merge(MergeTol)`, `Align(MyType, Ordinate)`, `Connect()`, `Disconnect()` sobre selección.

### 2.3 Puntos — `PointObj` (78)

- `GetCoordCartesian(Name, CSys='Global')` py-> (X, Y, Z, ret). **[H]** lo usa `get_points`.
- `SetLoadForce(Name, LoadPat, Value[6], Replace=False, CSys='Global', ItemType)` py-> (Value, ret); `GetLoadForce`, `DeleteLoadForce`, `CountLoadForce`. Variantes `*WithGUID`.
- `SetLoadDispl / GetLoadDispl / DeleteLoadDispl`.
- (no listados aquí: AddCartesian, SetRestraint, SetSpring, SetSpringAssignment, GetNameList, Count; pedir `describe_oapi(path="PointObj", filter="Restraint")` / `"Spring"` / `"Add"` cuando toque).

### 2.4 Propiedades de losa/zapata — `PropArea` (45)

- `SetSlab(Name, SlabType, ShellType, MatProp, Thickness, Color=-1, Notes='', GUID='')` py-> (ret). `GetSlab(Name)` py-> (SlabType, ShellType, MatProp, Thickness, Color, Notes, GUID, ret).
  - `SlabType` (enum eSlabType de ETABS): 0 Slab, 1 Drop, 2 Stiff, 3 Ribbed, 4 Waffle, 5 Mat, 6 Footing. **Confirmar en vivo** cuál acepta SAFE para Footing/Mat; el MCP ya define `define_slab_section` con este método (**[H]** para Slab según README).
  - `ShellType`: 1 ShellThin, 2 ShellThick, 3 Membrane, 4 (layered)…
- `SetSlabRibbed(Name, OverallDepth, SlabThickness, StemWidthTop, StemWidthBot, RibSpacing, RibsParallelTo)`, `SetSlabWaffle(...)`.
- `SetShellDesign(Name, MatProp(rebar), SteelLayoutOption, CoverTopDir1, CoverTopDir2, CoverBotDir1, CoverBotDir2)` / `GetShellDesign` — recubrimientos de diseño por sección.
- `GetTypeOAPI(Name)` py-> (PropType, ret); `GetNameList(PropType=0)`; `Delete`, `ChangeName`, `SetModifiers`.
- `SetShell/_1`, `SetDeck*`, `SetWall*`, `SetPlane`, `SetAsolid`, capas: son de ETABS/SAP; no usar.

### 2.5 Resorte de suelo — `PropAreaSpring` (5)

- `SetAreaSpringProp(Name, U1, U2, U3, NonlinearOption3, SpringOption=1, SoilProfile='', EndLengthRatio=0, Period=0, Color=0, Notes='', iGUID='')` py-> (ret).
  - `NonlinearOption3`: 0 Linear, 1 Compression only, 2 Tension only. `SpringOption`: 1 user-specified, 2 soil profile.
- `GetAreaSpringProp(Name)`, `GetNameList()`, `Delete`, `ChangeName`.
- Asignar: `AreaObj.SetSpringAssignment(Name, SpringProp)`. **[H]** según README (`define_soil_spring` + `assign_area_spring` corrieron en TORRE A); reconfirmar.

### 2.6 Diseño de losa y franjas — `DesignConcreteSlab` (8) · `.DesignStrip` (7) · `.ACI318_19` (1)

- `StartSlabDesign()` py-> (ret). **[H]** documentado y usado por `run_slab_design`.
- `GetFlexureAndShear()` py-> (StoryName[], DesignStripName[], Station[], ConcWidth[], FTopCombo[], FTopMoment[], FTopArea[], FTopAMin[], FBotCombo[], FBotMoment[], FBotArea[], FBotAMin[], AxialForce[], VCombo[], VForce[], VArea[], Status[], GlobalX[], GlobalY[], Layer[], ret) — **acero requerido por estación** (As top/bot y As mín). Cubre "acero de franja".
- `GetSummaryResultsFlexureAndShear()` py-> (StoryName, DesignStripName, SpanID, Location, FTopCombo, FTopMoment, FTopArea, FBotCombo, FBotMoment, FBotArea, VCombo, VForce, VArea, Status, Layer, ret). **[H]** probable base de `get_slab_design_summary`.
- `GetSummaryResultsSpanDefinition()` py-> (StoryName, DesignStripName, SpanID, SpanLength, StartDist, EndDist, X1, Y1, X2, Y2, ret). **[H]** base de `get_span_definitions`.
- `DesignStrip.GetNameList()`, `GetDesignStrip(Name)` py-> (Point[], X[], Y[], Z[], WBLeft[], WBRight[], WALeft[], WARight[], AutoWiden[], ret), `GetDesignStrip_1` añade DesignType, `Delete(Name)`, `ChangeName`, Get/SetGUID.
  - **No existe `Add`/`Set` de franja en el typelib.** Crear o ensanchar franjas por API solo se puede por `DatabaseTables` (tabla de definición de strips) o por F2K. Punto a resolver en Fase 2 con `list_tables(filter="Strip")` sobre un modelo abierto.
- `ACI318_19.GetPreference(Item)` py-> (textValue, numericValue, ret). Solo lectura de preferencias; también existen `ACI318_14` y `ACI318_25`. No hay `SetPreference` ni overwrites en el typelib → por tablas.
- `DesignResults.DesignForces` (sub-interfaz, no explorada).

### 2.7 Punzonamiento

**No hay ningún namespace ni método con "Punch" en el typelib** (buscado en SapModel, AreaObj, DesignConcreteSlab, Results). SAFE lo expone únicamente por `DatabaseTables`: tablas tipo "Punching Shear Design …" (nombre exacto a confirmar con `list_tables(filter="Punch")` con un modelo diseñado abierto). Lectura: `GetTableForDisplayArray`. Parámetros de punzonamiento por columna (perímetro, aberturas, refuerzo tipo stud/estribo) también por tabla de edición si SAFE la marca como editable (`ImportType` en `GetAvailableTables`). `get_punching_check` del MCP ya va por esta vía.

### 2.8 Resultados — `Results` (55)

- `AreaForceShell(Name, ItemTypeElm)` py-> (n, Obj, Elm, PointElm, LoadCase, StepType, StepNum, F11, F22, F12, FMax, FMin, FAngle, FVM, M11, M22, M12, MMax, MMin, MAngle, V13, V23, VMax, VAngle, ret).
- `AreaStressShell(...)` (S11Top… S23Avg), `AreaJointForceShell`, `AreaStrainShell`.
- `JointDispl(Name, ItemTypeElm)` py-> (n, Obj, Elm, LoadCase, StepType, StepNum, U1, U2, U3, R1, R2, R3, ret) — **asientos**.
- `JointReact(...)` mismo formato con F1..M3 — **reacciones**.
- `FrameJointForce`, `FrameForce` (no listado), `BaseReact`, `ModalPeriod`, etc.
- Antes de leer: `Results.Setup.DeselectAllCasesAndCombosForOutput()` + `SetCaseSelectedForOutput(case)` / `SetComboSelectedForOutput(combo)`. Documentado por CSI para SAFE.
- Presión de suelo: no hay método directo; el MCP la lee por tabla (`get_soil_pressure`). Alternativa: `AreaJointForceShell` en la cara de contacto.

### 2.9 Archivo — `File` (13)

- `OpenFile(FileName)` py-> (ret). **No existe `open_model` en el MCP de SAFE** (sí en el de ETABS). Hueco prioridad 0.
- `Save(FileName='')`, `NewBlank()`, `NewGridOnly(...)`.
- `ImportFile(FileName, FileType(eFileTypeIO), Type)` — `Type` no está descrito en el CHM (probable: 0 nuevo modelo / 1 agregar a existente). `probe_file_types` del MCP ya explora esto.
- `ExportFile(FileName, FileType)` con eFileTypeIO 1..5. **DXF no está en `eFileTypeIO`**: el export a DXF para detallar no tiene método API. Alternativas: tablas → CSV → DXF con `ezdxf` fuera de SAFE, o `Detailing` (typelib, sin probar en SAFE).

## 3. Lo que el MCP actual ya cubre (31 tools, v0.1.0) y sobre qué capa se apoya

`describe_oapi`, `get_model_info`, `get_units`/`set_units`, `list_tables`/`get_table_data`/`set_table_data` (capa A), `import_file`/`export_file`/`probe_file_types`/`save_model` (capa A), `run_analysis`/`get_analysis_status` (capa A), `run_slab_design` (capa A), `get_slab_design_summary`/`get_slab_design_detail`/`get_span_definitions`/`get_design_strips` (capa B, DesignConcreteSlab), `get_punching_check`/`get_soil_pressure` (tablas), `get_areas`/`get_points`/`create_area_by_coordinates` (capa B, AreaObj/PointObj), `define_concrete_material`/`define_rebar_material` (PropMaterial), `define_slab_section` (PropArea.SetSlab), `define_soil_spring`/`assign_area_spring` (PropAreaSpring/AreaObj), `add_load_pattern`/`add_load_combo` (LoadPatterns/RespCombo), `refresh_view`.

## 4. Huecos confirmados que hoy obligan a control total del PC

1. **Abrir/cerrar modelo**: falta `open_model(path)`, `new_model`, `close`. `File.OpenFile` existe y está documentado.
2. **Llamada genérica**: falta `call_oapi(path, method, args)` como en `servidor-mcp` (ETABS). Sin esto Claude no puede verificar métodos de capa B sin que Codex escriba una tool por cada prueba. **Es el primer lote**: con `call_oapi` Claude convierte cada [T] en [H] o [X] en una sesión.
3. **Borrar / mover / editar área**: `AreaObj.Delete`, `SetSelected` + `EditGeneral.Move`, `EditArea.ChangeConnectivity`, `EditPoint.ChangeCoordinates`, `AreaObj.SetProperty`, `SetOpening`, `SetThickness`.
4. **Cargas puntuales de columna**: `PointObj.SetLoadForce` (y `PointObj.AddCartesian` para crear el punto).
5. **Acero requerido por estación**: `DesignConcreteSlab.GetFlexureAndShear` (hoy solo hay el resumen).
6. **Franjas de diseño**: crear/editar → solo por tabla. Requiere identificar la tabla editable con `GetAvailableTables` (ImportType) sobre un modelo con franjas.
7. **Punzonamiento por columna con parámetros**: solo por tabla; identificar tablas `Punch*` editables.
8. **DXF**: sin API; decidir vía externa.
9. **Selección**: `SelectObj.ClearSelection/All/GetSelected` como tool (prerrequisito de 3).

## 5. Método de verificación (regla para ambos agentes)

Una tool pasa a [H] solo si: (a) `ret == 0`, (b) el efecto se relee con otra llamada (`GetPoints`, `GetProperty`, `GetTableForDisplayArray`…), (c) se anota aquí con fecha y firma. Un método que devuelve `ret != 0` en SAFE pasa a [X] con el código; no se reintenta con variantes de nombre porque el typelib ya es el real: si falla es que SAFE no lo implementa.

Modelo de prueba: copia `_pruebas-mcp.FDB` del `.FDB` de PRIMIS (`...\03- TORRE VERTICAL SERRALLES II. PRIMIS\SAFE\`). La carpeta `12-HOSPITAL MUNICIPAL EL VALLE` solo contiene un `.zip` sin modelos SAFE a 2026-09-25.

## 6. Verificado en vivo 2026-09-25 (segunda conexión) — modelo real HOSPITAL MUNICIPAL EL VALLE

[claude] Conexión restablecida tras relanzar SAFE. Modelo abierto: `...\12-HOSPITAL MUNICIPAL EL VALLE\Food Shop Shell Bonao - 15-05-2026\HOSPITAL MUNICIPAL EL VALLE\Modelos\SAFE\SAFE-HOSPITAL MUNICIPAL EL VALLE-25-09-26.FDB`. Es proyecto real: **solo lecturas**; nada de escrituras ni análisis sin orden de Emil. Unidades del modelo: N, mm (cargas en N, dimensiones en mm). Análisis: 6 casos (Dead, Live, LiveT, Qx, Qy, ~LLRF), ninguno corrido → no hay tablas de resultados todavía (64 tablas disponibles, todas de definición).

Tools del MCP que pasaron a **[H]** en esta sesión: `get_model_info`, `list_tables`, `get_table_data`, `get_analysis_status`, `get_design_strips` (capa B: `DesignStrip.GetNameList` + `GetDesignStrip_1` funcionan en SAFE 23), `get_punching_check` (lee la tabla de overwrites; con diseño corrido debería aparecer además la tabla de resultados de punzonamiento, nombre por confirmar).

### 6.1 Tablas que cierran los huecos 6 y 7 (esquema real, columnas exactas)

**Franjas — `Strip Object Connectivity`** (80 filas en este modelo):
`Name, NumSegs, StartPoint, EndPoint, WStartLeft, WStartRight, WEndLeft, WEndRight, AutoWiden, Layer, GUID`
Ej.: `CSA10, 1, 324, 318, 375, 375, 375, 375, No, A, <guid>`. Anchos en mm y son **semi-anchos** (375 → franja de 750). `Layer` = A o B. Puntos por nombre de PointObj. Crear una franja = insertar fila aquí por `SetTableForEditingArray` + `ApplyEditedTables` (pendiente probar en copia; `GetAvailableTables` devuelve `ImportType` por tabla y el MCP hoy lo descarta: **Codex, exponer `ImportType` en `list_tables`** para saber qué tablas aceptan edición sin probar a ciegas).

**Punzonamiento — `Concrete Slab Design Overwrites - Punching Shear - General`** (18 filas = 18 puntos de columna):
`UniqueName, CheckPunchingShear, LocationType, Perimeter, EffDepthType, OpeningDef, RebarType`
Valores vistos: `Program Determined, Auto, Auto, Auto, Auto, None`. `RebarType` es donde va el refuerzo de punzonamiento (None / studs / estribos; dominio exacto por confirmar editando). Las dimensiones de columna para el perímetro crítico vienen de `Joint Loads Assignments - Force` (`XDim, YDim`), no de esta tabla.

### 6.2 Otras tablas útiles ya confirmadas con esquema

- `Slab Property Definitions`: `Name, ModelType, PropType, Material, Thickness, NotSizeType, NotAutoFact, NotUserSize, f11Mod…v23Mod, MMod, WMod, Color, GUID, Notes, Ortho, EffectiveThickness11/22/12`. En el modelo: `S40 Shell-Thin Stiff C210 400` (con m11/m22/m12Mod = 100) y `Z40 Shell-Thick Footing C210 400`. Confirma que `PropType` acepta `Footing` y `Stiff`; `define_slab_section` debe mapear a esos textos si va por tabla, o a los enteros de eSlabType si va por `PropArea.SetSlab`.
- `Area Assignments - Section Properties`: `UniqueName, SectProp, PropType` (40 áreas: 12 S40 + 28 Z40).
- `Area Assignments - Area Springs`: `UniqueName, SpringProp` (20 áreas con `SOIL1`).
- `Spring Property Definitions - Area Springs`: `Name, StiffOpt, StiffU1, StiffU2, StiffU3, NonlinOpt3, Color, GUID, Notes`. `SOIL1: User, 0, 0, 0.035, Compression Only` (0.035 N/mm³ = 35,000 kN/m³ ≈ k = 1.2·σ_adm del SOP con σ_adm ≈ 2.9 kg/cm²; verificar contra el estudio de suelos).
- `Joint Loads Assignments - Force`: `UniqueName, LoadPattern, FX, FY, FZ, MX, MY, MZ, XDim, YDim, GUID` (72 filas; patrones tipo `Dead_ABOVE`: cargas importadas de ETABS).
- `Load Combination Definitions`: `Name, Type, IsAuto, LoadName, SF, GUID, Notes`, una fila por término (196 filas). Comb3: 1.248 D + 1.0 L + 0.714 Qx + 0.2142 Qy (patrón 100/30 con factor sísmico ya reducido).
- `Concrete Slab Design Overwrites - Strip Based`, `- Finite Element Based`, `Concrete Slab Design Load Combination Data`, `Concrete Design Preferences - ACI 318-19`, `Reinforcing Bar Sizes`, `Material Properties - Rebar Data`: existen; esquema pendiente de leer cuando haga falta.

### 6.3 Pendiente para cerrar con este modelo (requiere decisión de Emil)

- Correr análisis + diseño de losa en ESTE modelo para ver los nombres de las tablas de resultados (punzonamiento, soil pressure, strip forces) y validar `get_slab_design_summary/detail`, `get_soil_pressure`, `get_span_definitions`. El análisis no altera definiciones pero bloquea el modelo y genera archivos de resultados junto al .FDB. Decide Emil.
- Pruebas de escritura (crear franja por tabla, editar overwrite de punzonamiento, borrar/mover área, `open_model`, `call_oapi`): solo sobre copia `_pruebas-mcp.FDB`.

## 7. Corrida viva del lote 1 — 2026-09-25 [claude], sobre `_pruebas-mcp.FDB` (copia; sin guardar, reabierta limpia al final)

| Tool / método | Resultado | Evidencia |
|---|---|---|
| `open_model` (File.OpenFile) | **[H]** | Abrió la copia; get_model_info devuelve la ruta nueva. |
| `close_model` (File.NewBlank) | **[H]** | Cerró sin guardar; SAFE quedó en blanco; reabrió después. |
| `copy_model_file` | **[H]** | `_pruebas-mcp-2.FDB` 228,948 bytes. |
| `call_oapi` | **[H]** | 15 llamadas, ret y outs correctos. |
| `select_objects` / `get_selection` / `clear_selection` | **[H]** | Seleccionó áreas 6 y 1; GetSelected las listó (tipo 5 = area). |
| `get_area_info` (GetProperty/GetPoints/GetOpening + GetCoordCartesian) | **[H]** | Área 6: Z40, 4 vértices, coordenadas. |
| `set_area_property` (AreaObj.SetProperty) | **[H]** | 6: Z40→S40→Z40 releído. |
| `set_area_opening` (AreaObj.SetOpening) | **[H] con efecto colateral** | SetOpening(True) deja `GetProperty = None` y desaparece de `Area Assignments - Section Properties`; SetOpening(False) NO restaura. Corregido en v0.2.1: reasigna la sección previa o `section=`. |
| `add_point` (PointObj.AddCartesian) | **[H]** | Punto 339 en (30000,30000,0). |
| `assign_point_load` (PointObj.SetLoadForce) | **[H]** | Dead Fz=-150000 Mx=2e6; GetLoadForce relee 1 carga. |
| `move_objects` punto (SetSelected + EditGeneral.Move) | **[H]** | 339: (30000,30000)→(31000,30500). |
| `move_objects` área | **[H]** | Área 1 dx=+100/-200/+100: vértices siguen. La sección se conserva. Si los vértices están compartidos (área 6 con franjas), SAFE crea puntos nuevos para el área movida (5-8 → 340,353-355). |
| `move_objects` sobre vértices compartidos | **[H]** | Mover puntos 340 y 355 -100 en X los llevó a la posición de 5 y 8 y SAFE los fusionó: el área quedó con vértices 5,353,354,8. Es la vía para editar una esquina de zapata. |
| `set_point_coordinates` vía EditPoint.ChangeCoordinates / _1 | **[X] ret -99** | Reimplementada en v0.2.1 con GetCoordCartesian + move_objects. |
| `set_area_points` vía EditArea.ChangeConnectivity | **[X] ret -99** | Desregistrada en server.py; código queda para reintentar en versiones futuras. |
| `delete_object` área (AreaObj.Delete) | **[H]** | Área 6 borrada; GetProperty ret 1. |
| `delete_object` punto | **[X] → corregido** | PointObj no tiene `Delete`; `DeleteSpecialPoint(name, 0)` funciona (ret 0, GetCoordCartesian ret 1 después). v0.2.1 usa eso. |
| `get_strip_rebar_stations` (GetFlexureAndShear) | **[H]** | 552 estaciones con As sup/inf, mínimo, cortante, estado, X/Y. El modelo traía resultados de diseño guardados aunque `get_analysis_status` diga "no corrido". |
| `get_table_fields` (GetAllFieldsInTable) | **[H]** | `Strip Object Connectivity`: 11 campos, todos importables salvo NumSegs. Crear franjas por tabla es viable. |
| `list_tables` con ImportType | pendiente | requiere reinicio de Claude Desktop (código nuevo). |

### 7.1 Enums confirmados escribiendo y releyendo por tabla

- **eSlabType** (`PropArea.SetSlab`): 0 Slab, 1 Drop, 2 Stiff, 3 Ribbed, 4 Waffle, 5 Mat, 6 Footing. `GetSlab("Z40")` → (6, 2, C210, 400); `GetSlab("S40")` → (2, 1, …). **Bug v0.1.0:** `define_slab_section("Footing")` escribía 3 = Ribbed (losa nervada con nervios 125/900). Corregido en v0.2.1 (+ shell thick para footing/mat, + relectura).
- **eShellType**: 1 Shell-Thin, 2 Shell-Thick.
- **NonlinearOption3** (`PropAreaSpring.SetAreaSpringProp`): 0 None (lineal), 1 Compression Only, 2 Tension Only. **Bug v0.1.0:** `define_soil_spring(compression_only=True)` escribía 2 = **Tension Only** (resorte invertido). Corregido en v0.2.1 con verificación por tabla. `GetAreaSpringProp` devuelve NonlinearOption3 = 0 siempre (SOIL1, MCPTEST1, MCPTEST2): la relectura por método es inútil, solo vale la tabla.
- Advertencia: cualquier modelo creado con v0.1.0 vía `define_slab_section("Footing")` o `define_soil_spring(compression_only=True)` tiene secciones Ribbed y resortes Tension Only. Revisar TORRE A / SERRALLES II si se usaron esas tools.

### 7.2 v0.2.1 (mismo día)
Cambios en `src\Safe.py`: enums corregidos, `delete_object` de puntos por DeleteSpecialPoint, `set_point_coordinates` vía Move, `set_area_opening(section=)`, `set_area_points` desregistrada. 48 tools registradas. Pendiente: reinicio de Claude Desktop y segunda pasada sobre las 5 tools cambiadas.
