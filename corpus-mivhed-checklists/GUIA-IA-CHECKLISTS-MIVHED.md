# Guía para la IA: checklists del MIVHED en CDCRD-Digital

Esta guía le dice a cualquier IA (Claude, Codex u otra) cómo usar los checklists del portal NORM del MIVHED al evaluar un proyecto, al diseñar y al generar memorias con MemoriasPlus. Los datos están en `data/mivhed-norm-checklists.json`; los `.md` de `md/` son la misma información en texto legible y se regeneran con el script.

## 1. Qué son y qué no son

Son las listas con las que el ministerio revisa los expedientes: 14 checklists, 271 ítems y 2.763 motivos de incumplimiento o de no aplicabilidad. Cada ítem trae la base legal que cita el portal (instrumento, edición, ruta y extracto).

Sirven para hacer un **autochequeo previo a la entrega**. No sustituyen la revisión del MIVHED, no certifican que algo cumple y la IA nunca debe escribir que un proyecto «está aprobado» o «cumple con el MIVHED». La fórmula correcta es «autochequeo contra CHECK-ESTRUCTURA v1.0-draft: N ítems sin hallazgos, M con hallazgos, K que requieren verificación humana».

## 2. Estado de los datos (verificado el 2026-11-24)

Estructura, Eléctrica, Sanitaria y Geotecnia están en versión `1.0-draft`. Arquitectura está en `1.1`. Recepción de Proyectos y los demás están en `1.0`. Los borradores pueden cambiar sin aviso, así que toda cita debe llevar la versión.

La numeración de ítems es la posición del ítem en el checklist. Si el MIVHED inserta o quita un ítem, los números se corren. Por eso `mapa-memoria-estructural.json` guarda el título esperado de cada grupo y el script `mapa` avisa cuando algo ya no coincide. Nunca aplicar el mapa sin ejecutar esa verificación si la versión cambió.

Qué falta en el dataset (no inventarlo): el texto completo de las disposiciones citadas (solo hay ruta, encabezado y un extracto), las versiones archivadas de los checklists y 4 normas que la API anuncia pero no devuelve (anuncia 27, devuelve 23). El portal no se revisó en cuanto a términos de reutilización.

## 3. Cómo citar

Usar siempre el ID del ítem y el código del motivo, con la versión: `CHECK-ESTRUCTURA#37`, motivo `37.1` (v1.0-draft). Los motivos de no aplicabilidad llevan `NA`, por ejemplo `1.NA1`. No parafrasear el código ni reordenar los motivos. Un `No Aplica` solo puede apoyarse en uno de los motivos de no aplicabilidad que el propio ítem lista; si ninguno encaja, el ítem aplica.

## 4. Modo evaluación (autochequeo previo a la entrega)

1. Elegir el checklist por disciplina. Para ingresar un proyecto, empezar por `CHECK-RECEPCION-DE-PROYECTOS` (42 ítems) y después el de cada disciplina presente.
2. Para cada ítem, resultado posible: `Cumple`, `No Cumple` (con uno o más códigos de motivo), `No Aplica` (con código `NA`) o `No verificable por IA`.
3. Son **no verificables por IA** y deben quedar marcados para una persona: sellos y firmas físicas, vigencia real de una colegiatura CODIA, legibilidad de un escaneo, registro ante DGMC, aprobaciones de otras entidades. La IA puede comprobar que el documento se menciona o está en el expediente, no que sea auténtico.
4. Nunca marcar `Cumple` sin citar la evidencia (archivo, hoja, párrafo, celda). Sin evidencia, el resultado es `No verificable`.
5. El motivo más repetido del portal es que los datos básicos no coinciden con el resto del expediente: nombre del proyecto, ubicación, propietario, promotor o solicitante, designación catastral. Antes de revisar ítems sueltos, extraer esos datos de cada documento y compararlos entre sí. Es la verificación de mayor rendimiento.
6. Entregar un informe con una fila por ítem: ID, resultado, códigos de motivo, evidencia y quién debe revisarlo.

## 5. Modo diseño

