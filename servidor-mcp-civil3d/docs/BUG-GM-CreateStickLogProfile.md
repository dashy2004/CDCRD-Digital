# Bug del Geotechnical Modeler: NullReferenceException en CreateStickLogProfile

Reporte para Autodesk (C3D-GeoTechModeler-2027.bundle, Civil 3D 2027 /
release 26.0). Preparado por el equipo CDCRD-Digital, 2026-10-15.

## Sintoma

Al crear el perfil de sondeos desde el panel *Subsurface Profiles* (boton
que ejecuta `CreateSubsurfaceProfile2D`), el GM lanza
`System.NullReferenceException` con el marco superior en
`Aecc.Gtm.CADServices.ProfileService.CreateStickLogProfile`.

## Analisis (decompilacion de Aecc.Gtm.CADServices.dll, 417.112 bytes, 2026)

`CreateStickLogProfile(Point3d, Alignment, string, double, double, string,
StickLogConfiguration, GeologyHatchStyleConfiguration)` desreferencia sin
chequeo el resultado de varios lookups que pueden devolver null:

1. **`GetStratumAndLensSurfaces().TopSurface`** — el candidato principal.
   `GetStratumAndLensSurfaces()` clasifica las TinSurface del dibujo asi:
   - *FullStratum*: por **carpeta** (las que viven en la carpeta GM de
     superficies de estrato), no por nombre;
   - *Top*: **solo** la superficie con nombre **exactamente igual** a
     `"GM - Top Surface"` (`FirstOrDefault()`, puede ser null).

   Acto seguido el metodo ejecuta:

   ```csharp
   Color color = ((SurfaceStyle)_docService.GetObject(
       ((Entity)stratumAndLensSurfaces.TopSurface).StyleId, ...))
       .GetDisplayStylePlan(SurfaceDisplayStyleType.Triangles).Color;
   ```

   Si la superficie top no existe con ese nombre exacto (borrada, o renombrada
   por el propio Civil 3D a `"GM - Top Surface.1"` al resolver una colision de
   nombres — el mismo mecanismo que dejo las superficies de estrato de este
   proyecto como `GM - Stratum - <X>.1`), `TopSurface` es null y la linea
   anterior lanza el NRE **dentro de CreateStickLogProfile**, consistente con
   la pila observada.

2. `GetProfileViewStyle("GM - Standard")`, `GetProfileLabelSetStyle("GM -
   Standard")`, `GetProfileViewBandSetStyle("GM - Standard")` y
   `GetProfileStyle("GM - Hidden")` se usan sin chequeo de null (para
   `"GM - Top Surface"` si hay chequeo con mensaje claro). Un dibujo sin esos
   estilos produce el mismo sintoma.

3. En el bucle de estratos, `CopyProfileStyle("GM - Stratum Surface", ...)`
   puede devolver null si el nombre destino fue purgado en la misma sesion
   (comportamiento conocido de `CopyAsSibling` en 2027) y se usa sin chequeo.

## Estado del proyecto afectado

- Dibujo: SOLAR.dwg (metrico). Sondeos S-1..S-5 importados de CSV.
- Superficies GM presentes: `GM - Top Surface` **(hoy existe)** y
  `GM - Stratum - {RELLENO, ARCILLA RESIDUAL, CALIZA METEORIZADA, CALIZA
  COMPETENTE}.1` (sufijo `.1` por re-creacion; los ProfileStyles de estrato
  tambien quedaron con `.1`, huerfanos).
- Los seis estilos de nombre fijo existen. 68 hatch huerfanos en la capa
  `GM-PROF-STICKLOG-2D` de corridas anteriores.

## Reproduccion y evidencia automatizadas

- `gm_diagnosticar` (puente cdcrd-civil3d >= 0.5.0) verifica cada
  precondicion anterior y lista lo que falta.
- `gm_crear_perfil_sondeos(..., solo_perfil=True)` llama
  `CreateStickLogProfile` con el mismo flujo del panel y devuelve la
  excepcion completa (tipo, mensaje, metodo, pila) cuando falla.
- El GM trae logging oculto: los comandos `GM_DebugLogging_On` /
  `GM_DebugLogging_Off` escriben `DebugLog_<ticks>.txt` en el
  `DebugLogFilePath` de `%PROGRAMDATA%\Autodesk\C3D-GeoTechModeler-2027\
  Application.config`; cada paso de `CreateStickLogProfile` queda logueado
  (`GetProfileViewStyle(GM - Standard)`, `SetProfileStyleProperties`, ...),
  asi que la ultima linea del log identifica el lookup que devolvio null.

## Mitigacion en el proyecto

- `gm_reparar` renombra `GM - ... .1` al nombre base cuando el base falta y
  limpia los hatch huerfanos.
- Camino alternativo sin GM: receta nativa `generar_perfil_estratigrafico`
  (docs/PERFIL_ESTRATIGRAFICO.md) + isometricos 3D nativos
  (docs/TRIDIMENSIONAL.md), verificados en vivo sobre el mismo dataset.

## Sugerencia para Autodesk

Chequear null tras `GetStratumAndLensSurfaces().TopSurface` y tras cada
`Get*Style` de nombre fijo, con el mismo mensaje claro que ya existe para
`GM - Top Surface` como ProfileStyle (`CreateMissingStyleErrorMessage`), y
buscar la superficie top de forma tolerante al sufijo `.N` que el propio
Civil 3D agrega al resolver colisiones de nombre.
