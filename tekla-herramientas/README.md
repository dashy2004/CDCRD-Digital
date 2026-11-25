# Inventario de piezas y planos de conjunto en Tekla Structures 2026

La macro de modelado `InventarioPiezas.cs` lee las piezas seleccionadas en la vista del modelo. Crea un JSON local con el nombre del modelo, GUID de pieza, perfil, material, marca de numeración (cuando exista) y GUID del conjunto. Lee los dibujos del modelo y conserva los planos de conjunto de esas piezas, con marca, nombre y estado de actualización de Tekla. La clave de cruce en el JSON es `conjunto_guid`. Varios planos pueden representar el mismo conjunto.

## Ejecución

En Tekla Structures 2026 con licencia, identifique su carpeta de macros de usuario a partir de `XS_MACRO_DIRECTORY`. Copie únicamente `InventarioPiezas.cs` en la subcarpeta `modeling` de una ruta de macros habilitada y con acceso de escritura. Abra un modelo de prueba y seleccione piezas individuales con el selector de piezas del modelo. En **Aplicaciones y componentes**, ejecute **InventarioPiezas** y elija un archivo JSON nuevo en una carpeta privada. Tekla compila la macro y realiza las lecturas a través de su Open API. [Ejecución de macros](https://developer.tekla.com/documentation/macros-cs) · [Selección de objetos](https://developer.tekla.com/doc/tekla-structures/2026/get-selected-objects-method-73447) · [Plano de conjunto](https://developer.tekla.com/doc/tekla-structures/2026/assembly-drawing-class-66828)

La propiedad `seleccion_omitida` cuenta objetos seleccionados que no son piezas. Un `conjunto_guid` nulo identifica una pieza sin conjunto devuelto. El cruce usa el identificador directo del conjunto. Una lista vacía también puede corresponder a un dibujo compartido por marca cuya instancia representativa es otra. Para resolver ese caso, coteje la numeración vigente y la marca en Tekla. La marca puede estar pendiente de numeración. El estado de actualización procede del dibujo, no certifica revisión profesional ni capacidad de la unión. La ventana para elegir destino aparece después de la lectura. La macro conserva las salidas anteriores.

## Verificación reproducible

Desde la raíz del repositorio, ejecute en PowerShell:

```powershell
.\tekla-herramientas\pruebas\ejecutar.ps1
```

La prueba compila la macro x64 contra los ensamblados de la instalación local de Tekla 2026 y ejecuta el contrato JSON con dos piezas sintéticas y un dibujo. Si la instalación usa otra ubicación, indique `-TeklaBin` con la ruta a `bin`. Las DLL de Trimble permanecen en la instalación.

Para la verificación nativa, seleccione dos piezas de conjuntos diferentes, uno con dibujo de conjunto y otro sin él. Compare GUID, perfil y material con **Consultar objeto**, y la marca y el estado del dibujo con **Gestión de documentos**. Repita después de actualizar el plano y guarde en otro archivo. Esta comprobación de selección real y catálogo de dibujos requiere la sesión autorizada.
