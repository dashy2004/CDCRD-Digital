# Bugs del Geotechnical Modeler al crear el perfil de sondeos

Reporte para Autodesk (C3D-GeoTechModeler-2027.bundle, Civil 3D 2027 /
release 26.0). Equipo CDCRD-Digital. Abierto 2026-10-15, actualizado
2026-10-16 con el stack real y con la reproduccion exitosa.

Hay **dos fallas distintas** en el mismo flujo del panel *Subsurface
Profiles*. La primera es un `NullReferenceException`; la segunda es un
cuelgue por dialogo modal. Las dos se reproducen sin UI con
`gm_crear_perfil_sondeos` del puente cdcrd-civil3d (>= 0.5.1).

---

## Falla 1 — NullReferenceException al borrar los sticklogs anteriores

### Stack real (capturado en vivo del dialogo de error, 2026-10-15)

```
ProfileService.DeleteStickLogProfile
  -> StickLogDiagram.Delete(bool deleteProfileView)
    -> ProfileStickLog.Delete()
      -> ObjectId.GetObject(...)
```

`CreateStickLogProfile` empieza por "Delete existing profiles", asi que el
NRE ocurre **antes** de crear nada: el metodo que falla es el de borrado, no
el de creacion.

### Analisis (decompilacion de Aecc.Gtm.CADServices.dll, 417.112 bytes)

`ProfileStickLog.Delete()` recorre los miembros del grupo de AutoCAD del
sticklog y los borra uno por uno:

```csharp
ObjectId[] allEntityIds = _stickLogObjectsGroup.GetAllEntityIds();
foreach (ObjectId objId in allEntityIds)
{
    DBObject val = _docService.GetObject(objId, OpenMode.ForRead, openErased: false);
    if (val is BlockReference val2)
    {
        ObjectId blockTableRecord = val2.BlockTableRecord;
        BlockTableRecord val3 = (BlockTableRecord)blockTableRecord.GetObject(OpenMode.ForWrite, false);  // <-- marco del stack
        ...
        ((DBObject)val2).Erase();
        ((DBObject)val3).Erase();
    }
    else { ... val.UpgradeOpen(); val.Erase(); }
}
_docService.GetGroupDbDictionary().Remove(_stickLogObjectsGroup.Id);
```

Tres cosas, ninguna protegida:

1. `_docService.GetObject(..., openErased: false)` se pasa directo a
   `Transaction.GetObject`; el resultado se usa sin chequeo de null y sin
   atrapar `eWasErased`.
2. El `BlockTableRecord` de la `BlockReference` se abre con
   `ObjectId.GetObject` **sin comprobar** que siga vivo. Un sticklog creado
   por una corrida anterior interrumpida deja referencias cuya definicion de
   bloque ya fue borrada: ahi falla, y ese es el marco del stack observado.
3. Un sticklog que comparte definicion de bloque con otro queda con el
   segundo `val3.Erase()` sobre un BTR ya borrado.

El propio GM tiene el saneo en otro metodo
(`ProfileService.DeleteOrphanedStickLogObjects`), pero solo borra grupos
**vacios** cuyo nombre empieza con `GM - Profile - 2D - StickLog ` y
BlockTableRecords sin referencias; no cubre el caso de arriba, y corre
**despues** de `DeleteStickLogProfile`.

### Confirmacion experimental (2026-10-16)

Con el dibujo saneado a mano (68 hatch huerfanos de `GM-PROF-STICKLOG-2D` y
3 grupos de `ACAD_GROUP` de sticklogs viejos, borrados por LISP y guardados),
`CreateStickLogProfile` **pasa**: 5 sondeos, 230 ms, sin excepcion, y el
`DebugLog` del GM llega hasta `End: ProfileService.CreateStickLogProfile`
pasando por `DeleteStickLogProfile` y `DeleteOrphanedStickLogObjects`.

=> La causa del NRE es el **estado residual del dibujo**, no la ausencia de
`GM - Top Surface` (que existia en todas las corridas).

### Nota sobre los grupos (medido, no supuesto)

Al borrar una entidad, AutoCAD la quita de sus grupos: el grupo queda
**vacio** (0 codigos 340), no con referencias nulas. Verificado creando un
grupo de una sola linea y borrando la linea: `(dictsearch ... grupo)` ya no
trae miembros. Por eso un detector util debe buscar **grupos vacios**
(y BlockTableRecords sin referencias), no "miembros muertos".

### Candidato secundario (sigue abierto)

`GetStratumAndLensSurfaces()` clasifica las TinSurface asi: *FullStratum* por
**carpeta**, pero *Top* **solo** por nombre exactamente igual a
`"GM - Top Surface"` (`FirstOrDefault()`, puede ser null). Acto seguido:

```csharp
Color color = ((SurfaceStyle)_docService.GetObject(
    ((Entity)stratumAndLensSurfaces.TopSurface).StyleId, ...))
    .GetDisplayStylePlan(SurfaceDisplayStyleType.Triangles).Color;
```

