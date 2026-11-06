# SAFE MCP — lote 2 sobre v0.2.1

Servidor MCP de CSI SAFE 23.3.0, OAPI 2.016. ProgID confirmado:
`CSI.SAFE.API.ETABSObject`. Fuente técnica: `docs/OAPI-SAFE-real.md`;
inventario ampliado: `docs/BACKLOG-HERRAMIENTAS.md`; enums y fuentes locales:
`docs/ENUMS-SAFE.md`.

El catálogo tiene **60 funciones implementadas: 59 tools registradas y una
[X] deshabilitada**. Son las 31 iniciales, las 18 del lote 1 de Claude, las
3 por tabla del lote 2 y las 8 de pilotes (2026-11-02/03, ver más abajo).
`set_area_points` fue retirada por Claude tras
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
| Pilotes [H] | `get_pile_spacing`, `get_pile_axial_reactions`, `export_pile_check_xlsx`, `suggest_pile_changes` (solo lectura); `trial_pile_changes`, `apply_pile_proposal`, `optimize_pile_removal`, `optimize_pile_addition` (escriben solo en una copia); `assign_pile_groups` (escribe grupos; guarda solo con `save=True`) | 9 |

## Pilotes: separación S/B y reacción axial, solo lectura [H] (claude, 2026-11-02)

`get_pile_spacing` mide la separación centro a centro entre pilotes y devuelve
S/B con el factor de reducción de capacidad axial de grupo de la **tabla 5.1 del
MOPC R-024** (S/B 6→1.0, 5→0.9, 4→0.8, 3→0.7). `get_pile_axial_reactions` da la
carga axial por pilote y combinación con la envolvente y el pilote crítico, que es
el control real (el pilote más cargado, no el promedio). Criterio en
`src/pilotes.py` (módulo puro, sin COM); lectura COM en el bloque PILOTES de
`src/Safe.py`; procedimiento de corrida viva en `docs/PRUEBA-VIVA-PILOTES.md`.

Vía elegida para leer frames: `FrameObj.GetAllFrames` (una llamada para todo el
modelo, con extremos y sección) + `PropFrame.GetNameList(PropType=9)` /
`GetTypeOAPI` / `GetCircle` para las secciones circulares. No se añade un
`get_frames` genérico ni se usan tablas: tres lecturas por tabla más parseo
de texto no mejoran nada frente a una llamada tipada. Las dos pasaron la
corrida viva del 2026-11-02 sobre un modelo real (847 frames, 561 pilotes, 39
combinaciones): signo de `JointReact.F3` y `FrameForce.P` confirmado con el caso
Dead por las dos vías (`docs/PRUEBA-VIVA-PILOTES.md`). `q_adm` es carga de
servicio: el ratio solo vale contra combinaciones de servicio, y la tool lo avisa.

Decisiones fijadas (todas declaradas en la salida JSON):

- Solo lectura: nunca `File.Save`. Unidades fijadas con `set_units` antes de leer
  y restauradas al terminar; la salida dice cuáles se usaron.
- Filtro de pilotes explícito: `sections="auto"` = todas las secciones circulares
  (tipo verificado con `GetTypeOAPI`, no por nombre) o lista de secciones;
  `diameter_mm` para secciones no circulares o mallas mixtas.
- Cabeza del pilote = extremo de Z mayor; frames inclinados usan su proyección en
  planta y quedan marcados. Pilotes duplicados en la misma coordenada se avisan y
  se excluyen; diámetros mezclados usan el mayor de la pareja (conservador).
- Vecino más cercano por grilla espacial (celda = 8Ø); el S/B del pilote es el de
  su pareja más desfavorable a menos de 6·Dmax (`pareja_s_b`), que con diámetros
  mezclados no es siempre la más cercana. `scope="by_footing"` agrupa por
  punto-en-polígono sobre las áreas de tipo Footing (`cap_types`), que es el grupo
  del R-024; la capacidad de grupo solo se calcula ahí. Un pilote solo en su
  cabezal queda `sin_vecino` con factor 1.0: no es "fuera de tabla".
- Tabla 5.1 sin interpolar por defecto (`step_down`, escalón inferior); `linear`
  disponible y declarado. S/B < 3 queda fuera de tabla: factor `null` con bandera.
- El factor reduce la capacidad **última**; `q_adm = q_ult·ξ / fs`. Si se pasa
  una `q_adm` ya calculada, la salida advierte que solo equivale si el FS no cambia.
