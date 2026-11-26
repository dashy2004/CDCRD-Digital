# Revisión de datos de ingeniería con IA

CDCRD-Digital genera una revisión Markdown a partir de los archivos de cálculo o del expediente. El documento incluye la huella SHA-256 de los bytes originales y conserva los datos utilizados. Se puede leer en un editor de texto, adjuntar a un asistente que admita archivos o proporcionar como contexto a una herramienta local. El generador usa la biblioteca estándar de Python y funciona sin red, cuentas ni claves de proveedores.

## Generar una revisión en el equipo

Desde la raíz de esta rama, elija el comando correspondiente a la fuente disponible. La carpeta de destino debe existir.

```shell
python herramientas/revision_ia.py --tipo memoria --entrada docs/revision-ia/data.json --salida Revision-memoria.md
python herramientas/revision_ia.py --tipo losas --entrada resultados.json --recibo lectura.json --salida Revision-losas.md
python herramientas/revision_ia.py --tipo derivas --entrada revision.json --salida Revision-derivas.md
python herramientas/revision_ia.py --tipo expediente --entrada expediente.json --salida Revision-expediente.md
```

La opción `--origen` permite identificar la procedencia con una descripción. En losas, `--recibo` coteja la huella del resultado con el recibo del puente. Los recibos históricos que carecen de esa huella quedan identificados como pendientes de verificación. En el expediente, los estados y las referencias se interpretan por lista y criterio. Las cifras y los veredictos son los que declaró el archivo de entrada. Para revisar un hallazgo, pida al asistente que indique el campo o criterio, la fuente, la unidad cuando corresponda y qué dato falta para verificarlo. Revise el documento antes de compartirlo porque puede contener nombres y resultados del proyecto.

## Qué ejecuta cada aplicación

| Entrada | Aplicación o motor | Salida para revisar |
|---|---|---|
| Listados TXT/DL, libros de cargas y fuentes de modelos autorizados | Los lectores de CDCRD-Digital preparan los datos de la memoria. MemoriaPlus ofrece la interfaz de escritorio. | Word editable y revisión Markdown que parten del mismo `data.json`. |
| Geometría y usos exportados desde Revit | El puente de CDCRD-Digital utiliza el motor FEM de EstructurasRD y el cálculo de losas del complemento. | Excel, resultados JSON, recibo y revisión de losas. |
| Derivas de diseño por piso, caso y dirección | El verificador de CDCRD-Digital procesa los desplazamientos de diseño en metros y las condiciones declaradas. | Resultado JSON de la comprobación y revisión Markdown. |
| Informe del expediente MIVHED | El lector de revisión conserva las listas de arquitectura, estructura, instalaciones y demás disciplinas presentes. | Criterios, estados declarados y referencias para localizar la evidencia. |

## Probarlo en GitHub

El flujo [Memoria de diseño y revisión para IA](../../.github/workflows/memoria-revision-ia.yml) reconstruye el [ejemplo de 27 losas](data.json) desde el listado sintético del motor de memoria. Genera el Word, verifica que contenga la tabla de losas y coteja la huella del JSON con la del Markdown. El artefacto `memoria-y-revision-ia` reúne la memoria, su configuración, los resultados y la revisión.

Los flujos [Cálculo de losas](../../.github/workflows/calculo-losas.yml) y [Comprobación de derivas](../../.github/workflows/derivas.yml) ejecutan sus ejemplos sintéticos o las entradas convencionales de la rama. Para losas, la pareja es `entradas-losas/proyecto.json` y `entradas-losas/usos.json`. Para derivas, la entrada es `entradas-sismo/derivas.json`. Reserve los modelos y los expedientes reales para un entorno de trabajo privado autorizado.

En la aplicación de escritorio, use **Generar → Preparar revisión para IA**. El paquete Windows incorpora una copia del generador de CDCRD-Digital junto al motor de la memoria. Para una instalación de desarrollo, conserve el archivo `herramientas/revision_ia.py` en el checkout de CDCRD o copie la misma versión junto a `generar.py`. [Código de MemoriaPlus en EstructurasRD](https://github.com/dashy2004/EstructurasRD/tree/codex/memoriaplus-diseno/src.Memoria)

El mismo flujo ofrece el paquete de escritorio como artefacto **MemoriaPlus-Windows-x64**. En una ejecución correcta, abra **Artifacts**, descargue el archivo ZIP, extraiga su contenido y ejecute **Abrir MemoriaPlus.cmd**. [Instrucciones del paquete](windows/LEEME.txt)
