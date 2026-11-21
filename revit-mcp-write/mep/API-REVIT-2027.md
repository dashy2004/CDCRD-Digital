# API de Revit 2027 usada por el paquete `mep` — firmas leidas del binario

Evidencia de las firmas contra las que se escribio `revit-mcp-write/mep/`.
**No se ejecuto Revit**: es lectura de metadatos del ensamblado instalado.

- Ensamblado: `C:\Program Files\Autodesk\Revit 2027\RevitAPI.dll`
- ASSEMBLY RevitAPI, Version=27.0.20.0, Culture=neutral, PublicKeyToken=null
- FILEVERSION 27.0.20.10
- Metodo: PowerShell 7 + `System.Reflection.MetadataLoadContext` (carga de solo
  metadatos, con `PathAssemblyResolver` sobre la carpeta de Revit y la del runtime
  de .NET). Por cada tipo se listan constructores, propiedades y metodos publicos
  declarados en el propio tipo (`BindingFlags.DeclaredOnly`); los enum se listan
  por nombre, filtrados a los miembros que interesan. En los tipos grandes
  (`Document`, `Element`, `Curve`, `XYZ`, `Parameter`, `FamilyInstance`,
  `FilteredElementCollector`, `UnitTypeId`, `SpecTypeId`...) la seccion muestra
  solo los miembros consultados, no el tipo completo.

Que prueba y que no: prueba que el miembro **existe con esa firma** en la version
instalada. **No prueba comportamiento** (que `NewTeeFitting` logre colocar la te,
que `IsConnected` refleje un circuito, etc.): eso solo se sabe en una sesion viva.

## Resultado frente a lo pedido

| Pedido | En el binario |
|---|---|
| `Pipe.Create` | 3 sobrecargas (conector-conector, conector-punto, punto-punto con tipo de sistema) + `CreatePlaceholder` |
| `PlumbingUtils.BreakCurve` | `static ElementId BreakCurve(Document, ElementId pipeId, XYZ ptBreak)` |
| `NewTeeFitting` / `NewElbowFitting` / `NewTakeoffFitting` / `NewTransitionFitting` / `NewUnionFitting` | existen en `Autodesk.Revit.Creation.Document`; todas devuelven `FamilyInstance` |
| `Connector`: `IsConnected`, `ConnectTo`, `Origin`, `CoordinateSystem`, `Domain`, `Radius`, `PipeSystemType`, `ElectricalSystemType`, `AllRefs`, `MEPSystem` | existen todas. `ConnectTo` devuelve `Void` (no hay retorno que comprobar: se verifica con `IsConnected`) |
| `ConnectorManager`, `MEPModel`, `FamilyInstance.MEPModel` | existen (`Connectors`, `UnusedConnectors`, `Lookup`; `GetElectricalSystems`) |
| `ElectricalSystem.Create` | 2 sobrecargas: `(Connector, ElectricalSystemType)` y `(Document, IList<ElementId>, ElectricalSystemType)` |
| `ElectricalSystem.SelectPanel` | `Void SelectPanel(FamilyInstance panel)` |
| Carga y numero de circuito | `ApparentLoad` (Double), `CircuitNumber` (String), `PanelName`, `PolesNumber`, `Voltage`; `BaseEquipment` y `Elements` se heredan de `MEPSystem` |
| `IFailuresPreprocessor` / `FailuresAccessor` | existen; `PreprocessFailures(FailuresAccessor)` devuelve `FailureProcessingResult` |
| `ElementId` | constructor `(Int64)` y propiedad `Value` (Int64). **`IntegerValue` no existe** (comprobado: `False`) |
| `RBS_ELEC_APPARENT_LOAD`, `RBS_PIPE_SLOPE`, `RBS_PIPE_DIAMETER_PARAM` | existen en `BuiltInParameter` |

Hallazgos que condicionaron el codigo:

- `ElectricalEquipment` **no es un `Element`**: deriva de `MEPModel`. El sistema de
  distribucion del tablero se lee en `tablero.MEPModel.DistributionSystem`.
- `Connector.Id` es `Int32` (indice del conector dentro de su elemento), no un `ElementId`.
- Los parametros electricos del conector de una familia se leen con
  `Connector.GetMEPConnectorInfo()` -> `MEPFamilyConnectorInfo.GetConnectorParameterValue(ElementId)`
  -> `DoubleParameterValue.Value` / `IntegerParameterValue.Value`. El metodo esta solo en la
  subclase `MEPFamilyConnectorInfo`.
- `Transaction.Commit` y `Transaction.RollBack` aceptan `FailureHandlingOptions`.
- `Element.get_Parameter(BuiltInParameter)` existe (accesor del indizador `Parameter`).
- No hay en la API publica una propiedad de pendiente editable en `Pipe`/`MEPCurve`:
  la pendiente se construye con la cota de los extremos del tramo.

## Jerarquias

