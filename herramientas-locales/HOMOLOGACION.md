# Homologación de un acceso entre Revit y Civil 3D

## Primera ejecución

Desde la raíz de CDCRD-Digital, con el entorno de `herramientas-locales` instalado, ejecute en PowerShell:

```powershell
$casos = '.\herramientas-locales\ejemplos\homologacion'
.\herramientas-locales\cdcrd.ps1 homologar-acceso --criterios "$casos\criterios.json" --medicion "$casos\antes.json"
.\herramientas-locales\cdcrd.ps1 homologar-acceso --criterios "$casos\criterios.json" --anterior "$casos\antes.json" --medicion "$casos\despues.json"
```

La primera llamada encuentra un desnivel de 0,04 m y devuelve código 1. En la segunda, el umbral conserva su cota de 10,04 m y la llegada sube de 10,00 a 10,04 m. Se esperan código 0 y `correccion_geometrica_releida`. Los valores y tolerancias de los ejemplos son sintéticos. El servidor local también expone `homologar_acceso` sobre archivos dentro de la raíz configurada.

## Qué mide

El control coteja la implantación y la relación de arquitectura con vialidad, saneamiento y accesos. En cada medición se conservan la procedencia, el punto, el marco, la revisión y los identificadores de lámina. El informe enlaza la [plantilla pública de homologación](https://norm.mivhed.gob.do/portal/templates/33). El expediente y las reglas de evaluación del formulario se tratan en [Expediente MIVHED](EXPEDIENTE-MIVHED.md).

| Magnitud | Cálculo y criterio |
| --- | --- |
| Control independiente | Medir el mismo hito en Revit y Civil. Comparar distancia horizontal y diferencia de cotas con las tolerancias explícitas del proyecto. El hito debe estar separado del acceso. |
| Desnivel | Z del umbral menos Z de la llegada. Restar el desnivel previsto y comparar el valor absoluto con la tolerancia vertical. Los extremos del acceso deben coincidir en planta dentro de la tolerancia horizontal. |
| Caída a la rejilla | Z de la llegada menos Z del borde modelado de la rejilla. Dividir por la distancia horizontal y multiplicar por 100 para obtener la pendiente media entre extremos. Comprobar caída positiva y pendiente mínima del proyecto. |
| Relectura | Comparar la misma ubicación, documento y elemento en las dos campañas. Cada cambio de coordenadas requiere revisión distinta. Una lectura previa observada y otra dentro de criterios acreditan la corrección geométrica puntual. |

El control de un hito detecta una discrepancia local. Para adoptar el marco de dos modelos hay que validar previamente datum, orientación, escala y transformación con los controles del levantamiento. La pendiente entre dos extremos requiere un perfil intermedio para establecer continuidad de escorrentía, además del análisis hidráulico que corresponda. El responsable fija los criterios y su fuente para el proyecto. La mera ausencia de observaciones geométricas no autoriza declarar aprobado un expediente.

## Verificación dentro de las aplicaciones

1. Preparar un modelo Revit sintético con umbral y control físico. Preparar un DWG sintético en metros con punto COGO de control, COGO de llegada perteneciente a un grupo fuente del TIN de diseño y estructura de red con cota de borde. Usar puntos con los mismos ejes y datum en ambos archivos. Identificar planta y sección y comprobar que muestran el acceso.
2. Cargar los [comandos de Civil 3D](../servidor-mcp-civil3d/modulo-homologacion/README.md). Ejecutar `CDCRDAJUSTARLLEGADA` sobre el DWG guardado para preparar una **copia nueva**, abrir esa copia y tomar allí la lectura inicial. Usar el mismo nombre de documento y los mismos objetos para las dos campañas.
3. Seleccionar **Medir punto** en pyRevit para `umbral` y `control_revit`. En Civil, usar `CDCRDMEDIRPUNTO` para `llegada`, `sumidero` y `control_civil`. Pasar los cinco archivos después de `--medicion`. Cada punto registra su ID y láminas declaradas. Un papel anotado como afectado requiere cotejo de visibilidad y contenido.
4. Corregir en la copia de diseño la cota autorizada de llegada con `CDCRDAJUSTARLLEGADA`. El comando presenta el cambio solicitado y comprueba las cotas del COGO y del TIN reconstruido antes de confirmar la transacción. Guardar la copia cuando proceda. Repetir las lecturas de la revisión con salida nueva.
5. Pasar los cinco JSON iniciales después de `--anterior` y los cinco actuales después de `--medicion`. Revisar incidencias, identificadores, diferencia de cotas y resultado. Al conservar las revisiones de un documento, todas sus mediciones deben corresponder a la misma revisión.
6. Emitir plantas y secciones ya configuradas con **Emitir PDF** en Revit y `CDCRDREEMITIRPDF` sobre la presentación de Civil. Abrir los PDF y comprobar gráficamente las cotas y la revisión. Las herramientas de emisión operan sobre hojas o presentaciones existentes. El registro de la comparación geométrica y los PDF constituyen evidencias distintas.

Códigos de la CLI: 0 para valores dentro de los criterios de entrada, 1 para observado o pendiente y 2 para entrada inválida. La relectura histórica añade el estado `cambio`; comprobarlo al usar el informe como evidencia de corrección.

## Otras herramientas de la base

| Disciplina | Entrada y comprobación reproducible |
| --- | --- |
| Sanitaria y eléctrica | El [auditor de redes MEP](../revit-mcp-write/HOMOLOGACION-MEP.md) examina conexiones físicas y relaciona circuitos y tableros con una correspondencia de unifilar aportada. |
| Geotecnia | `cdcrd.ps1 revisar-sondeos --ubicaciones puntos.csv --litologia litologia.csv` recibe los CSV de Civil 3D. Cruza Location ID y contrasta Depth Top y Depth Base con Final Depth. Indica vacíos, solapes, intervalos huérfanos y extremos sin descripción o código. Requiere unidades coherentes declaradas en la campaña. |
| Estructura y cimentaciones | El [lector común de CSI](../intercambio-csi/README.md) vincula una lectura de tablas a un proceso, un modelo y unas unidades. El desarrollo específico de puentes y la validación nativa de SAP2000 y CSiBridge quedan pendientes. |
| Acero | La [macro para Tekla](../tekla-herramientas/README.md) relaciona piezas seleccionadas con sus conjuntos y dibujos. |
| Tramitación y demás disciplinas | La CLI `expediente-mivhed` verifica la respuesta admitida por cada esquema e indexa archivos de evidencia. El reconocimiento de una fuente o la detección de un archivo no constituyen un dictamen técnico o jurídico. |
