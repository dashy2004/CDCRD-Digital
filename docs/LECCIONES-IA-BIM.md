# Lecciones de operación y documentación BIM con IA

Corte: 2026-10-27. Registro público anonimizado de errores observados y controles
de trabajo. Complementa [los errores de ETABS](../servidor-mcp/ERRORES.md) y la
[propuesta de estándar de planos](https://github.com/dashy2004/CDCRD-Digital/pull/43).
No incluye modelos, imágenes, medidas, nombres, rutas ni identificadores privados.
La prueba en un encargo no constituye una prueba general del producto.

## Continuidad entre asistentes

Antes de operar, leer las instrucciones del proyecto, su bitácora vigente, el
reparto de tareas y las decisiones del responsable. Registrar la revisión de los
archivos y distinguir lo confirmado de lo supuesto. Cambiar de asistente no
reinicia el proyecto ni invalida los ajustes humanos.

Un sistema de etapas puede estar implementado con parámetros y filtros de vista.
Inventariar esos recursos antes de concluir que no existe porque el documento solo
tenga las fases de construcción predeterminadas. Las etapas de creación asistida
y las fases constructivas tienen significados distintos. Revisar también objetos
nuevos sin clasificar que puedan aparecer indebidamente en las primeras etapas.

## Errores, controles y evidencia necesaria

| Error observado | Control que debe aplicarse | Evidencia para considerarlo resuelto |
|---|---|---|
| Usar una lectura antigua para retirar un turno | Comparar la identidad completa al efectuar la operación; conservar el lock como evidencia; sin caducidad o apropiación automática | Prueba de exclusión y rechazo cuando cambia el propietario |
| Interpretar timeout como operación no ejecutada | Recibo previo, inicio y fin persistentes; reconciliar documento, transacción y proceso antes de reenviar | Estado final releído y cero llamadas pendientes |
| Diálogo modal por advertencias que deja el puente esperando | Manejador de fallos que registre y revierta el lote; corregir marcas duplicadas antes de repetir | Commit o rollback confirmado, sin cuadro pendiente |
| Atribuir un crash solo a poca memoria o al último método llamado | Conservar journal, excepción, hilo, versión y memoria; separar correlación de causa | Reproducción controlada o causa sustentada; si falta, diagnóstico abierto |
| Croquis de familia que cambia de forma al flexionar | Restricciones suficientes por vértice y cortes de vacíos explícitos según la clase de familia | Dimensiones, volumen y colocación en proyecto de prueba |
| Recargar una familia antigua sobre ajustes del usuario | Inspeccionar la familia actualmente cargada y sus referencias; partir de esa revisión | Parámetros y cambios humanos conservados tras recarga y reapertura |
| Considerar un círculo o línea 2D como barra o perno modelado | Identificar categoría, host, curvas y cantidad reales; rotular los símbolos de coordinación | Rebar nativo y secciones del modelo cotejados; símbolos no contados como sólidos |
| Completar datos de un croquis no acotados | Buscar en detalles aprobados; mantener variables o pendientes explícitos | Procedencia de cada valor; ausencia de geometría definitiva inventada |
| Duplicar un piloto antes de terminar su ajuste | Inventariar instancias y conservar un piloto único hasta la indicación de réplica | Correspondencia de hosts, orientación, marcas, cantidades y ausencia de duplicados |
| Añadir el nombre del asistente a recursos de producción | Reutilizar las convenciones y estilos existentes; guardar autoría en la bitácora | Inventario de nombres y verificación visual del recurso reutilizado |
| Copiar cotas pero omitir el criterio de las etiquetas editadas por el responsable | Comparar familia/tipo, líder, flecha, orientación y posición respecto al perfil o vuelo; conservar la vista de referencia | Piloto y hojas exportadas cotejados con la referencia, no solo conteo de etiquetas |
| Asignar un material de tierra sin comprobar su hatch en los cortes | Revisar patrón de corte, proyección y overrides efectivos por vista; mantener el propósito gráfico declarado | Patrón Earth visible y legible en el PDF a escala, con huecos y anotaciones claros |
| Dibujar cotas con texto sustituido o sin referencia real | Usar referencias de ejes, caras y centros nativos; conservar el estilo de unidades elegido | Referencias válidas, valores medidos y actualización al cambiar el elemento |
| Mezclar ejes con caras de una cimentación en una cadena ilegible | Ordenar parciales y generales; no dividir innecesariamente una dimensión por su eje central; separar burbujas y textos | PDF a escala y ampliación sin solapes de anotación |
| Mostrar tabiques en un esquema resistente de pórticos | Aplicar la visibilidad por propósito de la vista, sin borrar muros del modelo | Planos estructurales y vistas de coordinación revisados por separado |
| Presentar suelo gráfico como levantamiento o cubicación | Declarar la cota confirmada y el carácter gráfico de contorno, fondo y huecos | El elemento no se usa como terreno medido ni como cantidad de obra |
| Cambiar una plantilla Excel al rellenarla | Trabajar en copia, comparar estructura y presentación; conservar macros, fórmulas, estilos e impresión | Comparación visual, cálculo y reapertura; diferencias autorizadas registradas |
| Exportar valores distintos de los del visor | Motor, interfaz y exportador consumen la misma instantánea con identidad y revisión | Igualdad por paño, dirección, zona, unidad y valor; pendientes conservados |
| Usar V/A como rigidez o acero de franja como acero por nervio | Separar peso, rigidez y sección resistente; declarar unidades y dominio del acero | Trazabilidad entre sección, cálculo y propuesta; aprobación técnica independiente |
| Cerrar un issue porque hay código o una CI verde | Separar implementado, probado offline, probado nativo, persistido e integrado | Cumplimiento literal de los criterios de cierre |

## De modelo a planos

1. Conservar original y copia de trabajo; inventariar ejes, vistas, láminas,
   tablas, familias, estilos y anotaciones existentes.
2. Identificar una vista editada y aceptada como referencia gráfica. Leer sus
   tipos de cota y etiqueta, líderes/flechas, unidades, posiciones respecto a los
   perfiles, patrones de corte, recorte, profundidad y categorías.
3. Aplicar el criterio a un piloto manteniendo los cambios humanos. Una sección
   debe cortar el modelo correcto; un detalle genérico debe identificarse como tal.
4. Generalizar solo lo comprobado. Las marcas de modelo, tabla, etiqueta y
   detalle deben referirse a la misma revisión y al mismo elemento.
5. Exportar y mirar todas las hojas, más ampliaciones de zonas densas. Una hoja
   exportada con éxito puede seguir teniendo textos superpuestos o vistas vacías.
6. Registrar pendientes gráficos y de diseño por separado. Guardar según el
   protocolo del operador, reabrir y comparar con los resultados en memoria.

## Límites de las conclusiones

Los controles anteriores se derivan de incidentes y verificaciones de operación.
No declaran que todas las herramientas del repositorio ya los implementen. La
matriz de pendientes permanece en [#14](https://github.com/dashy2004/CDCRD-Digital/issues/14),
con aceptación UI en #23, modelado de acero en #24, geometría de aligeradas en #25,
equivalencia PM en #26, entrega de losas en #27 y conciliación en #32.

Tampoco convierten una demostración, un mapa de incidencias o una inspección
visual en verificación estructural ni en aprobación de diseño. La comunicación
pública debe mantener esa distinción y usar material autorizado o sintético.