```
Autodesk.Revit.DB.Electrical.ElectricalEquipment : ElectricalEquipment -> MEPModel -> APIObject -> Object
Autodesk.Revit.DB.Electrical.ElectricalSystem : ElectricalSystem -> MEPSystem -> Element -> Object
Autodesk.Revit.DB.Electrical.DistributionSysType : DistributionSysType -> ElementType -> Element -> Object
Autodesk.Revit.DB.Plumbing.Pipe : Pipe -> MEPCurve -> HostObject -> Element -> Object
Autodesk.Revit.DB.Plumbing.PipeType : PipeType -> MEPCurveType -> HostObjAttributes -> ElementType -> Element -> Object
Autodesk.Revit.DB.Plumbing.PipingSystemType : PipingSystemType -> MEPSystemType -> ElementType -> Element -> Object
Autodesk.Revit.DB.Plumbing.PipingSystem : PipingSystem -> MEPSystem -> Element -> Object
Autodesk.Revit.DB.MEPFamilyConnectorInfo : MEPFamilyConnectorInfo -> MEPConnectorInfo -> Object
Autodesk.Revit.DB.DoubleParameterValue : DoubleParameterValue -> ParameterValue -> Object
Autodesk.Revit.DB.FamilyInstance : FamilyInstance -> Instance -> Element -> Object
Autodesk.Revit.DB.Electrical.LightingFixture : LightingFixture -> MEPModel -> APIObject -> Object
```

## Firmas


### Autodesk.Revit.DB.Plumbing.Pipe

```
  prop PipeType PipeType {get;set}
  static Pipe Create(Document document, ElementId pipeTypeId, ElementId levelId, Connector startConnector, Connector endConnector)
  static Pipe Create(Document document, ElementId pipeTypeId, ElementId levelId, Connector startConnector, XYZ endPoint)
  static Pipe Create(Document document, ElementId systemTypeId, ElementId pipeTypeId, ElementId levelId, XYZ startPoint, XYZ endPoint)
  static Pipe CreatePlaceholder(Document document, ElementId systemTypeId, ElementId pipeTypeId, ElementId levelId, XYZ startPoint, XYZ endPoint)
  static Boolean IsPipeTypeId(Document document, ElementId pipeTypeId)
  static Boolean IsPipingConnector(Connector connector)
  prop PipeFlowState FlowState {get}
  prop Boolean IsPlaceholder {get}
  prop PipeSegment PipeSegment {get}
  static Boolean IsPipingSystemTypeId(Document document, ElementId systemTypeId)
  Void SetSystemType(ElementId systemTypeId)
```

### Autodesk.Revit.DB.Plumbing.PlumbingUtils

```
  static ElementId BreakCurve(Document document, ElementId pipeId, XYZ ptBreak)
  static Boolean ConnectPipePlaceholdersAtCross(Document document, Connector connector1, Connector connector2, Connector connector3, Connector connector4)
  static Boolean ConnectPipePlaceholdersAtCross(Document document, ElementId placeholder1Id, ElementId placeholder2Id, ElementId placeholder3Id)
  static Boolean ConnectPipePlaceholdersAtCross(Document document, ElementId placeholder1Id, ElementId placeholder2Id)
  static Boolean ConnectPipePlaceholdersAtElbow(Document document, Connector connector1, Connector connector2)
  static Boolean ConnectPipePlaceholdersAtElbow(Document document, ElementId placeholder1Id, ElementId placeholder2Id)
  static Boolean ConnectPipePlaceholdersAtTee(Document document, Connector connector1, Connector connector2, Connector connector3)
  static Boolean ConnectPipePlaceholdersAtTee(Document document, ElementId placeholder1Id, ElementId placeholder2Id)
  static ICollection<ElementId> ConvertPipePlaceholders(Document document, ICollection<ElementId> placeholderIds)
  static Boolean HasOpenConnector(Document document, ElementId elemId)
  static Void PlaceCapOnOpenEnds(Document document, ElementId elemId, ElementId typeId)
```

### Autodesk.Revit.DB.Mechanical.MechanicalUtils

```
  static ElementId BreakCurve(Document document, ElementId ductId, XYZ ptBreak)
```

### Autodesk.Revit.Creation.Document

```
  FamilyInstance NewCrossFitting(Connector connector1, Connector connector2, Connector connector3, Connector connector4)
  FamilyInstance NewElbowFitting(Connector connector1, Connector connector2)
  FamilyInstance NewTakeoffFitting(Connector connector, MEPCurve curve)
  FamilyInstance NewTeeFitting(Connector connector1, Connector connector2, Connector connector3)
  FamilyInstance NewTransitionFitting(Connector connector1, Connector connector2)
  FamilyInstance NewUnionFitting(Connector connector1, Connector connector2)
```

### Autodesk.Revit.DB.Connector

