# CHANGELOG — servidor-mcp-safe

## 0.2.0 — 2026-09-25 [claude] lote 1 (sin verificar en vivo hasta reiniciar Claude Desktop)

Nuevas tools (18): `open_model`, `close_model`, `copy_model_file`, `call_oapi`, `clear_selection`,
`select_objects`, `get_selection`, `delete_object`, `move_objects`, `get_area_info`,
`set_area_property`, `set_area_opening`, `set_point_coordinates`, `set_area_points`, `add_point`,
`assign_point_load`, `get_strip_rebar_stations`, `get_table_fields`.
Cambio: `list_tables` muestra `ImportType` por tabla.
Fuente de cada firma: `docs\OAPI-SAFE-real.md`. Codigo del lote tal como se agrego: `docs\lote1-claude-2026-09-25.py.txt`.
Estado inicial de todas: [T] (typelib). Pasan a [H] solo tras corrida de Claude releyendo el efecto.

## 0.1.0 — 2026-08-10
Primera version, 31 tools, probada en vivo contra TORRE A.

## 0.2.1 — 2026-09-25 [claude] correcciones tras corrida viva (docs\OAPI-SAFE-real.md §7)

- BUG v0.1.0: `define_slab_section("Footing")` escribía eSlabType 3 (Ribbed). Ahora 6 (Footing); mapa completo 0..6; Shell-Thick para footing/mat; relee con GetSlab.
- BUG v0.1.0: `define_soil_spring(compression_only=True)` escribía NonlinearOption3 2 (Tension Only). Ahora 1 (Compression Only); verifica por tabla.
- `delete_object("point", …)` usa `PointObj.DeleteSpecialPoint` (no existe `Delete`); relee.
- `set_point_coordinates` reimplementada con SetSelected + EditGeneral.Move (ChangeCoordinates devuelve -99 en SAFE 23).
- `set_area_opening(name, is_opening, section="")`: al desmarcar reasigna la sección (SetOpening(True) la borra).
- `set_area_points` desregistrada (ChangeConnectivity -99). 48 tools.
- Verificadas [H] en vivo: open/close/copy_model, call_oapi, selección (3), get_area_info, set_area_property, add_point, assign_point_load, move_objects (punto y área), delete_object (área y punto), get_strip_rebar_stations, get_table_fields.

## Lote 2 — 2026-09-25 [codex], sobre v0.2.1, pendiente de corrida viva

- Tres tools [capa A, T]: add_design_strip, set_strip_widths y set_punching_overwrite,
  con las columnas reales de OAPI-SAFE-real.md §6.1. Lectura completa, edición de
  campos importables, ApplyEditedTables y relectura completa. NumSegs no se importa
  (claude-212); se verifica junto con filas ajenas, GUID, capa y semi-anchos.
- Validación de ImportType 0–3 según el CHM local ETABS 23: 1 no significa edición
  interactiva. Modelo bloqueado con tipo 2, esquema desconocido, anchos inválidos,
  duplicados y error de importación se reportan como SafeError. Sin rollback.
- set_table_data preserva TableVersion, valida forma/columnas, rechaza NumErrorMsgs
  además de errores fatales y compara las filas después de aplicar. Puede haber
  cambios parciales antes de que SAFE reporte un error; requiere copia de pruebas.
- Correcciones descubiertas por mocks: errores OapiError→SafeError; ret desconocido
  no es éxito; no repetir variantes tras ret!=0. Verificación efectiva de GetProperty,
  GetPoints, GetCoordCartesian, GetOpening y GetLoadForce, cargas acumuladas y
  coordenadas de vértices nuevos al mover áreas. Lectores ya no ocultan ret de error.
- Conservadas las correcciones de Claude v0.2.1/claude-212: Footing=6, Mat=5,
  Compression Only=1, movimiento por Move, DeleteSpecialPoint, restauración de sección
  tras abertura y set_area_points desregistrada. Se refuerza relectura de sección
  completa y rigidez de resorte por tabla (sin paginación ni comparación por substring).
- tests/test_lote1.py cubre 49 funciones previas (31+18, incluida una [X]);
  tests/test_tablas.py cubre las tres nuevas. tests/conftest.py bloquea COM real y
  parchea Safe._model. Dependencias aisladas en requirements-dev.txt; salida real
  en tests/ULTIMA-CORRIDA.txt. Sin SAFE ni .FDB en las pruebas.
- README: 52 implementadas, 51 registradas, [T]/[H]/[X], copia de pruebas, tests y
  advertencia sobre modelos hechos con los enums erróneos de v0.1.0. ENUMS-SAFE.md
  registra wrapper con ruta/línea/hash, CHM leído y dominios XML todavía pendientes.
  PRUEBA-VIVA-LOTE2.md contiene el procedimiento de verificación y límites heredados.
- No se editaron config.py/config.json ni servidor-mcp (ETABS). Los cambios de Claude
  presentes en Safe.py/server.py y este CHANGELOG se conservan en el mismo archivo.
