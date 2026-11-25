# Medición de homologación en Civil 3D

Desde la raíz de CDCRD-Digital, compile para Civil 3D 2027. El proyecto usa el SDK de .NET 10 y las DLL de la instalación. Si Civil 3D está en otro directorio, pase `-p:Civil3DPath=...` a `dotnet build`.

```powershell
dotnet build servidor-mcp-civil3d/modulo-homologacion/Cdcrd.Homologacion.csproj -c Release
dotnet run --project servidor-mcp-civil3d/pruebas/homologacion/Pruebas.csproj
```

En la sesión autorizada de Civil 3D, cargue con `NETLOAD` el archivo `modulo-homologacion/bin/Release/net10.0-windows/Cdcrd.Homologacion.dll`. Trabaje sobre la copia de la revisión a cotejar. El archivo JSON describe el estado observado en memoria.

## CDCRDMEDIRPUNTO

El comando genera una medición por ejecución. Indique el identificador acordado del marco horizontal y vertical, la revisión y la presentación de papel que documenta el punto. La herramienta comprueba que la presentación existe. El operador debe comprobar la visibilidad del elemento en esa lámina y la correspondencia de la revisión. Identifique los puntos de control independientes antes de comparar modelos.

| Opción | Selección en el DWG | Lectura en coordenadas WCS del dibujo |
|---|---|---|
| Llegada | Punto COGO que identifica el extremo exacto de la rampa y superficie TIN terminada | X e Y locales del punto y elevación TIN en esa posición. El JSON conserva el handle de la superficie y el del COGO en el método. |
| Sumidero | Estructura de la red de gravedad que representa la rejilla | Centro en planta de la estructura y elevación del borde modelado (`RimElevation`). Compruebe que el borde representa la entrada en el modelo. La medición física de campo requiere levantamiento. |
| Control | Punto COGO de control | Coordenadas locales y elevación del punto. Deben corresponder al mismo testigo que el control de Revit. |

El comando convierte la unidad civil de dibujo a metros (1 para metros, 0,3048 para pie internacional y 1200/3937 para pie de agrimensura estadounidense). Lee coordenadas propias de cada objeto, independientes del UCS de pantalla. La zona cartográfica configurada se muestra para revisión. La identificación del marco es una declaración del operador. Si el WCS local del DWG requiere traslación, rotación o cambio de datum para coincidir con Revit, prepare y compruebe primero el marco compartido. Una superficie obsoleta o un punto fuera del TIN interrumpen la lectura. El archivo de destino debe ser nuevo.

## CDCRDREEMITIRPDF

Después de la corrección aprobada y de reconstruir las superficies afectadas, active la presentación de la revisión y salga de cualquier viewport activo. Configure previamente un dispositivo `DWG To PDF.pc3` o de la familia `AutoCAD PDF` y compruebe papel, escala y ventana. El comando regenera la vista y traza la presentación activa con esa configuración, verifica la cabecera del PDF y publica con un nombre nuevo. Abra el PDF resultante para cotejar etiquetas, medidas y revisión. Para cerrar el cotejo repita las mediciones en la copia corregida.

La prueba portable cubre el contrato, conversión y emisión de tres JSON sintéticos. La selección de objetos y el trazado deben comprobarse dentro de Civil 3D.

[Unidades y zona de Civil 3D](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/7b7c2087-923d-f76e-1db8-2d9fd2d59ff5.htm) · [Elevación del borde](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/922119ef-fc61-efd2-602d-c2c932420bfd.htm) · [Motor de trazado](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_PlottingServices_PlotEngine.html)