```
  prop Boolean AllowsSlopeAdjustments {get}
  prop ConnectorSet AllRefs {get}
  prop Double Angle {get;set}
  prop DuctFlowConfigurationType AssignedDuctFlowConfiguration {get}
  prop DuctLossMethodType AssignedDuctLossMethod {get}
  prop Double AssignedFixtureUnits {get;set}
  prop Double AssignedFlow {get;set}
  prop FlowDirectionType AssignedFlowDirection {get}
  prop Double AssignedFlowFactor {get;set}
  prop Double AssignedKCoefficient {get;set}
  prop Double AssignedLossCoefficient {get;set}
  prop PipeFlowConfigurationType AssignedPipeFlowConfiguration {get}
  prop PipeLossMethodType AssignedPipeLossMethod {get}
  prop Double AssignedPressureDrop {get;set}
  prop Double Coefficient {get}
  prop ConnectorManager ConnectorManager {get}
  prop ConnectorType ConnectorType {get}
  prop Transform CoordinateSystem {get}
  prop Double Demand {get}
  prop String Description {get}
  prop FlowDirectionType Direction {get}
  prop Domain Domain {get}
  prop DuctSystemType DuctSystemType {get}
  prop ElectricalSystemType ElectricalSystemType {get}
  prop Double EngagementLength {get}
  prop Double Flow {get}
  prop Double GasketLength {get}
  prop Double Height {get;set}
  prop Int32 Id {get}
  prop Boolean IsConnected {get}
  prop Boolean IsMovable {get}
  prop Boolean IsValidObject {get}
  prop MEPSystem MEPSystem {get}
  prop XYZ Origin {get;set}
  prop Element Owner {get}
  prop PipeSystemType PipeSystemType {get}
  prop Double PressureDrop {get}
  prop Double Radius {get;set}
  prop ConnectorProfileType Shape {get}
  prop Boolean Utility {get}
  prop Double VelocityPressure {get}
  prop Double Width {get;set}
  Void ConnectTo(Connector connector)
  Void DisconnectFrom(Connector connector)
  Void Dispose()
  FabricationConnectorInfo GetFabricationConnectorInfo()
  MEPConnectorInfo GetMEPConnectorInfo()
  Boolean IsConnectedTo(Connector connector)
```

### Autodesk.Revit.DB.ConnectorManager

```
  prop ConnectorSet Connectors {get}
  prop Boolean IsValidObject {get}
  prop Element Owner {get}
  prop ConnectorSet UnusedConnectors {get}
  Void Dispose()
  Connector Lookup(Int32 index)
```

### Autodesk.Revit.DB.ConnectorSet

```
  ctor()
  prop Boolean IsEmpty {get}
  prop Int32 Size {get}
  Void Clear()
  Boolean Contains(Connector item)
  Int32 Erase(Connector item)
  ConnectorSetIterator ForwardIterator()
  IEnumerator GetEnumerator()
  Boolean Insert(Connector item)
  ConnectorSetIterator ReverseIterator()
```

### Autodesk.Revit.DB.MEPModel

```
  prop ConnectorManager ConnectorManager {get}
  prop Boolean IsValidObject {get}
  ISet<ElectricalSystem> GetAssignedElectricalSystems()
  ISet<ElectricalSystem> GetElectricalSystems()
```

### Autodesk.Revit.DB.FamilyInstance

```
  prop MEPModel MEPModel {get}
  prop Element Host {get}
  prop Location Location {get}
  prop FamilySymbol Symbol {get;set}
```

### Autodesk.Revit.DB.MEPCurve

```
  prop ConnectorManager ConnectorManager {get}
  prop Double Diameter {get}
  prop Double Height {get}
  prop Double LevelOffset {get;set}
  prop MEPSystem MEPSystem {get}
  prop Level ReferenceLevel {get;set}
  prop Double Width {get}
```

### Autodesk.Revit.DB.MEPSystem

```
  prop FamilyInstance BaseEquipment {get}
  prop Connector BaseEquipmentConnector {get}
  prop ConnectorManager ConnectorManager {get}
  prop ElementSet Elements {get}
  prop Boolean HasDesignParts {get}
  prop Boolean HasFabricationParts {get}
  prop Boolean HasPlaceholders {get}
  prop Boolean IsEmpty {get}
  prop Boolean IsMultipleNetwork {get}
  prop Boolean IsValid {get}
  prop Double PressureLossOfCriticalPath {get}
  prop Int32 SectionsCount {get}
  Void Add(ConnectorSet connectors)
  ICollection<ElementId> DivideSystem(Document ADoc)
  IList<Int32> GetCriticalPathSectionNumbers()
  Int32 GetPhysicalNetworksNumber()
  MEPSection GetSectionByIndex(Int32 index)
  MEPSection GetSectionByNumber(Int32 sectionNumber)
  Boolean IsSystemDividable()
  Void Remove(ICollection<ElementId> elementIds)
  Void Remove(ConnectorSet connectors)
```

### Autodesk.Revit.DB.Plumbing.PipingSystem

```
  prop Connector BaseEquipmentConnector {get;set}
  prop Boolean IsWellConnected {get}
  prop ElementSet PipingNetwork {get}
  prop PipeSystemType SystemType {get}
  static Boolean CanBeHydraulicLoopBoundary(Element element)
  static PipingSystem Create(Document ADocument, ElementId typeId, String name)
  static PipingSystem Create(Document ADocument, ElementId typeId)
  static ISet<ElementId> CreateHydraulicSeparation(Document document, ISet<ElementId> pipeElementIds)
  static Void DeleteHydraulicSeparation(Document document, ISet<ElementId> pipeElementIds)
  Double GetFixtureUnits()
  Double GetFlow()
  ISet<ElementId> GetPumpSets()
  Double GetStaticPressure()
  Double GetVolume()
  Boolean IsFlowServerMissing()
  static Boolean IsHydraulicLoopBoundary(Element element)
  Boolean IsPressureDropServerMissing()
```