- Capacidad del grupo = menor de (a) suma de últimas reducidas y (b) pila
  equivalente; (b) no sale de SAFE y se reporta **pendiente**: la tool nunca
  devuelve "cumple". Reporta cifra, elemento crítico y ratio; no propone cambios.
- Fixtures sintéticas (repo público): malla 3×3 a 2.25 m con Ø450 → S/B 5.00 y
  factor 0.90; pareja a 1.20 m → S/B 2.67 fuera de tabla.

### `export_pile_check_xlsx`: libro de verificación [H]

`export_pile_check_xlsx(path, q_adm | q_ult+fs, service_combos="auto", ...)` cruza
las dos lecturas anteriores (geometría por cabezal y reacciones por nudo de punta
sobre todas las combinaciones) y escribe un `.xlsx` con seis hojas: **Resumen**
(conformidad geométrica SÍ/NO con motivos, pilote crítico, conteos, (b) pendiente),
**Pilotes**, **Cabezales** (suma (a), demanda simultánea por combinación, ratio,
cuántos pilotes sobran), **Candidatos** a eliminar con motivo, **Combos** y
**Criterios**. Las combinaciones se clasifican por lo que contienen
(`RespCombo.GetCaseList` + `LoadCases.GetTypeOAPI_1`: un caso estático con patrón
Quake es lateral), no por el nombre; las puramente laterales son envolventes y no se
comparan, las mayoradas van solo de referencia. Criterio en `src/pilotes_xlsx.py`
(puro, openpyxl solo al escribir). Candidatos: por baja demanda (el cabezal queda
≤ `margen_candidato` de (a) con un pilote menos), por geometría (pareja con S/B < 3)
y por modelo (frames duplicados). Toda eliminación exige reanálisis; la hoja lo dice.
Nunca sobrescribe sin `overwrite=True` ni guarda el modelo. Corrida viva 2026-11-02:
3 s sobre 564 pilotes y 36 combinaciones, cifras idénticas al prototipo manual.
Incluye la hoja **Propuesta** (abajo).

**Criterio doble (gravedad / sismo).** Con `service_combos=["Comb2"]` y
`seismic_combos=["Envelope"]` (o `["E"]`), la combinación de gravedad se compara con la
admisible tal cual (q_adm·ξ) y la envolvente sísmica con `seismic_factor` × q_adm·ξ
(4/3 por defecto: aumento de un tercio para cargas transitorias). Un pilote o cabezal no
cumple si falla cualquiera de las dos; el libro trae las dos columnas (P, combo y ratio
de gravedad y de sismo) y el ratio mayor manda en estado, candidatos y propuesta. Una
combinación envolvente (miembros que son combos) solo se lee si se indica así; de lo
contrario queda fuera como "no se compara". Los mismos parámetros existen en
`suggest_pile_changes` y `trial_pile_changes`.

**Cabezales por sección y grupos de SAFE.** `cap_types` admite, además de tipos de losa
(`footing`, `mat`), nombres de sección de área (`"Z50"`): cada token que no sea un tipo se
toma como sección y debe existir en el modelo. `assign_pile_groups(cap_types="Z50",
save=False)` crea en SAFE un grupo por cabezal, `CAB-<área>`, con el área y sus pilotes
(y los nudos con `include_points=True`), releyendo cada grupo con `GroupDef.GetAssignments`;
los mismos nombres van en la hoja **Grupos** y en la columna "Grupo SAFE" del libro, para
revisar cabezal a cabezal (Select > Groups) en vez de pilote a pilote. Los grupos son datos
del modelo: sin `save=True` se pierden al cerrar; `save=True` llama `File.Save` (solo sobre
copia o con autorización). Corrida viva 2026-11-03: 158 grupos y 897 pilotes en 15 s.

### Aplicar la propuesta en copia: `apply_pile_proposal` y `optimize_pile_removal`

`apply_pile_proposal(copy_path, q_adm, acciones=["quitar","anadir","modelo"], s_min_d=5,
s_fallback_d=0)` generaliza el ensayo: toma la hoja Propuesta del modelo activo, copia el
FDB, borra los candidatos de baja demanda y los frames duplicados, coloca los pilotes que
faltan dentro del área del cabezal (`pilotes.colocar_pilotes`: malla de candidatos a
≥ `borde_d` del borde, elegidos lo más lejos posible de los existentes, a ≥ `s_min_d`
diámetros y, si no caben, a `s_fallback_d`), reanaliza y compara antes/después. Lo que no
cabe o es "redistribuir"/"reespaciar" se reporta en `no_automatizado`.

