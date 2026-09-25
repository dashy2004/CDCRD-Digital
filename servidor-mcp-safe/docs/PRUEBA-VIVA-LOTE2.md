# Prueba viva del lote 2 — pendiente [T]

2026-09-25 [codex]. Ejecuta Claude después del reinicio completo de Claude Desktop.
No correr sobre el original. Usar copy_model_file, abrir la copia, confirmar archivo
activo y unidades. La revisión en mocks no cambia ningún estado a [H].

1. Leer list_tables y get_table_fields de las dos tablas de §6.1. Registrar
   ImportType, IsImportable, unidades y estado de bloqueo. Confirmar que NumSegs
   es no importable y el resto de campos esperados sí lo son. Si los esquemas
   cambian, devolver [P] con el esquema; no sustituir nombres a ciegas.
2. Guardar fuera del repositorio una lectura COMPLETA previa de ambas tablas,
   incluyendo GUID y filas no objetivo. Elegir dos puntos existentes distintos
   y confirmar coordenadas. Todas las nuevas marcas usan el prefijo CDX:.
3. add_design_strip: crear CDX:L2_A, capa A, AutoWiden=False, con semi-anchos
   asimétricos razonables en las unidades activas. Confirmar una fila nueva,
   NumSegs=1, puntos, cuatro anchos, Layer, AutoWiden y GUID no vacío. Comparar
   todas las filas anteriores. Repetir nombre debe fallar sin cambios.
4. set_strip_widths: modificar esa franja con cuatro valores distintos. Releer
   cuatro columnas y conservar puntos/capa/GUID/filas ajenas. Confirmar error
   ante nombre inexistente, ancho negativo y franja multisegmento. AutoWiden=True
   requiere ensayo separado: documentar Yes y si SAFE recalcula anchos.
5. set_punching_overwrite: elegir una fila existente y cambiar un valor de texto
   cuya validez se haya confirmado por interfaz/documentación viva. Pasar None
   para los demás; confirmar que quedaron idénticos. Reponer el valor original.
   Confirmar dominios exactos de CheckPunchingShear, LocationType, Perimeter,
   EffDepthType, OpeningDef y RebarType. El XML instalado no los incluye.
   Para probar creación, usar punto admisible y suministrar los seis valores;
   no inferir profundidad numérica a partir de eff_depth (es EffDepthType).
6. Invalidar un texto solo en la copia para comprobar cómo reporta SAFE el error:
   SetTableForEditingArray, ApplyEditedTables (incluidos NumErrorMsgs/ImportLog)
   o discrepancia de relectura. No repetir automáticamente: puede haber cambios
   parciales. Cerrar la copia sin guardar y reabrir limpia al terminar el ensayo.
7. Revalidar las rutas reforzadas: set_area_property; abertura True→False con
   section explícita; movimiento de punto/área (incluidos vértices que cambian ID);
   add_point; assign_point_load con Replace=True y False; define_slab_section
   Footing/Mat (tipo, shell, material, espesor); define_soil_spring (k y NonlinOpt3
   por tabla); create_area_by_coordinates y assign_area_spring. Verificar también
   clear/select, get_area_info, list_tables y call_oapi con ret de error.

Reportar por tool: [H]/[P]/[X], versión SAFE, unidades, argumentos sintéticos,
retorno, relectura y efectos colaterales. Guardar evidencias sin datos de clientes
en docs/OAPI-SAFE-real.md y responder al buzón del cierre de codex-209.

No registrar set_area_points: sigue [X], -99. La fusión de puntos que elimina un
ID individual queda como error de verificación para inspección; no se anuncia
éxito solo porque el ID desapareció. La edición de tablas no tiene rollback.

Pendientes heredados identificados por el contrato mock: add_load_pattern aún
pasa el texto load_type al método Add; el wrapper declara eLoadPatternType.
Confirmar ese contrato y sus aliases con Claude antes de ampliar/corregir el mapa.
Los tests de esa tool fijan la llamada actual y propagación de error, no validan
que SAFE acepte ese texto. Lo mismo aplica a getters/esquemas de relectura aún no
confirmados para definiciones de materiales, combos y archivo import/export.