### Autodesk.Revit.DB.Plumbing.PipingSystemType

```
  prop FlowConversionMode FlowConversionMethod {get;set}
  prop Double FluidTemperature {get;set}
  prop ElementId FluidType {get;set}
  prop RiseDropSymbol SingleLineBendDropType {get;set}
  prop RiseDropSymbol SingleLineBendRiseType {get;set}
  prop RiseDropSymbol SingleLineJunctionDropType {get;set}
  prop RiseDropSymbol SingleLineJunctionRiseType {get;set}
  prop RiseDropSymbol TwoLineDropType {get;set}
  prop RiseDropSymbol TwoLineRiseType {get;set}
  static PipingSystemType Create(Document ADoc, MEPSystemClassification systemClassification, String name)
  Boolean ValidateRiseDropSymbolType(RiseDropSymbol risedropType)
```

### Autodesk.Revit.DB.MEPSystemType

```
  prop String Abbreviation {get;set}
  prop SystemCalculationLevel CalculationLevel {get;set}
  prop Color FillColor {get;set}
  prop ElementId FillPatternId {get;set}
  prop Boolean FillVisible {get;set}
  prop Color LineColor {get;set}
  prop ElementId LinePatternId {get;set}
  prop Int32 LineWeight {get;set}
  prop ElementId MaterialId {get;set}
  prop MEPSystemClassification SystemClassification {get}
```

### Autodesk.Revit.DB.Plumbing.PipeType

```

```

### Autodesk.Revit.DB.Electrical.ElectricalSystem

```
  prop Double ApparentCurrent {get}
  prop Double ApparentCurrentPhaseA {get}
  prop Double ApparentCurrentPhaseB {get}
  prop Double ApparentCurrentPhaseC {get}
  prop Double ApparentLoad {get}
  prop Double ApparentLoadPhaseA {get}
  prop Double ApparentLoadPhaseB {get}
  prop Double ApparentLoadPhaseC {get}
  prop Boolean BalancedLoad {get}
  prop ElementId CableSize {get;set}
  prop ElementId CableType {get;set}
  prop CircuitConnectionType CircuitConnectionType {get;set}
  prop Int32 CircuitNamingIndex {get}
  prop String CircuitNumber {get}
  prop ElectricalCircuitPathMode CircuitPathMode {get;set}
  prop CircuitType CircuitType {get}
  prop Double Frame {get;set}
  prop ElementId GroundConductorSize {get}
  prop Int32 GroundConductorsNumber {get}
  prop Boolean HasCustomCircuitPath {get}
  prop Boolean HasPathOffset {get}
  prop ElementId HotConductorSize {get}
  prop Int32 HotConductorsNumber {get}
  prop Boolean IsBasePanelFeedThroughLugsOccupied {get}
  prop Double Length {get}
  prop String LoadClassificationAbbreviations {get}
  prop String LoadClassifications {get}
  prop String LoadName {get;set}
  prop ElementId NeutralConductorSize {get}
  prop Int32 NeutralConductorsNumber {get}
  prop ElementId OtherConductorSize {get}
  prop Int32 OtherConductorsNumber {get}
  prop String PanelName {get}
  prop Double PathOffset {get;set}
  prop String PhaseLabel {get}
  prop Int32 PolesNumber {get}
  prop Double PowerFactor {get}
  prop PowerFactorStateType PowerFactorState {get}
  prop Double Rating {get;set}
  prop Int32 RunsNumber {get}
  prop String SlotIndex {get}
  prop Int32 StartSlot {get}
  prop ElectricalSystemType SystemType {get}
  prop Double TrueCurrent {get}
  prop Double TrueCurrentPhaseA {get}
  prop Double TrueCurrentPhaseB {get}
  prop Double TrueCurrentPhaseC {get}
  prop Double TrueLoad {get;set}
  prop Double TrueLoadPhaseA {get}
  prop Double TrueLoadPhaseB {get}
  prop Double TrueLoadPhaseC {get}
  prop Double Voltage {get}
  prop Int32 Ways {get}
  Boolean AddToCircuit(ElementSet components)
  static ElectricalSystem Create(Connector connector, ElectricalSystemType elecSysType)
  static ElectricalSystem Create(Document document, IList<ElementId> electComponents, ElectricalSystemType elecSysType)
  Void DisconnectPanel()
  IList<XYZ> GetCircuitPath()
  Boolean IsCircuitPathValid(IList<XYZ> nodes)
  WireSet NewWires(View view, WiringType wiringType)
  Void RemoveFromCircuit(ElementSet components)
  Void SelectPanel(FamilyInstance panel)
  Void SetCircuitPath(IList<XYZ> nodes)
```

### Autodesk.Revit.DB.Electrical.ElectricalSystemType (enum)

```
  UndefinedSystemType, Data, PowerCircuit, Telephone, Security, FireAlarm, NurseCall, Controls, Communication, PowerBalanced, PowerUnBalanced
```

### Autodesk.Revit.DB.Electrical.DistributionSysType

