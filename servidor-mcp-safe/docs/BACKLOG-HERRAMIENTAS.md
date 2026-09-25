# CDX: SAFE-MCP, inventario y backlog de herramientas

Fecha: 2026-09-25. Responsable: Codex <codex@aiq>. Encargo: `_coordinacion/buzon/204-claude.md` (claude-204); respuesta: codex-205. Alcance completado: FASE 0. No se modificó código ejecutable, sesión SAFE, modelo FDB ni `servidor-mcp` de ETABS.

**Estado vigente al cierre:** el inventario principal conserva el corte solicitado v0.1.0 (31 tools). Durante la tarea Claude entregó v0.2.0 con 18 tools adicionales (49 registros en disco), aún [T], y anuló el lote 1 para Codex en claude-208. La actualización al final prevalece sobre la propuesta de lote 1; no duplicar ese trabajo. Los cambios ejecutables de Claude no forman parte del commit documental de Codex.

## Corte y fuentes

Rutas relativas a `C:\Users\emilg\Artificial IQ`, salvo indicación. Las referencias `Safe.py:L` y `server.py:L` son de `CDCRD-Digital/servidor-mcp-safe/src/` al corte `fb71f65` de CDCRD-Digital. Hay **31 registros `mcp.tool()`**, no 31 herramientas probadas. `config://app` es un recurso y no se cuenta.

