# SAFE MCP — lote 2 sobre v0.2.1

Servidor MCP de CSI SAFE 23.3.0, OAPI 2.016. ProgID confirmado:
`CSI.SAFE.API.ETABSObject`. Fuente técnica: `docs/OAPI-SAFE-real.md`;
inventario ampliado: `docs/BACKLOG-HERRAMIENTAS.md`; enums y fuentes locales:
`docs/ENUMS-SAFE.md`.

El catálogo tiene **52 funciones implementadas: 51 tools registradas y una
[X] deshabilitada**. Son las 31 iniciales, las 18 del lote 1 de Claude y las
3 por tabla del lote 2. `set_area_points` fue retirada por Claude tras
`EditArea.ChangeConnectivity → -99`; sigue bajo test para detectar regresiones.
No debe anunciarse como tool disponible.

## Evidencia [T] / [H] / [X]

- **[T]**: firma/esquema documentado o presente en typelib. Los mocks comprueban
  argumentos, retornos y verificaciones del cliente; no prueban la implementación SAFE.
- **[H]**: corrida viva de Claude con `ret=0` y efecto releído, con fecha y evidencia
  en `docs/OAPI-SAFE-real.md`. Un resultado histórico no verifica una revisión nueva.
- **[X]**: falla confirmada en SAFE, con retorno y versión. No se sustituye por un
  nombre supuesto ni se reintenta una escritura después de un retorno de error.

**Nada es [H] sin corrida viva de Claude.** Las tres tools nuevas y todas las
verificaciones añadidas en este lote quedan [T] hasta esa corrida. `claude-212`
confirma la corrida del lote 1 y los enums; v0.2.1 y este lote requieren reiniciar
Claude Desktop desde la bandeja y revalidar los cambios.

## Catálogo

| Grupo | Tools registradas | Cantidad |
|---|---|---:|
| Sesión y diagnóstico | `get_model_info`, `get_units`, `set_units`, `save_model`, `refresh_view`, `describe_oapi` | 6 |
| Geometría inicial | `get_points`, `get_areas`, `create_area_by_coordinates` | 3 |
| Propiedades y cargas iniciales | `define_concrete_material`, `define_rebar_material`, `define_slab_section`, `define_soil_spring`, `assign_area_spring`, `add_load_pattern`, `add_load_combo` | 7 |
| Análisis y diseño | `run_analysis`, `get_analysis_status`, `run_slab_design`, `get_slab_design_summary`, `get_slab_design_detail`, `get_design_strips`, `get_span_definitions`, `get_punching_check`, `get_soil_pressure` | 9 |
| Tablas y archivos iniciales | `probe_file_types`, `list_tables`, `get_table_data`, `set_table_data`, `import_file`, `export_file` | 6 |
| Archivo y diagnóstico lote 1 | `open_model`, `close_model`, `copy_model_file`, `call_oapi` | 4 |
| Selección lote 1 | `clear_selection`, `select_objects`, `get_selection` | 3 |
| Geometría y cargas lote 1 | `delete_object`, `move_objects`, `get_area_info`, `set_area_property`, `set_area_opening`, `set_point_coordinates`, `add_point`, `assign_point_load` | 8 |
| Lecturas lote 1 | `get_strip_rebar_stations`, `get_table_fields` | 2 |
| Tablas lote 2 [T] | `add_design_strip`, `set_strip_widths`, `set_punching_overwrite` | 3 |

Función conservada sin registro: `set_area_points` **[X]**. Para cambiar una esquina,
Claude verificó mover sus puntos; mover un área puede crear otros IDs de vértices.
`move_objects` relee la conectividad después de mover. Si desaparece el ID de un
punto movido individualmente por fusión, devuelve error de verificación: inspeccionar
antes de repetir. `set_area_opening(False, section="...")` restaura la sección;
SAFE no la restaura por sí solo al quitar una abertura.

`get_punching_check` puede devolver solo overwrites si no hay tablas de resultados.
Eso no equivale a una comprobación resistente de punzonamiento. El acero por estación
es acero requerido; no es un plano de armado. DXF no está en `eFileTypeIO` (1–5).

## Nuevas herramientas por tabla [capa A, T]

```python
add_design_strip(name, start_point, end_point, w_left, w_right,
                 layer="A", auto_widen=False)
set_strip_widths(name, w_start_left, w_start_right, w_end_left, w_end_right)
set_punching_overwrite(point, check=None, location=None, perimeter=None,
                      eff_depth=None, opening=None, rebar_type=None)
```

Franjas: `Strip Object Connectivity`, exactamente las once columnas del esquema
vivo §6.1. Los anchos son **semi-anchos en unidades activas**, no anchos totales.
Crear usa el mismo ancho al inicio y final, una franja de un segmento, Layer A/B,
y GUID generado por SAFE. No reemplaza nombres existentes. Editar rechaza franjas
multisegmento hasta confirmar un selector por segmento.

