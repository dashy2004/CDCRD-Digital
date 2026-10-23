# Losas, dimensiones y coronaciones en una copia

Estas herramientas requieren ruta exacta de la copia, PID, archivos protegidos y
turno exclusivo (owner, session, task). No seleccionan un original por nombre
parcial. Sus recibos son archivos privados del proyecto, fuera de este repositorio.

## Dimensiones de losas

`revit_dimensiones_losas(config)` obtiene `Lx` y `Ly` del contorno rectangular real
del Sketch, en los ejes declarados. No usa la caja global ni confunde X/Y con luz
corta/larga. Rechaza contornos no rectangulares, inclinados o ambiguos. Crea
parámetros compartidos de instancia, Length, grupo Dimensions, con GUID estables.
Los valores no se redondean al guardarlos. Son dimensiones exteriores del contorno,
no luces libres entre caras de apoyos. Requieren actualización explícita por API
cuando cambie el modelo; no hay un updater automático.

## Aligerado con menor número de instancias

`revit_aligerado_propuesta(config)` procesa un paño por llamada. Usa una familia de
vacíos y una de EPS, con una instancia de cada una por paño, en vez de miles de
instancias individuales. Los sólidos dentro de cada familia conservan la geometría
de las cavidades. Cierra documentos temporales y libera resultados booleanos.

El umbral de esta operación es **espesor mayor que 0,16 m**, cuando el operador lo
declara en la configuración. No cambia automáticamente la política de cálculo
histórica de `puente_losas.espesor.seccion_biblioteca`; son contratos distintos.
Espesor, capa superior, nervios, separación, bandas macizas y dirección provienen de
entradas revisadas. Una propuesta geométrica no acredita cálculo ni armado.
Se rechazan paños con Parts, acero hospedado, caras inclinadas o cambios de forma.
Cada cavidad pasa contención e interferencias geométricas antes del corte. La
operación comprueba el volumen resultante, avisos y guardado. La memoria mínima
se comprueba antes de geometría y antes de abrir familias. Reducir instancias no
elimina el consumo de los sólidos ni garantiza éxito con RAM insuficiente.

## Regla de muros bajo losa/viga

**Los muros deben terminar en la cara inferior de la losa o viga que los limita.
No deben invadir ni cortar bloques de aligeramiento.** Para una losa aligerada se
usa su intradós nominal completo, no la cara inferior de la capa superior dentro
de una cavidad. Adjuntar el muro a esa cara puede hacerlo subir dentro del EPS.

`revit_coronar_muros(config)` admite `inspect`, `simulate` y `apply`. Recibe una
lista explícita de muros, cotas y elementos de referencia comprobados. No es un
detector automático de soportes. Si hay losa, mantiene su intradós como cota
general y conserva los recortes locales de las vigas. Sin losa, admite la cota
inferior de una viga comprobada. Rechaza muros estructurales, fijados, agrupados o
con perfil editado; esta versión no resuelve geometría inclinada.

La simulación revierte el grupo completo. Comprueba sólidos reales: cambios en la
partición de caras no implican cambios de volumen ocupado. Las vigas, losas, EPS
y acero deben conservar geometría y parámetros editables. Los muros solo pueden
perder material, sin aumentar intersecciones ni generar advertencias.

Revit puede regenerar columnas adyacentes al acortar muros unidos. Esa excepción
está desactivada por defecto. Si se habilita explícitamente, conserva los parámetros
de columna, documenta la variación y comprueba intersecciones antes y después.
Las uniones columna–losa necesarias se ensayan primero; la losa corta la columna,
sin modificar el sólido de la losa. `apply` exige las mismas listas de columnas y
uniones del ensayo (`expected_changed_columns`, `expected_column_floor_joins`).
La limpieza de registros internos de Revit también debe coincidir con
`expected_internal_cleanup_ids` y solo admite registros sin categoría, nombre,
tipo, propietario de vista, geometría ni parámetros editables.

`beam_wall_joins` permite declarar encuentros locales adicionales: cada par debe
tener intersección sólida comprobada y no estar ya unido. La viga corta el muro;
al terminar se exige intersección cero y que la viga mantenga el mismo sólido.
Esta fase permite conservar una coronación que ya está a la cota prevista.

Los pares `duplicate_columns` son opcionales y explícitos. Solo se admite retirar
el duplicado cuando coincide la geometría, tipo, parámetros (excepto identidad
IFC) y uniones; no tiene dependencias, etiquetas ni elementos hospedados, no está
fijado ni agrupado, y `Delete` devuelve exclusivamente su ID. No se realiza una
limpieza general ni se decide qué duplicado conservar automáticamente.

Un recibo `started` indica llamada en curso o interrumpida: después de un timeout
del puente hay que reconciliar el estado, nunca repetir a ciegas. `applied_unsaved`
indica cambios confirmados cuyo guardado no se pudo verificar. Solo `applied` con
`saved=true`, seguido de reapertura y auditoría, confirma persistencia nativa.

## Alcance de las pruebas

El aligerado conserva instantáneas de los vecinos que se solapan, tocan o están
unidos al host. Tras el corte compara sólidos nativos; si solo cambia la
partición de caras, contrasta la diferencia booleana. Comprueba además el volumen
real del EPS y sus intersecciones con muros, vigas, columnas, cimentaciones y
losas. Un cambio protegido o una interferencia revierte el grupo completo.
`simulate_only=true` ejecuta estas comprobaciones y revierte el proyecto; las RFA
del ensayo permanecen en la carpeta declarada y se listan en el recibo.

El modo de memoria predeterminado exige 1000 MiB libres. `memory_mode="bounded"`
permite 768 MiB únicamente para hasta 150 cavidades y 40 vecinos. El recuento de
vecinos precede a la extracción/clonado de sólidos. Un paño mayor conserva el
umbral de 1000 MiB; demasiados vecinos rechazan el modo acotado. Sigue siendo una
losa por operación, con dos instancias y documentos de familia cerrados de forma
secuencial. No hay modo sin límite. Los clones se liberan también al rechazar un
lote. Ambos tipos de transacción usan tratamiento de fallos sin diálogos; un
fallo de limpieza/rollback se registra como `rollback_unverified` y exige revisar
el estado antes de repetir. Ningún modo admite cortar hosts con acero existente.

Los tests Python cubren contratos y guardas que no requieren Revit. La prueba real
requiere una copia respaldada, simulación con rollback, aplicación, guardado,
reapertura, auditoría de geometría y exportación de vistas inspeccionadas. Los RVT,
configuraciones y recibos con rutas reales no se publican con el código.