```
  prop ElectricalPhase ElectricalPhase {get;set}
  prop ElectricalPhaseConfiguration ElectricalPhaseConfiguration {get;set}
  prop ElectricalPhaseLine HighLegPhase {get;set}
  prop Boolean IsInUse {get}
  prop Int32 NumWires {get;set}
  prop VoltageType VoltageLineToGround {get;set}
  prop VoltageType VoltageLineToLine {get;set}
```

### Autodesk.Revit.DB.Electrical.ElectricalEquipment

```
  prop ElementId CircuitNamingSchemeId {get;set}
  prop DistributionSysType DistributionSystem {get;set}
  prop Boolean IsSwitchboard {get}
  prop Int32 MaxNumberOfCircuits {get;set}
  CircuitNaming GetCircuitNamingSchemeType()
  static Boolean IsValidCircuitNamingSchemeId(Document aDocument, ElementId circuitNamingSchemeId)
  Boolean IsValidDistributionSystem(DistributionSysType distributionSystem)
  Void SetCircuitNamingSchemeType(CircuitNaming circuitNamingType)
```

### Autodesk.Revit.DB.IFailuresPreprocessor (interface)

```
  FailureProcessingResult PreprocessFailures(FailuresAccessor failuresAccessor)
```

### Autodesk.Revit.DB.FailuresAccessor

```
  prop Boolean IsValidObject {get}
  Boolean CanCommitPendingTransaction()
  Boolean CanRollBackPendingTransaction()
  TransactionStatus CommitPendingTransaction()
  Void DeleteAllWarnings()
  Void DeleteElements(IList<ElementId> idsToDelete)
  Void DeleteWarning(FailureMessageAccessor failure)
  Void Dispose()
  IList<FailureResolutionType> GetAttemptedResolutionTypes(FailureMessageAccessor failure)
  Document GetDocument()
  FailureHandlingOptions GetFailureHandlingOptions()
  IList<FailureMessageAccessor> GetFailureMessages(FailureSeverity severity)
  IList<FailureMessageAccessor> GetFailureMessages()
  FailureSeverity GetSeverity()
  String GetTransactionName()
  Boolean IsActive()
  Boolean IsElementsDeletionPermitted(IList<ElementId> idsToDelete)
  Boolean IsElementsDeletionPermitted(IList<ElementId> idsToDelete, String& reason)
  Boolean IsElementsDeletionPermitted()
  Boolean IsFailureResolutionPermitted()
  Boolean IsFailureResolutionPermitted(FailureMessageAccessor failure)
  Boolean IsFailureResolutionPermitted(FailureMessageAccessor failure, FailureResolutionType resolutionType)
  Boolean IsPending()
  Boolean IsTransactionBeingCommitted()
  Void JournalFailures(IList<FailureMessageAccessor> failures)
  Void PostFailure(FailureMessage failure)
  Void ReplaceFailures(FailureMessage failure)
  Void ResolveFailure(FailureMessageAccessor failure)
  Void ResolveFailures(IList<FailureMessageAccessor> failures)
  TransactionStatus RollBackPendingTransaction()
  Void SetFailureHandlingOptions(FailureHandlingOptions options)
  Void SetTransactionName(String transactionName)
```

### Autodesk.Revit.DB.FailureMessageAccessor

```
  prop Boolean IsValidObject {get}
  FailureMessage CloneFailureMessage()
  Void Dispose()
  ICollection<ElementId> GetAdditionalElementIds()
  FailureResolutionType GetCurrentResolutionType()
  String GetDefaultResolutionCaption()
  String GetDescriptionText()
  ICollection<ElementId> GetFailingElementIds()
  FailureDefinitionId GetFailureDefinitionId()
  Int32 GetNumberOfResolutions()
  FailureSeverity GetSeverity()
  Boolean HasResolutionOfType(FailureResolutionType type)
  Boolean HasResolutions()
  Void SetCurrentResolutionType(FailureResolutionType resolutionType)
  Boolean ShouldMergeWithMessage(FailureMessageAccessor messageToMergeWith)
```

### Autodesk.Revit.DB.FailureProcessingResult (enum)

```
  Continue, ProceedWithCommit, ProceedWithRollBack, WaitForUserInput
```

### Autodesk.Revit.DB.FailureSeverity (enum)

```
  None, Warning, Error, DocumentCorruption
```

### Autodesk.Revit.DB.FailureHandlingOptions

```
  prop Boolean IsValidObject {get}
  Void Dispose()
  Boolean GetClearAfterRollback()
  Boolean GetDelayedMiniWarnings()
  IFailuresPreprocessor GetFailuresPreprocessor()
  Boolean GetForcedModalHandling()
  ITransactionFinalizer GetTransactionFinalizer()
  FailureHandlingOptions SetClearAfterRollback(Boolean bFlag)
  FailureHandlingOptions SetDelayedMiniWarnings(Boolean bFlag)
  FailureHandlingOptions SetFailuresPreprocessor(IFailuresPreprocessor preprocessor)
  FailureHandlingOptions SetForcedModalHandling(Boolean bFlag)
  FailureHandlingOptions SetTransactionFinalizer(ITransactionFinalizer finalizer)
```

### Autodesk.Revit.DB.Transaction