| Ref. | Fuente consultada | Alcance de la evidencia |
|---|---|---|
| S | `C:\Users\emilg\Documentos\02 TRABAJO_INGENIERIA\TRABAJO\_RECURSOS\Pasos.pdf` | Texto pp. PDF 23–51 y capturas del procedimiento. La ruta escrita por Emil con `02 TRABAJO\_INGENIERIA` se resolvió al directorio existente `02 TRABAJO_INGENIERIA`. |
| C | `CDCRD-Digital/servidor-mcp-safe/src/Safe.py`, `src/server.py`, `src/oapi.py` | Implementación, registro y tratamiento de retornos, leídos sin importar módulos ni invocar COM. |
| R | `CDCRD-Digital/servidor-mcp-safe/README.md` | Mezcla la descripción inicial no verificada con resultados del 2026-08-10; prevalece la evidencia posterior por operación. |
| H | `CDCRD-Digital/docs/HUECOS-ETABS-SAFE.md`, secciones SAFE S-1 a S-4 y Estado de implementación | Firmas y pruebas históricas. No se modificó la sección ETABS. |
| B | `BRAIN/03_APPS/2026-08-10 SAFE-MCP - primera corrida real SERRALLES II, ETABS pendiente.md` | Corrida sobre fundación SERRALLES II: 22 franjas, 186 posiciones, 396 estaciones, 13 puntos de punzonamiento; timeout de presión de suelo. |
| L | `CDCRD-Digital/servidor-mcp-safe/src/safe_mcp.log` | Conexiones OAPI 2.016; líneas 20, 55, 64, 70, 96, 162, 885 y 2036 al corte. Los `CallToolRequest` no indican nombre, argumentos ni resultado: no acreditan éxito por tool. |
| T | `C:\Users\emilg\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\comtypes\gen\_2406CB05_79B9_49C2_8684_CC7A67F5B12E_0_1_0.py` | Lectura **estática** del wrapper importado por `SAFEv1.py`; `typelib_path` apunta a `C:\Program Files\Computers and Structures\SAFE 23\NativeAPI\x64\SAFEv1.tlb`. Es candidato de contrato; no sustituye `describe_oapi` de la sesión. |
| X | `C:\Program Files\Computers and Structures\SAFE 23\Table and Field Keys.xml` | Catálogo instalado, declara producto SAFE, versión 23.3.0. Acredita nombres/campos, no disponibilidad ni editabilidad en el modelo abierto. |
| W | [CSI Developer](https://www.csiamerica.com/developer), [SAFE Enhancements](https://www.csiamerica.com/products/safe/enhancements) | CSI documenta la API compartida y export/import de F2K/tablas desde 22.4; no aporta contrato específico de cada método de esta sesión. |
| K | `CDCRD-Digital/servidor-mcp-safe/docs/OAPI-SAFE-real.md`, `docs/CSI-API-SAFE-v1-paginas-clave.md`, `_coordinacion/buzon/206-claude.md` | Entrega de Claude recibida durante FASE 0: documentación oficial y typelib compartido CSiAPIv1. Distinguir [T] de prueba funcional. |

El manifiesto adjunto `FUENTES-FASE0.json` fija SHA-256, tamaño y fecha de las fuentes locales, conteo de tools y resumen del log. No se abrió el CHM ni se ejecutó SAFE para obtener estos datos; la OAPI se leyó como texto del wrapper y catálogo instalados.

**Actualización al cierre:** Claude entregó K y la extracción del CHM en paralelo. K usa el typelib compartido CSiAPIv1, más amplio que T (SAFEv1). Por eso T muestra EditGeneral.Move solamente y EditPoint vacío, mientras K enumera ReplicateLinear, ChangeCoordinates y ChangeConnectivity. Las ausencias en T de las tablas de este documento **no son ausencia definitiva en el objeto COM activo**: para FASE 2 se usará el contrato que confirme Claude en ese objeto. K todavía deja pendientes tablas Strip/Punch por caída de conexión. Emil informó después que volvió a abrir SAFE; falta relectura de conexión/modelo por Claude.

Emil confirmó en esta tarea: **SAFE 23 ya tiene el proyecto abierto**. Aportó la referencia `C:\Users\emilg\Documentos\02 TRABAJO\_INGENIERIA\TRABAJO\PROYECTOS\2026\12-HOSPITAL MUNICIPAL EL VALLE`. Esto no prueba el nombre del FDB activo. Claude debe registrar `get_model_info` al iniciar su FASE 1 y trabajar sobre copia `_pruebas-mcp.FDB` para las pruebas de escritura. Codex no inspeccionó ni modificó el FDB.

## Convenciones de estado y páginas

- **verificada en vivo**: existe evidencia histórica explícita, citada por fila. Se limita al caso probado; una firma introspectada por sí sola no acredita que una escritura funcionó. Todo lote nuevo necesita otra corrida de Claude.
- **conjetura marcada en código**: implementación presente sin prueba funcional trazable, apoyada en marcas de método/sección o en la advertencia general de `Safe.py:1–35`. Cuando el contrato fue sondeado pero la ejecución no está acreditada se indica. No significa que el método no exista.
- **no existe**: falta la tool dedicada o la ampliación indicada. Puede haber un método OAPI o un lector parcial ya disponible.
- Prioridad **1**: cubre la brecha reportada que hoy deriva a `computer_*`, o es prerrequisito para cerrarla. **2**: útil. **3**: exploración. La prioridad no implica viabilidad confirmada.

Las páginas siguientes son **ordinales PDF, base 1**. En el ejemplar encontrado, `Safe` empieza en **p. 24**, no 23: p. 23 todavía es ETABS. Las referencias históricas a p. 34/37/46/49 suelen estar desplazadas una página. Se conserva el número de paso impreso; el texto extraído salta de 3.10 a 3.12, por lo que no se inventa un título para 3.11.

| Paso SOP | Páginas PDF | Operación |
|---|---|---|
| 1 | 24–29 | Transferencia ETABS→SAFE; hay operaciones del lado ETABS fuera de este encargo. |
| 2; 3 materiales | 30–31 | Visualización de joints, unidades ton/m, materiales. |
| 3 combinaciones; 3.1–3.3 | 32–34 | Modificar DL, combinaciones, edición de tablas y pegado desde Excel. |
| 3.4 | 35–36 | Propiedades de zapata y elementos de apoyo. |
| 3.5 | 37 | Tamaños de barras; no equivale a definir solo el material de acero. |
| 3.6 | 38 | Propiedad del resorte de suelo. |
| 3.7; 3.8 | 39–40 | Recubrimientos; opciones de modelación/análisis. |
| 3.9; 3.10 y continuación | 41–43 | Dibujar áreas; asignar suelo. |
| F5; 3.12; 3.13 | 44–45 | Análisis, presión de contacto y punzonamiento. |
| 3.14; 3.15 | 46–48 | Pedestal, franjas; capturas de overwrites por franjas y por elementos finitos. |
| 3.16; 3.17 | 49; 50–51 | Verificar acero; exportar DXF con capas y unidades. |

## Inventario de las 31 tools registradas

El prefijo de Claude Desktop es `safe__`. Se omite para facilitar comparación con `server.py:47–97`.

| Tool | Paso del SOP que cubre | Estado | Prioridad | Evidencia y límite actual |
|---|---|---|---|---|
| `get_model_info` | Previo al 1 | verificada en vivo | 2 | K §6: segunda conexión a SAFE 23.3.0 y ruta del FDB de EL VALLE, informadas por Claude. |
| `get_units` | 2, p. 30 | conjetura marcada en código | 2 | C:254; B reporta N-mm, sin atribuir salida a esta tool. |
| `set_units` | 2, p. 30 | conjetura marcada en código | 2 | C:263; falta relectura de unidades tras invocación. |
| `save_model` | Respaldo previo a 3.9 | conjetura marcada en código | 1 | C:277; falta evidencia por tool; prerrequisito de pruebas de escritura. |
| `refresh_view` | 2 y control visual | conjetura marcada en código | 2 | C:290; no verifica retorno de `RefreshView`. |
| `describe_oapi` | Fuera del SOP: diagnóstico | verificada en vivo | 1 | R/H transcriben firmas obtenidas con esta tool. No acredita setters. |
| `get_points` | 2; apoyo a 3.9 | conjetura marcada en código | 1 | C:320; lectura sin validar el último retorno; base para relectura geométrica. |
| `get_areas` | 3.9 y 3.12 | conjetura marcada en código | 1 | C:328; C ignora `_ret`; falta prueba por tool, aunque B contiene geometría exportada. |
| `create_area_by_coordinates` | 3.9, p. 41; 3.14 | conjetura marcada en código | 1 | C:343; creación implementada, sin prueba trazable de contorno y asignaciones. |
| `define_concrete_material` | 3 materiales, pp. 30–31 | conjetura marcada en código | 2 | C:366; variantes `SetMaterial`/`SetOConcrete*`, confirmar valores y unidades. |
| `define_rebar_material` | 3 materiales; apoyo 3.5 | conjetura marcada en código | 2 | C:415; define material, no catálogo de diámetros/áreas de barras. |
| `define_slab_section` | 3.4; 3.14, pp. 35–36/46 | conjetura marcada en código | 1 | C:460; enum Footing discrepante con T, ver hallazgo F0-01. |
| `define_soil_spring` | 3.6, p. 38 | conjetura marcada en código | 1 | C:501; firma confirmada en H S-4; enum CompressionOnly aún inferido. B lee un resorte existente, no prueba este setter. |
| `assign_area_spring` | 3.10, pp. 42–43 | conjetura marcada en código | 1 | C:547; firma confirmada H S-4; falta lectura posterior de una asignación nueva. |
| `add_load_pattern` | 3.1 y cargas | conjetura marcada en código | 1 | C:576; pasa `load_type` string: contrastar enum real y comportamiento si existe. |
| `add_load_combo` | 3.2–3.3, pp. 32–34 | conjetura marcada en código | 1 | C:586; `combo_type` no se usa; prueba caso/combo como variantes semánticas. Debe resolver tipo antes de escribir. |
| `run_analysis` | F5, p. 44 | verificada en vivo | 2 | B: análisis+diseño sobre SERRALLES II. Timeout del cliente no cancela COM. |
| `get_analysis_status` | F5, p. 44 | verificada en vivo | 2 | K §6: 6 casos Dead/Live/LiveT/Qx/Qy/~LLRF, ninguno corrido, en EL VALLE. |
| `run_slab_design` | 3.16, p. 49 | verificada en vivo | 2 | B: corrida seguida de 186 posiciones de diseño OK. |
| `get_slab_design_summary` | 3.16, p. 49 | verificada en vivo | 1 | B: 186 posiciones; salida textual, sin filtro ni As provista explícita. |
| `get_slab_design_detail` | 3.16, p. 49 | verificada en vivo | 1 | B: 396 estaciones, As sup/inf y mínima, coordenadas; no confundir mínima con provista. |
| `get_design_strips` | 3.15, p. 47 | verificada en vivo | 1 | B: 22 franjas; C:704 solo imprime primeros anchos, no geometría completa. |
| `get_span_definitions` | 3.15–3.16 | verificada en vivo | 2 | H, Estado S-3 declara probado; no documenta conteo individual de tramos. |
| `get_punching_check` | 3.13, p. 45 | verificada en vivo | 1 | B: 13 puntos; 1056 ratio 1.029, 872 sin calcular. C:802 sin filtro por objeto; busca cualquier tabla que contenga Punch. |
| `get_soil_pressure` | 3.12, pp. 44–45 | verificada en vivo | 2 | **Prueba fallida por timeout**, no verificación funcional: B, 1.38 M filas. La extracción que funcionó fue export tipo 4 + parseo. |
| `probe_file_types` | 1; exploración 3.17 | verificada en vivo | 3 | H/B: F2K=1; tipos 6–20 sin archivo. No repetir sonda a ciegas; cotejar prefijos para no confundir 1 con 10. |
| `list_tables` | 3.2–3.3; 3.12–3.13 | verificada en vivo | 1 | R/H: retorno de 5 valores corregido tras prueba. |
| `get_table_data` | 3.2–3.3; 3.12–3.13 | verificada en vivo | 1 | R/H/B: lectura de tablas pequeñas; paginación solo recorta salida, trae toda la tabla por COM. |
| `set_table_data` | 3.3, p. 33 | conjetura marcada en código | 1 | C:940/R: tuple corregida; faltan readback y prueba de persistencia. `n_errmsg>0` no impide mensaje de escritura. |
| `import_file` | 1, pp. 24–29 | conjetura marcada en código | 1 | C:984 declara pendiente import de F2K real de ETABS; significado `import_type=0` no confirmado. |
| `export_file` | 1 y extracción de resultados | verificada en vivo | 1 | H/B: F2K tipo 1 y texto tipo 4. **No DXF**. C:1060 no verifica archivo producido: riesgo E-036. |

## Backlog mínimo de claude-204

Los nombres propuestos son contratos MCP de trabajo; no se presume un método homónimo en la OAPI. Las ampliaciones de tools existentes se separan de sus casos ya probados.

| Tool / ampliación | Paso del SOP que cubre | Estado | Prioridad | Contrato pendiente / vía candidata |
|---|---|---|---|---|
| `move_objects` | 3.9; corrección 3.12 | no existe | 1 | T: `EditGeneral.Move(DX,DY,DZ)` actúa con selección; confirmar `SelectObj` y restaurar selección, controlar puntos compartidos y relectura. |
| `delete_object` | 3.9; correcciones | no existe | 1 | `AreaObj.Delete`, `FrameObj.Delete`; `PointObj.DeleteSpecialPoint` no es un Delete general. Lista explícita de tipos admitidos y dependencias. |
| `copy_object` | 3.9; ampliación de zapatas | no existe | 1 | T no tiene Copy/Replicate; K sí expone EditGeneral.ReplicateLinear como [T]. Confirmar firma y ejecución sobre copia, devolver relación origen/copia y asignaciones preservadas. |
| `set_area_section` | 3.4; 3.14 | no existe | 1 | T: `AreaObj.SetProperty/GetProperty`; devolver sección anterior y relectura, evitar modificar otras áreas que comparten propiedad. |
| `set_area_offset` | 3.9; 3.14 | no existe | 1 | T tiene GetOffsets3 sin setter; K expone SetOffsets [T]. Alternativa X: Area Assignments - Insertion Point; confirmar cardinal point, sistema y offsets por vértice. |
| `edit_area_points` / `set_area_points` | 3.9; 3.12 | no existe | 1 | T es limitado; K confirma nombre EditArea.ChangeConnectivity [T]. X: conectividad Floor/Point. Preservar identidad/asignaciones y validar polígonos >4 vértices. |
| `define_footing_section` | 3.4, pp. 35–36 | no existe | 1 | Especializar/corregir `define_slab_section`; validar enum con `PropArea` y leer `GetSlab` tras crear. No usar Footing=3. |
| `get_punching_params` | 3.13, p. 45 | no existe | 1 | Leer por punto las tablas General/Perimeter/Openings de overwrites, diferenciando defaults de valores explícitos. |
| `set_punching_params` | 3.13, p. 45 | no existe | 1 | Escribir solo campos confirmados de esas tablas; conservar resto del objeto, invalidar resultados de diseño y releer. |
| `get_punching_check(point_ids/area_ids)` | 3.13, p. 45 | no existe | 1 | Ampliación del lector probado; tabla exacta de resultados, todos los registros seleccionados, estado no calculado separado de OK. Área→punto por conectividad; bbox solo sería asociación aproximada declarada. |
| `punching_reinforcement` | Extensión de 3.13 | no existe | 1 | X: General tiene RebarType/Pattern/Fy/Dia/Spacing; resultados tienen ReinfType/NumRails/StudPerRail. Confirmar enums de studs/estribos y distinguir configuración de refuerzo calculado. |
| `add_design_strip` | 3.15, p. 47 | no existe | 1 | X: `Strip Object Connectivity`; T no tiene Add en DesignStrip. Confirmar edición por tabla, Layer, segmentos y puntos existentes. |
| `set_design_strip_width` | 3.15, p. 47 | no existe | 1 | Misma tabla: WStartLeft/Right, WEndLeft/Right, AutoWiden; releer todos los segmentos con `GetDesignStrip_1`. |
| `get_strip_forces` | 3.15–3.16 | no existe | 1 | X: `Strip Forces` y summaries. Seleccionar casos/combos, estación, capa, P/V2/T/M3, unidades y ejes; no sustituir por momentos de diseño envolventes. |
| `get_strip_rebar` | 3.16, p. 49 | no existe | 1 | Reusar resultados de detalle para As req/min sup/inf. As provista requiere fuente independiente (objetos de acero); si falta, devolver no disponible, nunca req=min=prov. |
| `set_rebar_overrides` | 3.7; 3.16 | no existe | 1 | X: overwrites Strip Based y Finite Element Based. Son recubrimiento/material/modo; no asumir que incluyen cuantía provista. Configuración de barras colocadas va aparte. |
| `add_point_load` | Cargas; apoyo pasos 1/3.1 | no existe | 1 | T: `PointObj.SetLoadForce/GetLoadForce`; 6 componentes, sistema, patrón, reemplazo/acumulación explícitos. |
| `add_area_load` | Cargas; apoyo 3.1/3.9 | no existe | 1 | T: `AreaObj.SetLoadUniform/GetLoadUniform`; dirección y signo confirmados, no deducir de la vista. |
| `assign_frame_load` | Cargas de vigas/muros; extensión | no existe | 1 | T: `FrameObj.SetLoadDistributed/SetLoadPoint`, getters; distribución, longitudes relativas/absolutas y reemplazo explícitos. |
| `get_load_cases` | 3.1–3.3 y F5 | no existe | 1 | T: `LoadCases.GetNameList/GetTypeOAPI*`; no confundir patrones, casos y combinaciones. |
| `export_dxf` | 3.17, pp. 50–51 | no existe | 1 | Bloqueado por vía nativa observada: T solo ExportFile con enum 1–5. Investigar salida DXF propia desde datos confirmados, con alcance distinto del detallado nativo; no inventar tipo 6. |
| `export_f2k` | 1; respaldo/intercambio | no existe | 1 | Alias específico sobre export_file tipo 1, ya probado; exigir archivo nuevo/no vacío y cabecera esperada. |
| `import_f2k` + verificar importación | 1, pp. 24–29 | no existe | 1 | Alias de import_file, import aún sin corrida. Confirmar parámetro Type, importar en copia y cotejar geometría/cargas/combos/unidades contra origen. |
| `get_displacements` | Extensión: servicio de losas/plateas | no existe | 2 | T: `Results.JointDispl` + `Results.Setup`; caso/paso, coordenadas, unidades y filtro por objeto/elemento. |
| `get_reactions` | Extensión: equilibrio/apoyos | no existe | 2 | T: `Results.JointReact/BaseReact`; X: Integrated Wall Reactions; separar reacción puntual, integrada de muro y global. |
| `get_soil_pressure(area_ids, cases)` | 3.12, pp. 44–45 | no existe | 2 | Ampliación viable candidata: X `Soil Pressures Summary`/`Enveloping Summary`. Mapear SlabPanel↔Area explícitamente; no bajar 1.38 M filas para filtrar después. |
| `set_analysis_options` (uplift/no lineal) | 3.8, p. 40; extensión plateas | no existe | 2 | Separar opciones globales de caso, no linealidad del apoyo y fisuración. T: Analyze/Options/LoadCases.StaticNonlinear; X tablas de caso. |
| `import_load_combos_from_excel` | 3.1–3.3, pp. 32–34 | no existe | 2 | Parser local de plantilla de firma + validación de casos/factores, vista previa, idempotencia y readback con RespCombo o tablas; ruta/hoja/versión aún por identificar. |
| `get_slab_stresses` | Extensión: losas/plateas/PT | no existe | 2 | T: `Results.AreaStressShell/AreaStressShellLayered`; cara sup/inf, ejes locales y casos. No equivale al chequeo de tensiones admisibles de diseño PT. |

## Ampliación más allá del SOP, sustentada en OAPI/catálogo de SAFE 23

Todo este apartado es **candidato estático** pendiente de confirmación FASE 1; una interfaz compartida puede devolver no soportado en SAFE. No se promete diseñar escaleras o muros de sótano por el mero nombre de una interfaz.

| Tool propuesta | Paso del SOP que cubre | Estado | Prioridad | Fuente y uso en trabajos de la firma |
|---|---|---|---|---|
| `get_tendons` | Fuera del SOP: losas postensadas | no existe | 2 | T: TendonObj.GetNameList/GetTendonGeometry/GetNumberStrands/GetDatumOffset; inventario y trazado 3D verificable. |
| `define_tendon_property` | Fuera del SOP: PT | no existe | 2 | T: PropTendon.GetProp/SetProp; material y área por torón. Lectura posterior obligatoria. |
| `get_tendon_loads_losses` | Fuera del SOP: PT | no existe | 2 | T: GetLoadForceStress_1/GetLossesDetailed/Fixed/Percent; esfuerzo de tesado y pérdidas por tendón, sin confundir transferencia con estado final. |
| `add_tendon` / `set_tendon_profile` | Fuera del SOP: PT | no existe | 3 | TendonObj de T no tiene setters geométricos. X: Tendon Object Connectivity, numerosos campos de perfil; primero confirmar importabilidad y forma de múltiples registros. |
| `set_tendon_jacking_losses` | Fuera del SOP: PT | no existe | 3 | X: Tendon Load Assignments - Jacking Stress / Loss Options. Confirmar compatibilidad de método de pérdidas y unidades. |
| `get_pt_stress_checks` | Extensión de 3.16: PT | no existe | 2 | X: Concrete Slab Design - Flexural Stress Check - Transfer / Normal / Long Term; combos, caras, capacidad y ratio de tensión. |
| `get_tendon_elongations` | Fuera del SOP: control PT | no existe | 2 | X: clave literal `Tendon  - Total Elongation` (dos espacios); fuerzas y elongación en ambos extremos. |
| `define_mat_section` | Extensión de 3.4: plateas | no existe | 2 | T: eSlabType_Mat=5, PropArea.SetSlab/GetSlab. Diferenciar Mat de Footing y el espesor de cada zona. |
| `get_soil_spring` / `set_soil_spring_stiffness` | Extensión de 3.6: plateas/uplift | no existe | 2 | T: PropAreaSpring.GetAreaSpringProp/SetAreaSpringProp; entrada k explícita fuerza/longitud³, componente y no linealidad; separar de sigma admisible. |
| `get_uplift_contact` | Extensión de 3.12: plateas | no existe | 2 | Derivar de presiones y desplazamientos confirmados por combo/paso con convención de signo y tolerancia explícitas; no inferir porcentaje de área sin geometría/pesos de integración. |
| `set_mesh_options` | 3.8; plateas/muros | no existe | 2 | X: Analysis Options - Automatic Mesh Settings for Floors / Automatic Rectangular Mesh Options for Walls; tablas de asignación por área; control de convergencia entre mallas fuera del setter. |
| `get_long_term_deflections` / `set_cracked_analysis` | Fuera del SOP: losas/PT/plateas | no existe | 2 | T: LoadCases.StaticNonlinear/StaticNonlinearStaged; X: CrackedOpt, LongTermOpt, AgeAtLoad, CreepCoeff, ShrnkStrain; resultados JointDispl. Confirmar qué opciones SAFE admite. |
| `define_wall_section` | Extensión de 3.4: muros de sótano | no existe | 2 | T: PropArea.SetWall/GetWall; X: Wall Property Definitions - Specified, Wall Object Connectivity; no implica verificación normativa del muro. |
| `assign_area_pressure` | Fuera del SOP: empuje de sótano | no existe | 3 | Investigar tabla/contrato para presión variable lateral y ejes. `SetLoadUniform` solo cubre uniforme; no presentarlo como empuje triangular automático. |
| `get_wall_forces` | Fuera del SOP: muros de sótano | no existe | 2 | T: Results.AreaForceShell/PierForce; X: Integrated Wall Reactions. Resultantes, ejes y conectividad antes de resumir por muro. |
| `create_inclined_slab` | Extensión de 3.9: escaleras/descansos | no existe | 3 | Basarse en AreaObj.AddByCoord 3D, GetPoints y conectividad; confirmar soporte de área inclinada, malla y diseño en SAFE. T marca Ramp_DO_NOT_USE: no usar ese enum como habilitación. |
| `get_local_axes` / `set_local_axes` | Extensión de 3.9/3.16: muros y escaleras | no existe | 2 | T: AreaObj.GetLocalAxes/SetLocalAxes/GetTransformationMatrix; interpretar esfuerzos/acero longitudinal y transversal. |
| `set_area_opening` | Extensión de 3.9/3.13: escaleras/huecos | no existe | 2 | T: AreaObj.SetOpening/GetOpening; hueco geométrico y abertura para punzonamiento son conceptos distintos. |
| `get_rebar_sizes` / `define_rebar_size` | 3.5, p. 37 | no existe | 2 | T: PropRebar.GetNameList/GetRebarProps, sin Set; X: Reinforcing Bar Sizes (Name, Diameter, Area, GUID). Confirmar edición de catálogo. |
| `get_provided_rebar` / `set_provided_rebar` | Extensión de 3.16: acero colocado | no existe | 2 | X: Slab Rebar Object Geometry / Slab Rebar Property Assignments (RebarSize, Material, BarNumType, TotalBars, MaxSpacing). Determinar unidades, solapes y anchos de reparto antes de asociar As provista a una franja. |

## Hallazgos y prerrequisitos técnicos

**F0-01, enum de sección:** `Safe.py:478` mapea Footing=3 y Stiff=2. T:80–87 declara Slab=0, Drop=1, Stiff_DO_NOT_USE=2, Ribbed=3, Waffle=4, Mat=5, Footing=6. Una llamada puede devolver cero y crear un tipo distinto. Prioridad 1: confirmar con Claude el contrato y `GetSlab`; corregir en lote 1, sin cambiarlo en FASE 0.

**F0-02, export/import:** T:33–38 sí contiene nombres del enum `eFileTypeIO` (TextFile=1; tablas Excel=2, Access=3, Text=4, XML=5). La afirmación histórica de que el typelib no tiene nombres no aplica a este wrapper. No aparece DXF. `File.ImportFile(..., Type)` conserva un entero sin significado demostrado. El tamaño/cabecera/mtime del archivo producido deben verificarse: `ret=0` no basta (B/E-036). La cuenta de métodos de cFile difiere entre H (13) y este wrapper (8 propios): pedir sondeo sin filtro, no extrapolar.

**F0-03, edición por tabla:** `set_table_data` no trata `n_errmsg>0` como fallo ni relee. Antes de basar franjas/punzonamiento en él: confirmar campos editables, leer tabla original, preservar filas y campos ajenos, validar claves y anchos de fila, aplicar, devolver ImportLog/advertencias y comparar lectura posterior. No asumir que ApplyEditedTables ofrece transacción/rollback del modelo. Si hay error parcial, informar qué cambió; no reintentar otra variante que duplique escrituras.

**F0-04, retorno desconocido:** `oapi.call` acepta `ret_code(...) is None` como éxito (oapi.py:129–132), pese al docstring de `call_checked`. Planificar endurecimiento compatible con fixtures reales; para escrituras nuevas exigir retorno conocido cero y readback. No construir tests que legitimen un retorno desconocido.

**F0-05, resultados y escala:** los lectores actuales retornan texto y no metadatos de unidades/estado/caso suficientes para composición. `get_table_data` obtiene toda la tabla y luego corta a 100 filas. Seleccionar tablas pequeñas, filtrar en OAPI cuando esté confirmado, indicar truncamiento y total. `Soil Pressures Summary` (X) es candidata, no solución ya probada. No mapear SlabPanel a UniqueName por igualdad supuesta.

**F0-06, suelo:** el código multiplica sigma admisible por 1.2 y llama ese valor k. El propio contrato documenta sigma como fuerza/longitud², mientras k exige fuerza/longitud³; ese factor requiere convención dimensional del procedimiento. No aplicar la relación como conversión universal entre unidades. Exponer k explícito y separar sigma admisible del análisis. No fijar un valor del estudio geotécnico inexistente en los datos (B).

**F0-07, documentación temporal:** README y cabeceras aún dicen que no hubo instalación real, y describen huecos ya parcialmente cubiertos. Actualizar por lote la evidencia concreta, sin borrar historia ni convertir firmas sondeadas en pruebas funcionales. No trasladar reglas del SOP a decisiones automáticas de dimensionamiento.

## Solicitud a Claude: FASE 1 en docs/OAPI-SAFE-real.md

Ese archivo pertenece a Claude y **no fue creado por Codex**. Registrar fecha, SAFE/build/OAPI, ruta activa obtenida con `get_model_info`, unidades, estado locked, y salida literal de `describe_oapi` (incluyendo `py-> (...)`, tipos, valores por defecto). Empezar por raíz `path=""` sin filtro para resolver nombres. El acceso es bajo SapModel: `DesignStrip` es **DesignConcreteSlab.DesignStrip**, no asumir un atributo raíz.

K ya entrega parte de las firmas; la matriz siguiente se conserva como control de completitud para los lotes. Pendientes concretos de conciliación: (a) enum de resorte: K dice 1=CompressionOnly/2=TensionOnly y C lo invierte, sin prueba de lectura citada; no fijarlo aún; (b) K atribuye a get_points el uso de GetCoordCartesian, pero C:320 llama GetAllPoints; (c) K §4 dice que falta acero por estación, pero get_slab_design_detail ya existe y B documenta 396 estaciones; (d) las marcas [H] apoyadas solo en «lo usa el MCP», «según README» o prueba equivalente en ETABS no se adoptan como corrida nueva en SAFE. Solicitar método, retorno y relectura concreta, sin modificar la evidencia ajena.

| Orden | Namespaces a sondear | Confirmación que desbloquea |
|---|---|---|
| A, lote 1 | `PropArea`, `AreaObj`, `PointObj`, `EditGeneral`, `SelectObj`, raíz | Get/SetSlab y enum, Get/SetProperty, geometría/readback, Move y selección por IDs, bloqueo del modelo. No escribir en la sonda. |
| A, lote 1 | `DatabaseTables`, `DesignConcreteSlab` | Tabla de resultado exacta de punzonamiento y tablas de parámetros; campos, unidades, claves por objeto y firmas de lectura. |
| B | `EditArea`, `EditPoint`, `FrameObj` | Confirmar límites de edición, copia/borrado por tipo y métodos reales. Ausencia también es resultado útil. |
| B | `DesignConcreteSlab.DesignStrip`, `DesignConcreteSlab.ACI318_14`, `.ACI318_19`, `.ACI318_25` | T da solo GetPreference en ACI318_19; confirmar los otros y no suponer SetOverwrite. Forma completa de GetDesignStrip_1 y resultados de diseño. |
| B | `PropAreaSpring`, `PropPointSpring`, `PropLineSpring` | Get/Set reales, unidades y NonlinearOption3. La semántica compression-only exige evidencia de lectura de propiedad conocida. |
| B | `File` | ImportFile/ExportFile y Type de importación; enum/capacidades. No probar enteros desconocidos sobre el proyecto abierto. |
| C | `LoadPatterns`, `LoadCases`, `RespCombo`, `FrameObj`, `PointObj`, `AreaObj` | Casos/patrones/combos y cargas puntuales, uniformes y distribuidas; Replace, ItemType, ejes y enums. |
| C | `Results`, `Results.Setup`, `Analyze`, `Options`, `LoadCases.StaticNonlinear`, `LoadCases.StaticNonlinearStaged` | Resultados por caso/paso, estado, no linealidad, fisuración y control de análisis. |
| D | `TendonObj`, `PropTendon`, `PropMaterial`, `PropRebar` | Lectura PT, propiedades, materiales y catálogo de barras; confirmar soporte real de interfaces compartidas. |

Además de `describe_oapi`, listar tablas y sondear `DatabaseTables.GetAllFieldsInTable` / lectura de esquemas: el mero nombre de una tabla en X no prueba que se pueda editar. Volcar versión de tabla, FieldKey, unidades, campo importable y filas de ejemplo acotadas. Prioridad de tablas:

1. `Concrete Slab Design - Punching Shear Data`: Point, Status, Ratio, Combo, Depth, Perimeter, Location, coordenadas y campos de refuerzo.
2. `Concrete Slab Design Overwrites - Punching Shear - General`, `... - Perimeter`, `... - Openings` (UniqueName y campos pertinentes).
3. `Strip Object Connectivity`; `Strip Forces`, `Strip Forces Summary`; overwrites `Strip Based` y `Finite Element Based`; `Concrete Slab Design - Flexure and Shear Data`.
4. `Area Assignments - Insertion Point`, `Floor Object Connectivity`, `Point Object Connectivity`, `Slab Property Definitions`.
5. `Soil Pressures Summary`, `Soil Pressures Enveloping Summary`; distinguir panel/área/elemento. Evitar la tabla nodal masiva durante la sonda.
6. Tablas PT, acero colocado, catálogo de barras, casos no lineales, malla y muros identificadas arriba.

Para confirmar enums de interfaz con una modificación y relectura, usar copia de prueba bajo control exclusivo de Claude, nunca el original. La inspección estática de este backlog sirve para dirigir la sonda; **ninguna implementación nueva se autoriza por un nombre sin confirmar en la FASE 1**.

## Lotes propuestos para FASE 2

**Lote 1 acordado con claude-206, prioridad 1 y orden interno:** reemplaza la propuesta inicial de comenzar por zapata/punzonamiento. Las tablas por objeto se difieren por instrucción expresa de Claude hasta su sonda del modelo.

| Tool nueva | Paso del SOP que cubre | Estado | Prioridad | Contrato / alcance |
|---|---|---|---|---|
| `open_model(path)` | 1 | no existe | 1 | File.OpenFile, capa A documentada; comprobar ruta existente y archivo activo leído después. |
| `new_model` | Preparación de copia de prueba | no existe | 1 | File.NewBlank, capa A; operación explícita que reemplaza el modelo activo, no invocarla automáticamente. |
| `get_file_path` | Preparación / 1 | no existe | 1 | File.GetFilePath, capa A; confirmar forma de salida y diferencia entre carpeta y nombre de archivo. |
| `call_oapi(path, method, args_json)` | Diagnóstico para todos los pasos | no existe | 1 | Resolver namespace confirmado, JSON como lista de argumentos, conservar outs/ret, registrar intento. No ejecutar código Python arbitrario; lectura/escritura dependen del método solicitado por Claude. |
| `select_objects(names, tipo)` | 2; prerrequisito 3.9 | no existe | 1 | SelectObj y SetSelected de AreaObj/PointObj; validar tipos/IDs y devolver selección releída. |
| `clear_selection` | 2; prerrequisito 3.9 | no existe | 1 | SelectObj.ClearSelection/GetSelected; capa documentada según K. |
| `delete_area(name)` | 3.9 | no existe | 1 | AreaObj.Delete [T]; rechazo de ID inválido, registro previo y ausencia posterior. Subconjunto de delete_object. |
| `move_selected(dx,dy,dz)` | 3.9; corrección 3.12 | no existe | 1 | EditGeneral.Move [T]; selección explícita, efectos en conectividad compartida y readback; base posterior de move_objects. |
| `set_area_property(name, prop)` | 3.4; 3.14 | no existe | 1 | AreaObj.SetProperty/GetProperty [T]; implementación de la necesidad set_area_section. |
| `set_area_opening` | 3.9; extensión de huecos | no existe | 1 | AreaObj.SetOpening/GetOpening [T]; no modifica por sí sola overwrites de punzonamiento. |
| `set_point_coordinates(name,x,y,z)` | 3.9; corrección 3.12 | no existe | 1 | EditPoint.ChangeCoordinates [T] de K; releer punto y áreas conectadas. |
| `set_area_points(name, points)` | 3.9; corrección 3.12 | no existe | 1 | EditArea.ChangeConnectivity [T] de K; base de edit_area_points, sin asumir continuidad ni preservación de cargas. |
| `add_point(x,y,z)` | 2; 3.9 | no existe | 1 | PointObj.AddCartesian [T]; ID retornado y coordenadas releídas. |
| `assign_point_load(name, pattern, F1..M3)` | Cargas; apoyo 1/3.1 | no existe | 1 | PointObj.SetLoadForce [T]; cubre add_point_load, confirmar Replace y sistema de coordenadas. |
| `get_strip_rebar_stations()` | 3.16 | no existe | 1 | Salida estructurada sobre GetFlexureAndShear; reusar get_slab_design_detail, no duplicar cálculo. Req/min; no inventar acero provisto. |

Son **15 tools nuevas propuestas**, con alias funcionales respecto del backlog de 204. Cada docstring indicará capa A/B y [T] hasta prueba de Claude. Su código seguirá oapi.call y errores explícitos; cualquier firma incompleta requiere completar la sonda antes de implementarla. La llamada genérica puede reducir ese bloqueo una vez entregado el lote. La implementación no se hizo en esta FASE 0.

**Lote 2:** corregir enum Footing de define_slab_section y añadir define_footing_section tras contrato/readback; endurecer set_table_data/retornos; get/set_punching_params, refuerzo y get_punching_check por objeto cuando Claude confirme tablas. Copy_object, set_area_offset y extensión de operaciones geométricas según contratos. Separar lotes si requieren ciclos de prueba distintos. El hallazgo F0-01 sigue prioridad 1, no queda resuelto por cambiar el orden.

**Lote 3:** creación/anchos de franjas, fuerzas, As req/min/prov, overwrites y acero colocado. Mantener salida «provista no disponible» si no existe fuente verificable.

**Lote 4:** cargas/casos, alias F2K y validación de import/export. DXF permanece P1 pendiente de vía demostrada; una exportación propia debe declarar capas, unidades y contenido distinto del detallado nativo.

**Lote 5:** resultados filtrados, presión resumida, desplazamientos/reacciones, opciones no lineales y plantilla Excel. Luego extensiones PT, plateas, muros y escaleras según evidencia y demanda.

## Criterio de aceptación por lote

- Patrón `oapi.call` con variantes **confirmadas** por Claude; no usar fallback entre semánticas distintas (p. ej. caso versus combo). Error explícito con namespace, método/variantes intentadas, retorno y objeto. Rechazar respuesta de forma desconocida. No reintentar una escritura tras posible efecto parcial.
- Tests unitarios con COM mockeado, sin SAFE abierto: enums exactos, [in,out]/retornos, errores/no-op, selección preservada según contrato aun ante excepción, readback discrepante, objeto/caso inexistente y conservación de filas no objetivo. Lote 1: JSON inválido, retorno COM no cero/desconocido, apertura fallida, selección vacía, punto compartido y arrays de resultados desalineados. Lote 2: impedir Footing=3 y conservar estado de punzonamiento no calculado. Mocks procedentes del contrato confirmado, sin confundirlos con validación en vivo.
- Un commit por lote, autor `Codex <codex@aiq>`, mensaje `CDX: safe-mcp lote N — <tools>` y entrada en `docs/CHANGELOG.md` con estado **pendiente de corrida en vivo**. FASE 0 solo lleva commit documental; no crea un changelog de implementación ficticia.
- Al cerrar cada lote, buzón AIQ-LINK y prompt pegable a Claude con commit, tools/cambios, parámetros de prueba y resultados esperados. Emil reinicia Claude Desktop desde la bandeja; Claude opera la copia, prueba lectura/escritura/readback y responde [H]/[P] **por tool** con versión/modelo/unidades/evidencia. Recién entonces cambia el estado a verificada en vivo.
- Para lote 1: ruta activa tras abrir, creación vacía en sesión/copia de prueba, selección exacta, punto/carga/sección/hueco/conectividad releídos, movimiento y borrado cotejados, estaciones de acero contrastadas con el lector previo. Para lote 2: Footing releído como tal y parámetros/filtro de punzonamiento verificados por punto. Los 13 puntos y ratio 1.029 de B son evidencia histórica, no expectativas obligatorias para otro modelo.

FASE 0 queda cerrada. K/claude-206 proporciona el siguiente encargo, todavía sin implementar: iniciar FASE 2 por el lote 1 anterior y completar contratos faltantes. 206 fue leído e incorporado a la planificación; queda pendiente de ejecución como FASE 2.

### Actualización concurrente al cierre de codex-205

Claude añadió K §6 después de la primera redacción: **reconexión restablecida**, FDB `...\12-HOSPITAL MUNICIPAL EL VALLE\Food Shop Shell Bonao - 15-05-2026\HOSPITAL MUNICIPAL EL VALLE\Modelos\SAFE\SAFE-HOSPITAL MUNICIPAL EL VALLE-25-09-26.FDB`, unidades N/mm, seis casos sin correr. Se actualizan arriba get_model_info y get_analysis_status a verificada en vivo por esa evidencia. La corrida de get_punching_check en EL VALLE leyó **overwrites**, no resultados de chequeo; no prueba cumplimiento estructural.

K §6 confirma lectura de `Strip Object Connectivity` (80 filas, anchos por lado en mm, capas A/B) y del overwrite general de punzonamiento (18 filas; solo siete campos presentes). El catálogo X es más amplio que los campos devueltos en este modelo: **no enviar automáticamente todas las columnas de X**. Falta confirmar GetAllFieldsInTable/ImportType y escribir/releer en copia. Añadir a la primera mejora de diagnóstico de FASE 2 la exposición de `ImportType` en `list_tables`, hoy descartado. Resultados Strip/Punch/Soil requieren análisis+diseño; la decisión sobre el original de EL VALLE ya está anotada por Claude en TABLERO, no se duplica ni se ejecuta desde Codex.

K también registra Z40 como Footing, S40 como Stiff y SOIL1 con texto Compression Only. Es evidencia de valores por **tabla**, aún no de sus enteros COM ni de la eficacia de los setters. Se mantienen F0-01/F0-06 y la solicitud de confirmar enums; no se deduce sigma admisible de k.

Otra sesión Codex (CDX-ciclo-1553, buzón 207) avanzó el cursor compartido de 202 a **206** mientras codex-205 estaba EN CURSO. Se conserva **206**, sin retrocederlo a 204 ni deshacer trabajo concurrente; el corte solicitado 204 está superado. Leído 207, que no asigna tarea independiente. El archivo 205 se mantiene con el número reservado explícitamente por Emil/claude-204. Este cierre solo modifica la línea propia codex-205 del tablero.

### claude-208: lote 1 implementado en paralelo y anulado para Codex

Fuente: `_coordinacion/buzon/208-claude.md`, `docs/CHANGELOG.md`, registros actuales de `src/server.py`. Claude declara implementación por orden de Emil, py_compile correcto y copia `_pruebas-mcp.FDB` creada. Codex comprobó el registro de **18 tools nuevas**, no auditó su implementación ni hizo corrida COM. El chequeo final que esperaba 31 tools en el árbol actual detectó este cambio concurrente; la cobertura de 31 se valida contra el corte git `fb71f65`, y el árbol actual se contabiliza aparte como 49. No confundir el test documental con tests unitarios del servidor.

| Tool incorporada por Claude | Paso del SOP que cubre | Estado | Prioridad |
|---|---|---|---|
| `open_model` | 1 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `close_model` | Preparación de sesión | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `copy_model_file` | Copia de pruebas | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `call_oapi` | Diagnóstico transversal | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `clear_selection` | 2; 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `select_objects` | 2; 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `get_selection` | 2; 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `delete_object` | 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `move_objects` | 3.9; 3.12 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `get_area_info` | 3.4; 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `set_area_property` | 3.4; 3.14 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `set_area_opening` | 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `set_point_coordinates` | 3.9; 3.12 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `set_area_points` | 3.9; 3.12 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `add_point` | 2; 3.9 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `assign_point_load` | Cargas; apoyo 1/3.1 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `get_strip_rebar_stations` | 3.16 | conjetura marcada en código ([T] según CHANGELOG) | 1 |
| `get_table_fields` | 3.2–3.3; diagnóstico de tablas | conjetura marcada en código ([T] según CHANGELOG) | 1 |

`list_tables` ahora expone ImportType según 208 y CHANGELOG; esa modificación necesita revalidación aunque el lector anterior tenga corrida. Las filas «no existe» anteriores para estas capacidades son el corte v0.1.0, superado por este anexo. `new_model`, `get_file_path`, `delete_area` y `move_selected` de la propuesta 206 no se registraron con esos nombres; no añadir aliases sin revisar primero las nuevas herramientas equivalentes.

**Próximo encargo de Codex (208), fuera de este cierre FASE 0:** tests COM mockeado para herramientas previas/nuevas; `add_design_strip`, `set_strip_widths`, `set_punching_overwrite` por esquemas reales; confirmar ImportType; actualizar README/CHANGELOG. Revisar F0-03 antes de reutilizar set_table_data y confirmar columnas editables, no solo lectura de DisplayArray. Pendiente de implementación en otra fase; no se reclama aquí la línea de Claude EN CURSO. Su afirmación de .git de solo lectura quedó desactualizada para CDCRD-Digital: el commit documental de este cierre sí fue posible; raíz Artificial IQ falló por autenticación SSH. No se toca su código ni se le atribuye verificación en vivo.
