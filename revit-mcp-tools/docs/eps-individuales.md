# EPS individuales para cantidades

`revit_eps_individualizar(config)` inspecciona una instancia EPS que contiene
varios volúmenes y propone sustituirla por instancias de familia independientes.
No sustituye familias VOID ni modifica los cortes de la losa. Cada pieza tiene
un ElementId propio, dimensiones de tipo fijas y trazabilidad en Comentarios.

Estado: implementación y pruebas de partición fuera de Revit. **Pendiente de
ensayo nativo**; un test Python no acredita carga de RFA, geometría guardada ni
cantidades visibles en una tabla de Revit.

## Contrato

1. Proporcionar `expected_path`, `protected_paths`, `expected_pid`, `lock_path`,
   `lock_identity` (owner/session/task) y `source_id`. `inspect_only` es `true`
   por defecto. Devuelve `plan_digest`, cajas, celdas y número de piezas.
2. Opcionalmente, `max_piece_xy_m: [0.5, 0.5]` divide franjas en piezas de
   hasta 50 cm sin crear huecos o nervios entre ellas. Un resto menor de 1 mm
   se incorpora a la pieza anterior; esta puede superar el nominal en menos
   de 1 mm. Los recortes cuentan como piezas, no como bloques comerciales enteros.
3. Para aplicar, pasar `inspect_only: false`, `replacement_authorized: true`,
   `expected_digest`, `backup_path`, `backup_sha256`, `family_template`,
   `family_dir` y un `receipt_path` nuevo. `save: true` solicita guardar la copia.
   `simulate_only: true` revierte el grupo, pero conserva RFA y recibo del ensayo;
   conciliarlos antes de reutilizar rutas. No sobrescribir un recibo.

Se rechazan geometrías curvas, giradas o no prismáticas, EPS con dependientes,
etiquetas, host, grupo, fijación o capacidad de corte, y piezas solapadas.
Se rechazan ensamblajes y opciones de diseño; las piezas conservan las fases
de creación y demolición del origen. Para reutilizar una familia se exige
procedencia del generador, categoría, dimensiones, flags y material coherentes.
Límite predeterminado: 600 piezas y 768 MB libres. Las familias temporales se
cierran una a una. Las dimensiones se almacenan con fórmulas constantes para
no aparentar que un cambio del parámetro redimensiona la geometría.

Antes de borrar el conjunto se comprueba cada pieza por intersección booleana.
Cada pieza debe contener exactamente un sólido; se vuelve a comprobar después
del commit, antes de confirmar el grupo.
El borrado se revierte si arrastra otro elemento. Se comparan firmas de la
geometría de todas las losas, vigas, columnas, muros, cimentaciones y otros
modelos genéricos y se rechazan advertencias nuevas. El recibo diferencia
inspección, simulación revertida, aplicación sin guardar y guardado confirmado.

En una tabla de Modelos genéricos, filtrar familias `CDX_EPS_PIEZA_…`, mostrar
Familia/Tipo, Comentarios, Recuento y Volumen. No incluir VOID. Las bovedillas
anteriores que ya sean individuales necesitan otro filtro o tabla consolidada.
La densidad/material comercial y el diseño estructural requieren validación
independiente; esta operación conserva el volumen geométrico del EPS.

## Referencia geométrica y nervios

No inferir el ancho de nervio exclusivamente a partir del espesor total. El
perfil heredado de `aligerado_propuesta` usa 15 cm para h=20 cm y 20 cm para
h=25 cm; eso es una convención del catálogo anterior, no una ley estructural.
Cuando el procedimiento aprobado indique 15 cm, medir el modelo y documentar
la discrepancia antes de reconstruirlo. La individualización no cambia nervios.

API utilizada: `SolidUtils.SplitVolumes`, `NewExtrusion`, `NewFamilyInstance`,
transacciones y comparación de sólidos. Contratos consultados en el XML local
de Revit 2027 y en la [documentación oficial de geometría](https://help.autodesk.com/cloudhelp/2025/ENU/Revit-API/files/Revit_API_Developers_Guide/Revit_Geometric_Elements/Geometry/Revit_API_Revit_Geometric_Elements_Geometry_Geometry_Utility_Classes_html.html).

## Sondeo del puente

El servidor descubre el transporte con `GET /routes/status`, sin ejecutar una
sonda Python en el hilo de Revit. Ese endpoint confirma el servidor HTTP, no
que Revit haya terminado de cargar ni que haya atendido una consulta nativa.
Después de un timeout, conciliar el recibo y las solicitudes pendientes antes
de reintentar. Este cambio no cancela eventos ya encolados ni instala una cura
en caliente dentro de pyRevit.
