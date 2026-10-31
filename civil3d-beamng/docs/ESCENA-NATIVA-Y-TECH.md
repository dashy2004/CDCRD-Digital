# Escena Civil 3D completa en BeamNG Tech

La API `scene.snapshot` del puente Civil 3D 0.5.20 lee las dos TIN,
el eje y los objetos visibles de un prefijo explícito de capas. Requiere
`expected_document` absoluto, `terrain_handle`, `road_handle`,
`alignment_handle`, `scene_layer_prefix` y `width_m`.
La herramienta MCP es `leer_escena_beamng`. La operación es de lectura:
no reconstruye, guarda ni modifica el DWG.

Los bloques se recorren aplicando sus transformaciones. Caras, superficies TIN
y sólidos se exportan como mallas; los sólidos usan la teselación de Autodesk.
`scene_skipped` enumera entidades no soportadas. Los colores ACI se resuelven
mediante `Color.ColorValue`; leer directamente `Color.Red` no resuelve esos índices.
La precisión de la teselación de sólidos no equivale a conservar su BREP.

```powershell
py -m cdcrd_beamng build --snapshot snapshot.json --output paquete-r03 `
  --level-id demo_r03 --square-size 0.5 --exact-terrain `
  --scene-visual-layer DEMO-BACHE --scene-visual-layer DEMO-MARCAS
```

`--exact-terrain` conserva la TIN nativa como una malla física. Usarlo solo si
la superficie fuente ya excluye carretera y aceras: no recorta solapes.
El modo predeterminado sigue siendo TerrainBlock/heightmap. Las capas visuales
no tienen colisión; esto evita que pintura y recubrimientos tapen físicamente
el bache. La carretera mantiene sus triángulos y material ASPHALT.

El importador recarga la colisión antes de colocar el vehículo. Después se debe
guardar desde el editor, volver a cargar el nivel y comprobar cotas y contacto.
Los edificios, árboles y materiales conservan el carácter simplificado de la
escena CAD; no constituyen un entorno fotogramétrico.

## Prueba del 31 de octubre de 2026

- Civil 3D 2027: exportación nativa sin modificar el DWG; 61 referencias de bloque,
  485 mallas de entorno y ninguna entidad omitida. La resolución de cuatro colores
  indexados se releyó mediante la API y se conservó en un recibo local separado.
- BeamNG Tech 0.39.4 / BeamNGpy 1.36: nivel guardado y recargado con 30 mallas;
  65 rayos de colisión contra la carretera, error máximo 0.00000769 m frente a
  las cotas de origen. Esta prueba compara geometría, no valida accidentes ni lesiones.
- Dos pasadas con conducción programada y una toma de detalle: H.264 1080p/30,
  aproximadamente 54 s en conjunto. Se añadió una toma corta del espejo VR.
  Decodificación completa sin errores;
  comprobación visual por fotogramas, no reproducción humana continua.
- OBS usa un perfil y una colección propios, captura WGC de `BeamNG.tech.x64.exe`
  y NVENC. `CaptureSession(..., application="BeamNG")` conserva el perfil previo
  y permite restaurarlo. La autenticación permanece en la configuración local.
- Quest 3S: usuario confirmó también R03 desde la cabina, seguimiento y fluidez
  percibida mediante SteamVR. OpenXR devolvió sesión Focused, visor activo y
  renderizado 1769 x 1892 por ojo al 70%; la última lectura fue 45 Hz frente a
  objetivo de 90 Hz, sin acreditar 90 fotogramas nativos. La toma es el espejo
  2D del visor, no un video de 360 grados. VR requiere Vulkan en esta versión.

Los recibos, DWG, niveles instalados y videos permanecen fuera de Git. No se
redistribuyen DLL de Autodesk, recursos del motor, claves ni configuraciones OBS.
Fuentes de las APIs y licencias: [REFERENCIAS-BEAMNG.md](REFERENCIAS-BEAMNG.md).

## Motocicletas

Existe el mod [Hirochi Outlaw](https://www.beamng.com/resources/hirochi-outlaw.33927/)
del autor thatjackguy, publicado en el repositorio de BeamNG. No forma parte de
esta prueba ni se ha certificado su compatibilidad con Tech. Para estudiar
caídas deben comprobarse sus ayudas de equilibrio, neumáticos y representación
del conductor; una demostración visual no acredita fidelidad biomecánica.