```
  ctor(Document document, String name)
  ctor(Document document)
  prop Boolean IsValidObject {get}
  TransactionStatus Commit(FailureHandlingOptions options)
  TransactionStatus Commit()
  Void Dispose()
  FailureHandlingOptions GetFailureHandlingOptions()
  String GetName()
  TransactionStatus GetStatus()
  Boolean HasEnded()
  Boolean HasStarted()
  TransactionStatus RollBack(FailureHandlingOptions options)
  TransactionStatus RollBack()
  Void SetFailureHandlingOptions(FailureHandlingOptions options)
  Void SetName(String name)
  TransactionStatus Start(String name)
  TransactionStatus Start()
```

### Autodesk.Revit.DB.TransactionStatus (enum)

```
  Uninitialized, Started, RolledBack, Committed, Pending, Error, Proceed
```

### Autodesk.Revit.DB.ElementId

```
  ctor(BuiltInParameter parameterId)
  ctor(BuiltInCategory categoryId)
  ctor(Int64 id)
  prop static ElementId InvalidElementId {get}
  prop Int64 Value {get}
  Int32 Compare(ElementId id)
  Int32 CompareTo(Object id)
  Boolean Equals(Object obj)
  Int32 GetHashCode()
  static ElementId Parse(String idStr)
  String ToString()
  static Boolean TryParse(String idStr, ElementId& id)
```

### Autodesk.Revit.DB.Domain (enum)

```
  DomainUndefined, DomainHvac, DomainElectrical, DomainPiping, DomainCableTrayConduit, DomainStructuralAnalytical
```

### Autodesk.Revit.DB.ConnectorType (enum)

```
  Invalid, End, Curve, Logical, Reference, Surface, EndSurface, Physical, NonEnd, MainSurface, Family, NodeReference, BlankEnd, AnyEnd, Super, AllModes
```

### Autodesk.Revit.DB.ConnectorProfileType (enum)

```
  Invalid, Round, Rectangular, Oval
```

### Autodesk.Revit.DB.Plumbing.PipeSystemType (enum)

```
  UndefinedSystemType, SupplyHydronic, ReturnHydronic, Sanitary, Vent, DomesticHotWater, DomesticColdWater, OtherPipe, FireProtectWet, FireProtectDry, FireProtectPreaction, FireProtectOther, Fitting, Global
```

### Autodesk.Revit.DB.MEPSystemClassification (enum)

```
  UndefinedSystemClassification, SupplyAir, ReturnAir, ExhaustAir, OtherAir, DataCircuit, PowerCircuit, SupplyHydronic, ReturnHydronic, Telephone, Security, FireAlarm, NurseCall, Controls, Communication, CondensateDrain, Sanitary, Vent, Storm, DomesticHotWater, DomesticColdWater, Recirculation, OtherPipe, FireProtectWet, FireProtectDry, FireProtectPreaction, FireProtectOther, SwitchTopology, Fitting, Global, PowerBalanced, PowerUnBalanced, CableTrayConduit
```

### Autodesk.Revit.DB.BuiltInParameter (enum)

```
  RBS_PIPING_SYSTEM_TYPE_PARAM, RBS_SYSTEM_CLASSIFICATION_PARAM, RBS_SYSTEM_NAME_PARAM, RBS_PIPE_SLOPE, RBS_PIPE_OUTER_DIAMETER, RBS_PIPE_DIAMETER_PARAM, RBS_CURVE_SLOPE, RBS_PIPE_INNER_DIAM_PARAM, RBS_ELEC_CIRCUIT_PANEL_PARAM, RBS_ELEC_CIRCUIT_NUMBER, RBS_ELEC_CIRCUIT_NAME, RBS_ELEC_PANEL_NAME, RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM, RBS_ELEC_APPARENT_LOAD_PHASEC, RBS_ELEC_APPARENT_LOAD_PHASEB, RBS_ELEC_APPARENT_LOAD_PHASEA, RBS_ELEC_TRUE_LOAD, RBS_ELEC_APPARENT_LOAD_PHASE3, RBS_ELEC_APPARENT_LOAD_PHASE2, RBS_ELEC_APPARENT_LOAD_PHASE1, RBS_ELEC_APPARENT_LOAD, RBS_ELEC_VOLTAGE, RBS_ELEC_NUMBER_OF_POLES, RBS_OFFSET_PARAM, RBS_END_OFFSET_PARAM, RBS_START_OFFSET_PARAM, RBS_START_LEVEL_PARAM
  RBS_PIPE_SLOPE_DEF_PARAM, RBS_ELEC_PANEL_SUPPLY_FROM_PARAM, RBS_ELEC_CIRCUIT_RATING_PARAM, SCHEDULE_LEVEL_PARAM, SYMBOL_NAME_PARAM, ALL_MODEL_TYPE_NAME, INSTANCE_REFERENCE_LEVEL_PARAM, INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM, FAMILY_LEVEL_PARAM
  RBS_PIPE_SLOPE, RBS_PIPE_DIAMETER_PARAM, RBS_ELEC_PANEL_NAME, RBS_ELEC_APPARENT_LOAD, RBS_ELEC_VOLTAGE, RBS_ELEC_NUMBER_OF_POLES
```

