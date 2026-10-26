# Validación de la primera entrega

Fecha: 2026-10-26. Datos exclusivamente ficticios. Seguimiento: [#41](https://github.com/dashy2004/CDCRD-Digital/issues/41).

## Evidencia local

- **104 pruebas aprobadas** con Python 3.12 en Windows; Ruff sin incidencias.
- MCP: proceso real por stdio, inicialización, catálogo de cuatro herramientas, invocación de las cuatro, error de plantilla no compatible y prueba de respuesta del bucle asíncrono durante una generación.
- Fuentes: hashes antes/después, preservación de fecha de modificación en prueba de integración, salidas exclusivas, enlaces/traversal y límites; un fallo conserva `INCOMPLETE`.
- Contrato: ausencia distinta de cero, valores no finitos y cadenas numéricas rechazados, referencias, unidades, modelos/revisiones, ejes locales girados sin transformación y ausencia de aprobación inferida.
- PDF: selección de páginas, índice y marcadores reales, tablas largas, páginas giradas, cifrado/archivos inválidos y contenido activo. Los formularios y anotaciones con apariencia se rechazan para impedir pérdida silenciosa de información.
- CLI: JSON legible incluso con consola Windows `cp1252` y nombres/símbolos Unicode.
- Wheel `cdcrd_memoria-0.1.0` construido correctamente.
- Integridad del corpus normativo del repositorio: 111 archivos, ninguno añadido, retirado o cambiado.

## Comprobación visual del ejemplo

El comando `demo` produjo un PDF de **4 páginas**: 2 del cuerpo y 2 de anexos. Se rasterizaron e inspeccionaron las cuatro páginas: tablas sin recortes, estados pendientes visibles, unidades y precisión conservadas, anexo original y pie global separados, índice 3–4 y marcadores correctos.

El DOCX se abrió en **Microsoft Word 16.0**, en modo de solo lectura y con macros deshabilitadas; se actualizaron campos en memoria y se exportó a PDF para inspección. El cuerpo editable y el inventario ocuparon **2 páginas**, ambas inspeccionadas. Se cerró sin guardar cambios. Los hashes de todos los archivos del paquete siguieron coincidiendo tras esta comprobación.

El renderer empaquetado de documentos no estaba operativo por ausencia de LibreOffice en este equipo; se utilizó Word nativo para comprobar el consumidor real. La paginación exacta puede variar entre motores tipográficos. HTML/DOCX incluyen el inventario; las páginas originales de anexos se incorporan al PDF ensamblado.

## Volumen

Prueba adicional con un anexo sintético de **1000 páginas**: salida de **1001 páginas**, rango global 2–1001, texto comprobado en páginas originales 1/500/1000 y SHA-256 de fuente intacto. Tiempo observado de composición y comprobación en este equipo: 6,6 segundos. Son páginas de texto simple; este resultado no promete ese rendimiento con memorias reales, imágenes pesadas o PDF complejos.

## Revisión independiente y límites

Revisión general y revisión Python cerradas sin hallazgos pendientes después de corregir cuatro problemas: números no finitos como texto, bloqueo del bucle MCP, codificación de consola y pérdida de apariencias PDF. La CI reproduce pruebas y lint en Windows y Linux; su estado vigente figura en el PR.

Esta evidencia acredita el flujo documental offline. No acredita resultados nativos ETABS/SAFE, análisis estructural, selección normativa, contenido correcto de fuentes reales ni firma/aprobación profesional. No se modificó la configuración de clientes MCP ni se instaló sobre el checkout operativo. El piloto con datos reales y la ampliación de captura conservan seguimiento en #41 y sus dependencias.
