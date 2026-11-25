# Lectura de tablas CSI por proceso y modelo

Lector de solo lectura para Windows x64. Compila contra la biblioteca común `CSiAPIv1.dll` de la instalación indicada. Para ETABS y SAFE 23 se contrastaron ensamblados instalados. La presencia del lector común en SAP2000 o CSiBridge debe comprobarse con la versión local y su licencia. Algunas versiones carecen de unión por PID. En ese caso el lector comunica el error.

```powershell
dotnet build intercambio-csi/LectorCsi.csproj -c Release
$lector = '.\intercambio-csi\bin\Release\net8.0-windows\LectorCsi.exe'
& $lector --verificar-api
```

Puede sustituirse la DLL con `-p:CsiApiDll="RUTA_COMPLETA_A_CSiAPIv1.dll"`. El modo de diagnóstico verifica la carga del ensamblado. Para leer un modelo, abrir una copia con el producto correspondiente y obtener el PID de esa ventana. Introducir su ProgID documentado y la ruta absoluta exacta de la copia abierta.

```powershell
& $lector $pidDelModelo $progId $rutaAbsoluta
& $lector $pidDelModelo $progId $rutaAbsoluta $claveDeTabla
```

La primera llamada devuelve claves disponibles. La segunda lee la clave elegida, campos, filas, unidades por campo y las listas activas de casos, combinaciones y patrones. Una unidad vacía se conserva tal como la devuelve CSI. Las tablas de resultados dependen de los casos y combinaciones de visualización seleccionados en el programa. Antes de trasladar una reacción o comparar combinaciones, registrar esa selección y cotejar las unidades de cada campo y los ejes de cada modelo. El código comprueba identidad de archivo y unidades antes y después de leer. Funciones específicas de puentes, diseño de uniones y nuevas combinaciones requieren comprobación independiente en el producto.

Prueba nativa propuesta: en una copia sintética comparar la cantidad de filas y dos celdas de la tabla contra la interfaz. Verificar que otro PID o una ruta distinta producen un error. [Documentación CSI](https://www.csiamerica.com/developer)
