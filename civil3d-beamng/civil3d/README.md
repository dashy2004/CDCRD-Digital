# Exportador Civil 3D 2027

Plugin convencional sin IA y separado del puente MCP existente. `CDCRDBEAMNGEXPORT` lee dos superficies TIN del dibujo activo y genera un JSON externo `cdcrd.civil3d.snapshot/1`. No modifica, reconstruye ni guarda el dibujo.

## Compilar e instalar

Se requiere Civil 3D 2027 instalado, Windows x64 y .NET SDK 10. Las DLL de Autodesk se referencian desde la instalacion; no se redistribuyen.

La compilacion local puede emitir `MSB3277` por versiones de dependencias de las DLL Autodesk (Microsoft.VisualBasic/System.Drawing). No se ocultan esas advertencias. La resolucion de carga efectiva queda pendiente de probar dentro de Civil 3D; una compilacion correcta no confirma la compatibilidad del runtime.

```powershell
cd <carpeta-del-proyecto>\civil3d
.\instalar.ps1 -SoloCompilar
.\instalar.ps1
```

Una instalacion alternativa acepta `-Civil3DPath`. El bundle propio es `%APPDATA%\Autodesk\ApplicationPlugins\CDCRD-BeamNG.bundle`. Cada DLL va a `Contents/build-<sha256>`; se conservan los builds anteriores y se archiva el manifiesto antes de reemplazarlo. El instalador no abre Civil 3D ni carga la DLL en una sesion existente. `-SoloCompilar` no escribe en ApplicationPlugins.

## Exportar

1. Verifique que el dibujo y las coordenadas reales estan en metros, `INSUNITS=6` y Civil 3D Drawing Settings > Units and Zone > Drawing Units = Meters. Se validan y registran ambas unidades; se rechazan dibujos sin unidades, en otras unidades o con unidades discordantes. No se asume ni se convierte la escala.
2. Ejecute `CDCRDBEAMNGEXPORT` y seleccione la TIN de terreno y la TIN final de calzada (`Top`/pavimento), distintas entre si. Verifique manualmente que la TIN de calzada incluye solo la geometria que quiere conducir: la seleccion no identifica automaticamente los codigos de corredor.
3. Seleccione un alineamiento opcional o pulse Enter. Si lo incluye, elija un perfil de ese eje por numero; Enter usa la elevacion de la TIN de calzada. La TIN debe cubrir cada punto del eje si no hay perfil. Indique el ancho informativo del eje; valor predeterminado 11.4 m. Ese ancho no altera la malla vial exportada.
4. Elija un archivo JSON nuevo. Se incluyen todas las caras visibles, sus vertices absolutos `[E,N,Z]` y los nodos `[E,N,Z,ancho]` cada 5 m mas el extremo final. Cuando el extremo final difiere de una estacion regular por menos de `1e-8 m`, sustituye esa estacion para evitar segmentos duplicados y conservar el extremo exacto. No hay limites artificiales de coleccion, redondeo de coordenadas ni simplificacion de TIN.
5. Use el comando de conversion de la [CLI del proyecto](../README.md) para transformar este snapshot al paquete de BeamNG.drive.

El JSON incluye nombre del dibujo (sin ruta completa), nombres/handles de las superficies y metadatos de origen. **Es informacion del proyecto**: guarde las exportaciones reales fuera del repositorio publico.

## Fronteras y fidelidad

`GetTriangles(false)` excluye caras invisibles: no reaparecen triangulos ocultos fuera de fronteras o dentro de agujeros. `boundary_edges` enumera las aristas usadas una vez en la malla visible, incluyendo agujeros; no crea polilineas en el dibujo. Los vertices conservan la Z exacta de la TIN elegida, incluido su bombeo/peralte. La calidad depende de esa TIN final y de la discretizacion previa del corredor.

Se rechazan referencias invalidas/desactualizadas, superficies pendientes de reconstruccion, TIN vacias, coordenadas NaN/infinito, caras degeneradas, aristas no manifold, perfiles que no cubren todo el eje y alineamientos con ecuaciones de estacion. Puede omitir el eje para exportar las TIN cuando tiene ecuaciones de estacion. Los archivos existentes se conservan. Una exportacion fallida no entrega un JSON parcial.

Este MVP no extrae links, codigos ni secciones transversales del corredor; tampoco incluye puentes, tuneles, solidos, texturas CAD, senalizacion o geometria con varias cotas en el mismo XY. Eso requiere otra representacion distinta de las TIN de calzada/terreno. La compilacion no demuestra una exportacion viva: esa prueba debe realizarse en Civil 3D con un dibujo y comprobar el resultado antes de declarar el puente validado de extremo a extremo.

Prueba independiente sin CAD de estaciones, incluido el extremo `10.000000000000002` y la regla del consumidor que rechaza nodos duplicados:

```powershell
dotnet run --project .\tests\StationSampling.Tests.csproj -c Release
```

Referencias oficiales: [GetTriangles](https://help.autodesk.com/cloudhelp/2022/ENU/Civil3D-API/files/html/7b0cc1ae-c036-49a5-5a91-38192e3bcc6d.htm), [PointLocation](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/f7b94f73-828d-7988-4347-207ae780cc5c.htm), [Profile](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/4ae959e8-6949-90dd-b393-12fd2fe14d44.htm), [IsOutOfDate](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/4fda1bc0-8fb6-6889-460d-01c9badd1920.htm). Las firmas se verifican compilando contra las DLL locales 2027.