Si Civil 3D renombro esa superficie a `GM - Top Surface.1` al resolver una
colision de nombres (el mismo mecanismo que dejo las de estrato de este
proyecto como `GM - Stratum - <X>.1`), `TopSurface` es null y esa linea
lanza NRE. No es lo que paso aqui, pero el chequeo tampoco existe.
Igual pasa con `GetProfileViewStyle("GM - Standard")`,
`GetProfileLabelSetStyle`, `GetProfileViewBandSetStyle`,
`GetProfileStyle("GM - Hidden")` y `CopyProfileStyle("GM - Stratum
Surface", ...)`.

---

## Falla 2 — Cuelgue: MessageBox modal dentro del flujo de hatches

### Sintoma

Con `hatchStyleConfig` armado, el flujo se queda sin responder entre
`GetAlignment` y `CreateStickLogProfile`. Desde una API (o desde un script)
no hay forma de saber por que: la ventana principal queda bloqueada y todo
lo que depende del hilo principal vence por timeout.

### Causa (decompilado, `GeologyHatchingService.cs`)

`AssignHatchStylesToBoreholeStrata(...)` cuenta los estratos que casaron con
el archivo de estilos y, si no caso ninguno, **abre un MessageBox**:

```csharp
int num = 0;
foreach (Borehole b in stickLogBoreholes)
    num += b.AssignHatchStylesToStrata(geologyField, cfg.HatchStyleLookup, cfg.DefaultHatchStyle);

if (num == 0 && (int)MessageBox.Show(
        "None of the strata in the current project have matching hatch styles ...
         Would you like to generate the hatch styles now?",
        "Generate Hatch Styles?", (MessageBoxButtons)4) == 6)
{ CreateHatchStylesForUnassignedGeologyNames(...); ... }
```

Es el **unico** `MessageBox` de todo `Aecc.Gtm.CADServices.dll` (grep sobre
el decompilado completo), y cae justo donde el flujo se detenia.

El `num == 0` se da facil: el campo de busqueda por defecto
(`StickLogConfiguration.ProfileGeologyField`) viene **vacio**, y con campo
vacio ningun estrato casa, aunque `GeologyHatchStyle.config` si tenga
entradas para `RELLENO`, `ARCILLA RESIDUAL`, `CALIZA METEORIZADA` y
`CALIZA COMPETENTE` (caso de este proyecto).

### Mitigacion

El propio comando de prueba del GM pasa `hatchStyleConfig = null`. El puente
hace lo mismo desde 0.5.2 (`hatch_geologia=False` por defecto) y con eso el
flujo corre limpio. Para usar hatches hay que fijar antes
`ProfileGeologyField` a un campo real (`GeologyCode1`, `LegendCode`, ...).

### Sugerencia para Autodesk

Ningun servicio de la capa CADServices deberia abrir dialogos: el aviso
pertenece a la UI del panel. Alternativa minima: parametro
`silent`/`interactive` y, en modo silencioso, devolver el conteo para que el
llamador decida.

---

## Estado del proyecto de prueba

- Dibujo: SOLAR.dwg (metrico, INSUNITS 6). Proyecto GM
  "Diseno de Terminal Interregional de Autobuses del Este", sondeos S-1..S-5
  importados de CSV. **Datos geotecnicos hipoteticos/preliminares.**
- Superficies: `GM - Top Surface` presente;
  `GM - Stratum - {RELLENO, ARCILLA RESIDUAL, CALIZA METEORIZADA,
  CALIZA COMPETENTE}.1` (sufijo `.1` por re-creacion).
- Los seis estilos de nombre fijo existen. Tras la limpieza: 0 hatch
  huerfanos, 0 grupos muertos.

## Reproduccion y evidencia automatizadas

- `gm_diagnosticar` (>= 0.5.0; cuenta de grupos desde 0.5.2) verifica cada
  precondicion y lista lo que falta.
- `gm_crear_perfil_sondeos(..., solo_perfil=True)` llama
  `CreateStickLogProfile` con el mismo flujo del panel y devuelve la
  excepcion completa (tipo, mensaje, metodo, pila) cuando falla.
  Con `hatch_geologia=True` reproduce la Falla 2.
- `eventos_dialogo` (servido desde el hilo del socket desde 0.5.2) identifica
  el modal que bloquea, con sus textos, aunque el hilo principal este tomado.
- Logging oculto del GM: `GM_DebugLogging_On` / `GM_DebugLogging_Off`
  escriben `DebugLog_<ticks>.txt` en el `DebugLogFilePath` de
  `%PROGRAMDATA%\Autodesk\C3D-GeoTechModeler-2027\Application.config`; cada
  paso de `CreateStickLogProfile` queda logueado, asi que la ultima linea
  identifica el punto exacto. El logger es *Scoped*: `gm_crear_perfil_sondeos`
  lo habilita por reflexion en su propio scope.

## Mitigacion en el proyecto

- Limpiar el estado residual antes de crear el perfil (`gm_reparar`:
  hatches huerfanos, grupos; y el renombrado de `GM - ... .1`).
- No armar `hatchStyleConfig` salvo que `ProfileGeologyField` tenga un campo
  real.
- Camino alternativo sin GM, verificado en vivo sobre el mismo dataset:
  receta nativa `generar_perfil_estratigrafico` (docs/PERFIL_ESTRATIGRAFICO.md)
  + isometricos 3D nativos (docs/TRIDIMENSIONAL.md).
