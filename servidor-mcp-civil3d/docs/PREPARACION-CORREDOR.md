# Próxima etapa: ensamblaje, corredor y secciones

Actualización: el flujo de un ensamblaje de enlaces, un corredor y secciones se implementó en [0.5.15](CORREDOR-0515.md). Se conserva abajo la preparación previa.

Estado al preparar 0.5.14: investigación de contratos instalados de Civil 3D 2027 y revisión del código existente. **No se ha creado ni probado un corredor con estas herramientas.** Curvas de ejes y perfiles se entregan por separado en [0.5.14](CURVAS-0514.md).

## Contratos públicos comprobados en la instalación

- `AssemblyCollection.Add(name, AssemblyType, Point3d)` y sobrecarga con estilos.
- `SubassemblyCollection.ImportStockSubassembly(name, stockName, Point3d)`, `ImportSubassembly(...)` e `ImportSACSubassembly(...)`. La disponibilidad de una firma no prueba que un subensamblaje concreto esté instalado o sea utilizable.
- `Assembly.AddSubassembly(ObjectId)` para asociar una pieza al ensamblaje.
- `CorridorCollection.Add(name, baselineName, alignmentId, profileId)` y sobrecarga con región y ensamblaje.
- `BaselineRegionCollection.Add(name, assemblyId, startStation, endStation)`.
- `SampleLine.Create(name, groupId, station)` y sobrecarga con `Point2dCollection`.

Antes de implementar: inspeccionar los parámetros reales del subensamblaje elegido, los métodos de reconstrucción, frecuencias y targets. Usar un ejemplo sintético explícito; no inferir anchos, espesores, pendientes ni vehículo de un proyecto real.

## Reutilización de secciones

Se revisó `civil3d-terrain-tools/plugin/TerrainApi.cs`, disponible en otro worktree de desarrollo. Su método `Sections` ya crea un grupo, habilita fuentes de superficie, conserva estilos originales mediante copias, genera líneas/secciones/vistas y relee la geometría. Ese módulo aún no está integrado en este worktree; no duplicarlo.

Su geometría actual crea un eje recto y calcula XY con una dirección constante. **Ese cálculo no sirve para el eje curvo.** Separar la creación del eje del muestreo y obtener cada sección mediante estación/offset del alineamiento nativo. Conservar los controles de unidades y de rango, comprobar los signos izquierda/derecha y muestrear explícitamente las fuentes del corredor.

## Etapas de aceptación

1. Ensamblaje nativo con subensamblajes y parámetros releídos; simulación y fallo intermedio sin residuos.
2. Corredor con eje/perfil ya verificados, baseline, región y frecuencia explícitas; reconstrucción y lectura de ensamblajes aplicados.
3. Líneas de muestreo y secciones sobre el corredor, reutilizando el módulo anterior. Comparar geometría con estaciones, offsets y cotas independientes.
4. Guardado/reapertura, preservación de objetos previos y capturas nativas revisadas antes de publicar.

Grading nativo, daylight, peraltes, espirales y barrido vehicular siguen fuera de este bloque.
