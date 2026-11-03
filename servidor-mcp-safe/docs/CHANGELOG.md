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

## 0.3.0 — 2026-11-02 [claude, Fable local] pilotes: S/B y reacción axial, pendiente de corrida viva

- Dos tools nuevas de SOLO LECTURA (53 registradas): `get_pile_spacing` (separación entre
  pilotes, S/B y factor de grupo de la tabla 5.1 del MOPC R-024) y `get_pile_axial_reactions`
  (carga axial por pilote y combinación, envolvente y pilote crítico). Spec de Cowork en
  `_coordinacion/PROMPTS/2026-11-02 safe-mcp separacion de pilotes S-sobre-D (local, Fable).md`.
- Nuevo `src/pilotes.py`: criterio puro sin COM (tabla 5.1 step_down/linear, fuera de tabla sin
  extrapolar, grilla espacial 8Ø, punto-en-polígono por cabezal, capacidad de grupo (a)/(b),
  envolvente axial). Lectura COM en el bloque PILOTES de `Safe.py`.
- Vía de lectura de frames: `FrameObj.GetAllFrames` + `PropFrame.GetNameList/GetTypeOAPI/GetCircle`
  (typelib SAFEv1 real). No se añadió `get_frames` genérico ni lectura por tablas.
- Unidades fijadas con `set_units` y restauradas; `ret=0` verificado (tipo Circle=9 confirmado por
  sección, longitudes de arreglos); nunca `File.Save`.
- Tests: `tests/test_pilotes.py` (43, fixtures sintéticas: malla 3×3 a 2.25 m Ø450 → S/B 5.00 /
  0.90; pareja a 1.20 m → 2.67 fuera de tabla; diámetros mezclados; duplicado; sin circulares;
  pilote solo; punto aislado) y `tests/test_pilotes_safe.py` (23, capa COM sobre el mock).
  258 verdes (`tests/ULTIMA-CORRIDA.txt`). `test_lote1` actualizado a 53 registradas.
- Revisión de código (agente code-reviewer, misma sesión) y correcciones aplicadas: un pilote solo
  en su cabezal ya no cuenta como S/B<3 (estado `sin_vecino`, factor 1.0); el barrido de anillos
  recorre solo el perímetro y cae a fuerza bruta para puntos aislados (antes cúbico); el S/B del
  pilote es el de su pareja más desfavorable a menos de 6·Dmax (`pareja_s_b`), no la más cercana en
  distancia; capacidad de grupo solo en `by_footing` (el barrido global no es un grupo); `q_ult` y
  `q_adm` excluyentes; ratio comparado sin redondear y traccion pura sin "cumple"; longitudes de
  arreglos verificadas en GetNameList/GetCaseStatus; unidades restauradas aunque falle la lectura;
  `FrameForce` conserva la estación traccionada y el número de paso.
- Docs: README (catálogo y sección Pilotes), ENUMS-SAFE.md (eFramePropType, eItemTypeElm, firmas),
  BACKLOG (dos filas + `scan_sf_model` pendiente), `docs/PRUEBA-VIVA-PILOTES.md`.
- `config.json` 0.2.1 → 0.3.0.
- Corrida viva el mismo día (SAFE 23.3.0, modelo real de 847 frames / 561 pilotes, conexión COM
  directa con el código nuevo): `get_pile_spacing` **[H]** en ambos alcances, unidades restauradas,
  firmas de `GetAllFrames` / `PropFrame` confirmadas, 0.2-0.6 s por llamada. Con el análisis corrido
  (autorizado), `get_pile_axial_reactions` también **[H]** por `joint` y por `frame`: signo confirmado
  con el caso Dead (misma cifra por las dos vías), envolvente de 39 combos en 1.7 s. Tras la corrida:
  aviso de frames duplicados también en reacciones (se leen todos) y aviso de que `q_adm` es carga de
  servicio cuando se combina con todas las combos. 259 tests. Ver `docs/PRUEBA-VIVA-PILOTES.md`.