**Lección de la corrida 2026-11-03 (tercer modelo):** aplicar "quitar" en bloque, aunque
cada cabezal siga cumpliendo por suma (a), **empeoró** el modelo: 275 pilotes menos y los
que no cumplen subieron de 136 a 246, porque la carga se redistribuye hacia los pilotes de
borde. Por eso existe `optimize_pile_removal(copy_path, q_adm, max_iter=6, por_iteracion=1)`:
quita un pilote por cabezal y por iteración, partiendo cada vez de una copia nueva de la
base, reanaliza y verifica; en cuanto un pilote del cabezal deja de cumplir, o su suma (a)
pasa de 1, ese cabezal se congela y su última quita se revierte. Termina dejando la copia
en la última configuración válida y el libro de esa configuración. Cada iteración es un
análisis completo. Las posiciones de pilotes nuevos son propuestas: las fija el ingeniero.

### Densificar hasta cumplir pilote por pilote: `optimize_pile_addition`

`optimize_pile_addition(copy_path, q_adm, max_iter=8, pasos=["5i","4i","5a","4a","3i"],
borde_d=1, holgura_d=2)` es la fase que faltaba: parte del modelo activo (normalmente la copia
ya reducida por `optimize_pile_removal`) y, en cada iteración, busca **una posición nueva junto
a cada pilote que no cumple** (peor ratio primero) siguiendo `pasos`: dentro del cabezal a 5 D
(`5i`), a 4 D (`4i`), **ampliando el cabezal** a 5 D (`5a`: `pilotes.extender_lado` mueve el
lado más cercano hacia fuera lo justo para que el pilote quepa con margen, y
`_ampliar_cabezal` desplaza sus dos vértices con `EditGeneral.Move`), ampliando a 4 D (`4a`) y,
por último, dentro a 3 D (`3i`, factor 0,7). Toda posición queda a ≥ s D de todos los pilotes
y a ≥ `borde_d` D del borde; una ampliación no puede invadir otro cabezal (`holgura_d` D) ni
mover un vértice conectado a otro objeto (`PointObj.GetConnectivity`). Cada iteración copia
de nuevo la base, reaplica lo aceptado más lo nuevo, reanaliza y verifica: el cabezal cuyo
número de fallos o ratio máximo no mejora se congela y sus cambios se descartan. Termina
cuando ningún pilote falla (`cumple_todo`), cuando no hay posición para ninguno o en
`max_iter`; deja la copia con lo aceptado y el libro. Lo que no se automatiza: reubicar los
pilotes existentes en malla uniforme y decidir hasta dónde puede crecer un cabezal.

### `suggest_pile_changes` y `trial_pile_changes`: proponer y ensayar en copia [H]

`suggest_pile_changes` devuelve, por cabezal, cuántos pilotes exige la demanda con la
suma (a) y el margen (`n_min` con el factor actual y con malla de 5 diámetros) y una
acción: **añadir**, **quitar** (los menos cargados), **redistribuir** (la suma cumple
pero hay pilotes individualmente sobrecargados: el problema es la distribución, no el
número, y no se quita nada), **reespaciar** (pareja con S/B < 3) o **mantener**. Es la
hoja Propuesta del libro. Sugerencia por capacidad (a): exige reanálisis y decisión del
firmante; quitar pilotes sube la tracción de los que quedan.

`trial_pile_changes(copy_path, q_adm, delete_frames, add_piles, xlsx_path)` es el
reanálisis: toma la verificación del modelo activo como base, copia el FDB, abre la
copia, borra frames (`FrameObj.Delete`), añade pilotes (`AddByCoord` entre la Z de
cabeza y de punta de un pilote de referencia, copiando su restricción y resortes de
punta y de línea), corre el análisis, verifica de nuevo y devuelve antes/después por
cabezal y global (ratios, crítico, tracción máxima, cabezales que mejoran o empeoran).
Guardas: nunca escribe si el modelo activo no es la copia; el original no se guarda y
se comprueba su fecha en disco al final. **Atención:** `run_analysis` de SAFE guarda el
modelo activo en disco antes de analizar; por eso el ensayo solo analiza la copia, y
por eso analizar el original (como se hizo el 2026-11-02 con autorización) sí lo
reescribe aunque no cambie nada. Corrida viva: 30 s con 12 borrados y 1 añadido.

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
cubre las tres nuevas, ret, errores de Apply, preservación y relectura;
`test_pilotes.py` prueba el criterio R-024 sobre fixtures sintéticas y
`test_pilotes_safe.py` la capa COM de las dos tools de pilotes.
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