Punzonamiento: `Concrete Slab Design Overwrites - Punching Shear - General`:
`UniqueName, CheckPunchingShear, LocationType, Perimeter, EffDepthType, OpeningDef,
RebarType`. `None` conserva la columna. Crear una fila exige sus seis valores;
no se inventan defaults. `eff_depth` corresponde al **tipo** `EffDepthType`, no
al valor numérico de profundidad. El XML instalado no declara dominios de texto:
Claude debe confirmarlos en copia. Los valores recibidos se someten a importación
y relectura; no se anuncian como válidos solo porque el cliente los acepte.

Ambas tablas se leen completas, se modifican las filas solicitadas, se envían
las columnas importables y se relee toda la tabla. `NumSegs` no es importable,
según Claude; se conserva para comparar. La relectura admite reordenación de filas,
formato numérico equivalente en anchos y generación de GUID; no admite cambios
silenciosos en otras filas. `GetTableForDisplayArray` no pagina la lectura COM.

`list_tables` explica `ImportType`: 0 no importable; 1 importable sin edición
interactiva; 2 editable con modelo desbloqueado; 3 editable también bloqueado.
Las tools nuevas exigen 2/3 y no desbloquean automáticamente. Un esquema distinto,
retorno no cero, errores de importación o efecto distinto producen `SafeError`.
`ApplyEditedTables` puede haber aplicado cambios parciales antes del error:
**no hay rollback automático**. Inspeccionar la copia antes de repetir.

## Copia de pruebas y corrida viva

1. Claude comprueba `get_model_info()` y `get_units()`. Para incorporar cambios
   pendientes al archivo, guardar explícitamente con `save_model()`.
2. Ejecutar `copy_model_file(dest_path="C:\\ruta\\_pruebas-mcp.FDB")`.
   Copia la versión guardada en disco; no captura cambios sin guardar y no cambia
   el modelo activo. No sobrescribe un destino existente salvo `overwrite=True`.
3. Abrir la copia con `open_model(path="C:\\ruta\\_pruebas-mcp.FDB")` y confirmar
   la ruta con `get_model_info()` antes de escribir. OpenFile cierra el anterior
   sin guardarlo. Todas las pruebas se hacen en esa copia.
4. Emil reinicia Claude Desktop desde la bandeja. Claude prueba cada tool nueva,
   relee tablas/geometría y devuelve [H]/[P]/[X] por buzón. Procedimiento concreto
   en `docs/PRUEBA-VIVA-LOTE2.md`.

Codex implementa, prueba mocks y documenta. Claude es el único operador de la
sesión viva. Los tests no abren SAFE, no cargan COM y no leen/escriben ningún .FDB.

## Tests

Desde `servidor-mcp-safe`, con Python 3.10 o posterior:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/
```

`tests/conftest.py` sustituye comtypes antes del import, bloquea sus puntos de
entrada y parchea `Safe._model` con un MagicMock. No crea un hilo COM. Los métodos
retornan las tuplas py-> documentadas, con datos sintéticos de valores distintos.
`test_lote1.py` cubre las 49 funciones anteriores (incluida [X]); `test_tablas.py`
cubre las tres nuevas, ret, errores de Apply, preservación y relectura.
La última salida real está en `tests/ULTIMA-CORRIDA.txt`.

GetPresentUnits/GetModelFilename/GetModelIsLocked devuelven valores directos,
no pRetVal. `describe_oapi` inspecciona y `copy_model_file` copia disco.
`probe_file_types` es diagnóstico: acumula los retornos fallidos por tipo en su
respuesta. Estas excepciones al test ret!=0 están identificadas en la suite.
Las definiciones heredadas de materiales/cargas y el import/export genérico no
obtienen por estos mocks una certificación del modelo: Claude debe releer su
contenido en vivo. El lote no inventa getters ni esquemas para esa validación.

## Enums: revisar modelos creados con v0.1.0

Claude confirmó el 2026-09-25 que v0.1.0 enviaba **3=Ribbed** al pedir Footing y
**2=Tension Only** al pedir Compression Only. v0.2.1 usa **6=Footing** y
**1=Compression Only**, con Shell-Thick para Footing/Mat. Los tests fijan estos
contratos y comprueban errores de relectura. `GetAreaSpringProp` devuelve siempre
0 para la opción no lineal en esta instalación; se verifica por tabla.

Los modelos que usaron esas tools con v0.1.0 deben revisarse por sus secciones y
resortes. Actualizar el servidor no modifica los modelos guardados. Detalles y
fuentes con línea/hash en `docs/ENUMS-SAFE.md`.

## Instalación

Instalar `requirements.txt` con el intérprete de Claude Desktop y ejecutar
`instalar-safe.ps1` para registrar `safe`; el servidor ETABS `fea` es independiente.
`src/config.json` fija el ProgID confirmado en esta máquina. Reiniciar Claude Desktop
desde la bandeja tras cambiar código/registro. Mantener `mcp>=1.10,<2`: el servidor
usa `mcp.server.fastmcp`. No es necesario reinstalar COM para correr tests.