- Tercera tool (54 registradas): `export_pile_check_xlsx` — libro de verificación geometría + demanda +
  candidatos a eliminar. Nuevo `src/pilotes_xlsx.py` (puro; openpyxl solo al escribir, dependencia nueva
  en `requirements.txt`). Refactor: los cuerpos de `get_pile_spacing` y `get_pile_axial_reactions`
  pasan a `_informe_separacion` / `_informe_reacciones` para reutilizarlos. Lectura nueva
  `_combos_definidos` (`RespCombo.GetCaseList` + `LoadCases.GetTypeOAPI_1`, [H]): las combos se
  clasifican por sus miembros (patrón Quake/Wind o caso dinámico = lateral), no por el nombre.
  Tests: `tests/test_pilotes_xlsx.py` (6) y uno más en `test_pilotes_safe.py`; 266 verdes. Corrida viva
  el mismo día sobre el modelo analizado: 3 s, cifras idénticas al prototipo manual **[H]**.
- Cuarta y quinta tools (56 registradas): `suggest_pile_changes` (propuesta por cabezal: añadir /
  quitar / redistribuir / reespaciar / mantener; hoja Propuesta en el libro) y `trial_pile_changes`
  (ensayo en COPIA: copia, borra/añade pilotes copiando apoyos de punta, reanaliza, compara
  antes/después; el original no se guarda y se verifica su fecha). `proponer_cambios` y
  `comparar_verificaciones` en `pilotes_xlsx.py`. Getters de asignación tolerantes a ret=1 (sin
  asignación, visto en vivo con `PointObj.GetSpring`). 272 tests. Corrida viva: propuesta 557→546
  pilotes (19 cabezales "redistribuir"), ensayo de 12 borrados + 1 añadido en 30 s **[H]**.
- Corrección documental: `Analyze.RunAnalysis` GUARDA el modelo activo en disco antes de analizar
  (comprobado por la fecha del FDB). "Solo lectura" de las tools de pilotes sigue siendo cierto; lo
  que no es cierto es que correr el análisis deje el archivo intacto.
- Criterio doble en el libro, la propuesta y el ensayo: `seismic_combos` + `seismic_factor` (4/3).
  Las combos de gravedad (`service_combos`, p. ej. Comb2) se comparan con q_adm·ξ y las sísmicas
  (p. ej. la envolvente E / Envelope) con 4/3·q_adm·ξ; el ratio mayor manda. Columnas nuevas en
  Pilotes y Cabezales; conteos por causa en Resumen. 276 tests. Corrida viva 2026-11-03 sobre copia de
  un tercer modelo (897 pilotes, 158 cabezales): 6 s con dos combos seleccionadas (el tiempo depende
  de las combos de salida, no solo de los pilotes); `PRUEBA-VIVA-PILOTES.md`.
- Sexta tool (57 registradas): `assign_pile_groups` — un grupo de SAFE por cabezal (`CAB-<área>`,
  `GroupDef.SetGroup` + `SetGroupAssign` de área y pilotes, releído con `GetAssignments`), para
  revisar por grupo; `save=True` guarda (solo copia o con autorización). `cap_types` admite
  nombres de sección de área (`"Z50"`); hoja **Grupos** y columna "Grupo SAFE" en el libro.
  279 tests. Corrida viva 2026-11-03 sobre la copia del tercer modelo: 158 grupos, 897 pilotes, 15 s.
- Corrida de aceptación antes del PR sobre una copia de un segundo modelo (~1100 pilotes, 174
  cabezales) en instancia SAFE arrancada por COM: las cinco tools **[H]**; 114 pilotes con S/B < 3,
  igual que el conteo independiente del mismo día. Tiempos con 1112 pilotes: 88 s reacciones,
  126 s libro (fila de rendimiento en BACKLOG). El primer `run_analysis` tras `ApplicationStart`
  quedó colgado una vez (solver completo, casos "no corrido"); al relanzar, 74 s.
