# Ajuste de la llegada en una copia de diseño

`CDCRDAJUSTARLLEGADA` modifica una única elevación de punto COGO y reconstruye la superficie TIN terminada en Civil 3D 2027. El piloto trabaja con WCS local y unidades de dibujo en metros. El operador identifica la rasante de diseño y aporta la nueva cota aprobada.

## Preparación de la copia

Con el dibujo fuente guardado y sin cambios de base de datos pendientes, ejecute el comando y elija un **DWG nuevo**. El comando copia la versión guardada y compara los SHA-256 de los archivos. Abra la copia en esa misma sesión de Civil 3D. Las referencias externas del DWG siguen siendo externas. Para mantener sus rutas relativas, utilice una carpeta compatible con la estructura del proyecto.

Ejecute `CDCRDMEDIRPUNTO` sobre la copia para registrar la llegada anterior con la precisión completa del JSON. Conserve su este, norte y cota. Declare la revisión de esta lectura. Medir en la misma copia antes y después conserva la identidad documental.

## Ajuste

Repita `CDCRDAJUSTARLLEGADA` en la copia preparada. El comando relee su huella en disco y comprueba que la base de datos está limpia. Seleccione el punto de diseño y el TIN. El nombre exacto de la superficie confirma la identificación declarada por el operador. Introduzca el este, norte y cota de la lectura anterior, y después la nueva cota. La vista previa indica ambas elevaciones y su diferencia. La opción **Aplicar** inicia la modificación.

La comprobación de procedencia requiere un punto de modelo local y editable, contenido en un grupo fuente activo del TIN, sin elevación sobrescrita en ese grupo. Se comprueba que ese punto no alimente por grupo otro TIN local. También se protegen puntos de topografía y de proyecto, puntos o capas bloqueados y superficies bloqueadas, referenciadas o desactualizadas. Esta comprobación de dependencias directas por grupos no enumera toda dependencia indirecta en corredores, superficies pegadas o referencias externas. Revise las entidades aguas abajo en la copia.

La comprobación anterior y posterior a la edición usa una holgura numérica fija de 0,000001 m para cotejar lecturas. Esa holgura sirve para repetir las coordenadas del JSON, con independencia de la tolerancia de diseño. Si la nueva cota coincide numéricamente con la anterior, el comando termina. Al reconstruir, verifica el estado del TIN, la planta y la elevación del COGO y la cota del TIN en ese mismo XY. Si falla una comprobación, se descarta la transacción. Si tiene éxito, la corrección queda en memoria y consume la autorización de esa copia para el comando.

## Comprobación en Civil 3D

En un DWG sintético de diseño cree una superficie TIN con un grupo de puntos COGO y prepare la copia. Repita primero indicando deliberadamente una cota anterior diferente y compruebe que la superficie y el COGO conservan la lectura inicial. Pruebe también cancelación, punto de topografía y punto que alimenta otro TIN. Aplique después una diferencia vertical conocida a un punto exclusivo, vuelva a leer la llegada mediante `CDCRDMEDIRPUNTO`, compruebe la rasante y su entorno y reemita la presentación correspondiente. Para conservar el cambio guarde exclusivamente la copia después de revisar el resultado. La comprobación sobre una sesión viva sigue pendiente.

Desde la raíz del repositorio, `dotnet run --project servidor-mcp-civil3d/pruebas/ajuste-llegada/Pruebas.csproj` verifica sin abrir Civil 3D los cotejos numéricos y la creación de una copia independiente con nombre exclusivo. `dotnet build servidor-mcp-civil3d/modulo-homologacion/Cdcrd.Homologacion.csproj` comprueba las firmas contra las DLL de la instalación.