### Autodesk.Revit.DB.BuiltInCategory (enum)

```
  OST_PlumbingEquipment, OST_Sprinklers, OST_PipeAccessory, OST_FlexPipeCurves, OST_PipeFitting, OST_PipeCurves, OST_DuctCurves, OST_PlumbingFixtures, OST_MechanicalEquipment, OST_LightingFixtures, OST_ElectricalFixtures, OST_ElectricalEquipment
```

### Autodesk.Revit.DB.UnitUtils

```
  static Double Convert(Double value, ForgeTypeId currentUnitTypeId, ForgeTypeId desiredUnitTypeId)
  static Double ConvertFromInternalUnits(Double value, ForgeTypeId unitTypeId)
  static Double ConvertToInternalUnits(Double value, ForgeTypeId unitTypeId)
```

### Autodesk.Revit.DB.UnitTypeId

```
  prop static ForgeTypeId Feet {get}
  prop static ForgeTypeId Meters {get}
  prop static ForgeTypeId Millimeters {get}
  prop static ForgeTypeId VoltAmperes {get}
  prop static ForgeTypeId Volts {get}
  prop static ForgeTypeId Watts {get}
```

### Autodesk.Revit.DB.SpecTypeId

```
  prop static ForgeTypeId ApparentPower {get}
  prop static ForgeTypeId ElectricalPotential {get}
  prop static ForgeTypeId Length {get}
  prop static ForgeTypeId PipeSize {get}
```

### Autodesk.Revit.DB.Document

```
  prop Document Create {get}
  prop Boolean IsFamilyDocument {get}
  prop Boolean IsLinked {get}
  prop Boolean IsModifiable {get}
  prop Boolean IsReadOnly {get}
  prop String PathName {get}
  prop String Title {get}
  Element GetElement(String uniqueId)
  Element GetElement(ElementId id)
  Element GetElement(Reference reference)
  Void Regenerate()
  Void Save(SaveOptions options)
  Void Save()
  Void SaveAs(String filepath)
  Void SaveAs(ModelPath path, SaveAsOptions options)
  Void SaveAs(String filepath, SaveAsOptions options)
  prop Application Application {get}
```

### Autodesk.Revit.ApplicationServices.Application

```
  prop DocumentSet Documents {get}
```

### Autodesk.Revit.DB.Line

```
  static Line CreateBound(XYZ endpoint1, XYZ endpoint2)
```

### Autodesk.Revit.DB.Curve

```
  prop Boolean IsBound {get}
  prop Double Length {get}
  XYZ Evaluate(Double parameter, Boolean normalized)
  XYZ GetEndPoint(Int32 index)
  IntersectionResult Project(XYZ point)
```

### Autodesk.Revit.DB.IntersectionResult

```
  ctor()
  prop Double Distance {get}
  prop Edge EdgeObject {get}
  prop Double EdgeParameter {get}
  prop Double Parameter {get}
  prop UV UVPoint {get}
  prop XYZ XYZPoint {get}
```

### Autodesk.Revit.DB.LocationCurve

```
  prop Curve Curve {get;set}
  prop ElementArray ElementsAtJoin {get;set}
  prop JoinType JoinType {get;set}
```

### Autodesk.Revit.DB.Transform

```
  prop XYZ BasisX {get;set}
  prop XYZ BasisY {get;set}
  prop XYZ BasisZ {get;set}
  prop XYZ Origin {get;set}
```

### Autodesk.Revit.DB.Electrical.VoltageType

```
  prop Double ActualValue {get}
  prop Boolean IsInUse {get}
  prop Double MaxValue {get}
  prop Double MinValue {get}
  Void SetVoltageValue(Double actualValue, Double minValue, Double maxValue)
```

### Autodesk.Revit.DB.Parameter

```
  prop Boolean HasValue {get}
  prop Boolean IsReadOnly {get}
  prop StorageType StorageType {get}
  Double AsDouble()
  ElementId AsElementId()
  Int32 AsInteger()
  String AsString()
  String AsValueString(FormatOptions formatOptions)
  String AsValueString()
  ForgeTypeId GetUnitTypeId()
  Boolean Set(Int32 value)
  Boolean Set(String value)
  Boolean Set(ElementId value)
  Boolean Set(Double value)
```

### Autodesk.Revit.DB.Element

```
  prop Category Category {get}
  prop ElementId Id {get}
  prop Boolean IsValidObject {get}
  prop ElementId LevelId {get}
  prop String Name {get;set}
  Parameter GetParameter(ForgeTypeId parameterTypeId)
  ElementId GetTypeId()
  Parameter LookupParameter(String name)
  String get_Name()
  Parameter get_Parameter(Guid guid)
  Parameter get_Parameter(BuiltInParameter parameterId)
  Parameter get_Parameter(Definition definition)
  prop Document Document {get}
  prop Location Location {get}
  prop String UniqueId {get}
```

### Autodesk.Revit.DB.MEPConnectorInfo

```
  prop Boolean IsPrimary {get}
  prop Boolean IsSecondary {get}
  prop Boolean IsValidObject {get}
  prop Connector LinkedConnector {get}
  Void Dispose()
```