Leer los ítems de la disciplina como lista de entregables y de condiciones que el diseño debe poder demostrar, antes de dar el diseño por cerrado. Ejemplos verificados en Estructura v1.0-draft: derivas entre pisos (ítem 37), deriva global (38), comparación de cortante basal estático y dinámico (39), identificación de irregularidades (35), archivos del modelo con geometría, materiales, cargas y combinaciones (47 a 55) y congruencia entre modelo, memoria y planos (55). Para planos, Recepción exige formato 24" x 36", blanco y negro o escala de grises, y una tarjeta en cada hoja (ítems 6 a 9). La memoria descriptiva va en 8 ½" x 11" (ítem 12).

Los ítems 18 a 29 de Estructura son la lista oficial de detalles que deben existir (zapatas, vigas de fundación, columnas, muros, losas, vigas y pórticos, uniones, escaleras y encofrado). Úsenlos como lista de comprobación al decidir qué detalles se generan o se modelan en Revit o AutoCAD y cuáles faltan.

Si el diseño necesita un dato que CDCRD-Digital no tiene (por ejemplo una tabla de viento), decirlo y detenerse en ese punto. No rellenar con un valor plausible.

## 6. Modo memorias (MemoriasPlus)

MemoriasPlus es parte de CDCRD-Digital y genera las memorias. Reglas para generarlas con estos checklists:

1. Estructurar la memoria estructural según `mapa-memoria-estructural.json`: los grupos con `destino: "memoria"` son secciones de la memoria y los de `destino: "modelo"` son anexos digitales. Los grupos `destino: "planos"` no van en la memoria, pero la memoria no debe contradecirlos. El mapa es una propuesta de Claude, no del MIVHED.
2. Mantener un solo registro de datos del proyecto (nombre, ubicación, propietario, promotor, solicitante, designación catastral) y propagarlo a todas las secciones y anexos. No retipearlo.
3. Incluir el bloque del profesional responsable (nombre, CODIA, fecha) y dejar los campos de firma y sello **en blanco, claramente marcados**. La IA no firma ni sella.
4. Cada resultado que el checklist compara con el modelo (derivas, deriva global, cortante basal estático y dinámico) debe salir del modelo computacional (ETABS por MCP), con el valor, la fórmula o la tabla de origen y el límite normativo citado. Si el modelo no se pudo leer, la sección queda vacía con la nota «pendiente de modelo», nunca con un número supuesto.
5. Al final de cada sección, una tabla corta con los ítems del checklist que esa sección cubre y su estado (`Cumple`, `Pendiente`, `Requiere verificación humana`). Es una ayuda de trazabilidad, no una declaración de cumplimiento.
6. Mostrar todo lo que se calcula con sus insumos. Cualquier cifra sin origen verificable se rotula como supuesto con el dato que habría que medir.

Para las demás disciplinas el mapa aún no existe. Antes de generarlo hay que verificar los títulos del checklist con `mapa`. Observación del texto de los motivos: en Eléctrica casi todos los ítems hablan de planos; en Sanitaria, los ítems 1 a 4, 6, 7, 9, 12, 15 y 17 a 21 mencionan memoria; en Geotecnia, el checklist describe el contenido que debe tener el informe geotécnico (29 ítems). Es una lectura por palabras clave, no una asignación verificada.

## 7. Cruce con lo que CDCRD-Digital ya tiene

Según un resumen de conversación del 24 de octubre (verificar en el repositorio, puede estar desactualizado), faltaban las tablas de viento y los Títulos 4 y 5, fallaba la herramienta que define el espectro y no había herramienta de áreas o losas. Esos huecos tocan ítems concretos: viento (33 y 52 de Estructura), cargas sísmicas (32 y 51) y diseño de losas (41). Las referencias legales de los checklists apuntan con frecuencia a *Suelos y Fundaciones* (46 referencias), *Cargas mínimas para análisis y diseño estructural* (44) y *Hormigón armado* (32 entre versión 01 y 02). Si los «Títulos 4 y 5» de ese resumen son Suelos y Fundaciones y Hormigón Armado, son la prioridad de corpus; es una hipótesis, no está confirmada.

## 8. Reglas no negociables para la IA

No inventar valores ni rellenar vacíos con números plausibles. No declarar cumplimiento oficial. No incluir datos de clientes, proyectos concretos, matrículas ni resultados de diseño atribuibles en este repositorio, que es público. Citar siempre ID, código de motivo y versión. Si un borrador cambia, rehacer la verificación del mapa antes de seguir.