### Autodesk.Revit.DB.MEPFamilyConnectorInfo

```
  ElementId GetAssociateFamilyParameterId(ElementId connectorParameterId)
  ParameterValue GetConnectorParameterValue(ElementId connectorParameterId)
```

### Autodesk.Revit.DB.ParameterValue

```
  prop Boolean IsValidObject {get}
  ParameterValue Copy()
  Void Dispose()
  Boolean IsEqual(ParameterValue other)
  Boolean IsSameType(ParameterValue other)
```

### Autodesk.Revit.DB.DoubleParameterValue

```
  ctor(Double value)
  ctor()
  prop Double Value {get;set}
```

### Autodesk.Revit.DB.IntegerParameterValue

```
  ctor(Int32 value)
  ctor()
  prop Int32 Value {get;set}
```

### Autodesk.Revit.DB.Electrical.ElectricalPhase (enum)

```
  SinglePhase, ThreePhase
```

### Autodesk.Revit.DB.Electrical.ElectricalPhaseConfiguration (enum)

```
  Undefined, Wye, Delta
```

### Autodesk.Revit.DB.ElementSet

```
  ctor()
  prop Boolean IsEmpty {get}
  prop Int32 Size {get}
  Void Clear()
  Boolean Contains(Element item)
  Int32 Erase(Element item)
  ElementSetIterator ForwardIterator()
  IEnumerator GetEnumerator()
  Boolean Insert(Element item)
  ElementSetIterator ReverseIterator()
```

### Autodesk.Revit.DB.DocumentSet

```
  ctor()
  prop Boolean IsEmpty {get}
  prop Int32 Size {get}
  Void Clear()
  Boolean Contains(Document item)
  Int32 Erase(Document item)
  DocumentSetIterator ForwardIterator()
  IEnumerator GetEnumerator()
  Boolean Insert(Document item)
  DocumentSetIterator ReverseIterator()
```

### Autodesk.Revit.DB.FailureDefinitionId

```
  ctor(Guid guid)
```

### Autodesk.Revit.DB.Level

```
  prop Double Elevation {get;set}
  prop Double ProjectElevation {get}
```

### Autodesk.Revit.DB.FilteredElementCollector

```
  ctor(Document hostDocument, ElementId viewId, ElementId linkId)
  ctor(Document document, ElementId viewId)
  ctor(Document document, ICollection<ElementId> elementIds)
  ctor(Document document)
  FilteredElementCollector OfCategory(BuiltInCategory category)
  FilteredElementCollector OfClass(Type type)
  FilteredElementCollector WhereElementIsElementType()
  FilteredElementCollector WhereElementIsNotElementType()
```

### Autodesk.Revit.DB.StorageType (enum)

```
  None, Integer, Double, String, ElementId
```

### Autodesk.Revit.DB.XYZ

```
  ctor(Double x, Double y, Double z)
  ctor()
  prop static XYZ BasisZ {get}
  prop Double X {get}
  prop Double Y {get}
  prop Double Z {get}
  XYZ Add(XYZ source)
  XYZ CrossProduct(XYZ source)
  Double DistanceTo(XYZ source)
  Double DotProduct(XYZ source)
  Double GetLength()
  Boolean IsAlmostEqualTo(XYZ source, Double tolerance)
  Boolean IsAlmostEqualTo(XYZ source)
  XYZ Multiply(Double value)
  XYZ Normalize()
  XYZ Subtract(XYZ source)
```

### Autodesk.Revit.DB.Electrical.LightingFixture

```

```

### Autodesk.Revit.DB.MEPCurveType

```
  prop FamilySymbol Cross {get;set}
  prop FamilySymbol Elbow {get;set}
  prop FamilySymbol MultiShapeTransition {get;set}
  prop JunctionType PreferredJunctionType {get;set}
  prop Double Roughness {get;set}
  prop RoutingPreferenceManager RoutingPreferenceManager {get}
  prop ConnectorProfileType Shape {get}
  prop FamilySymbol Tap {get;set}
  prop FamilySymbol Tee {get;set}
  prop FamilySymbol Transition {get;set}
  prop FamilySymbol Union {get;set}
```

### Autodesk.Revit.DB.Location

```
  Boolean Move(XYZ translation)
  Boolean Rotate(Line axis, Double angle)
```

### Autodesk.Revit.DB.LocationPoint

```
  prop XYZ Point {get;set}
  prop Double Rotation {get}
```

### Autodesk.Revit.DB.SubTransaction

```
  ctor(Document document)
  prop Boolean IsValidObject {get}
  TransactionStatus Commit()
  Void Dispose()
  TransactionStatus GetStatus()
  Boolean HasEnded()
  Boolean HasStarted()
  TransactionStatus RollBack()
  TransactionStatus Start()
```

### Autodesk.Revit.DB.Category

```
  prop BuiltInCategory BuiltInCategory {get}
  prop ElementId Id {get}
  prop String Name {get}
```

### Autodesk.Revit.DB.Electrical.CircuitType (enum)

```
  Circuit, Spare, Space
```

## Comprobaciones puntuales

```
MIEMBRO ElementId.IntegerValue: False
```
