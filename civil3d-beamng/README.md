# Civil 3D a BeamNG.drive

Puente determinista para exportar superficies Civil 3D y preparar un mapa propio de BeamNG.drive. Se ejecuta sin modelo de IA, cuenta IA ni servidor MCP. BeamNG.tech no es una dependencia del producto.

Version inicial 0.1.0. Compilacion y pruebas numericas disponibles; importacion manual, guardado, recarga, colision fisica y recorrido corto comprobados en drive 0.39.4. La evidencia de proyectos reales se conserva en sus carpetas privadas. La carga y exportacion del plugin dentro de Civil 3D siguen pendientes; el puente completo aun no tiene validacion de extremo a extremo.

## Componentes

| Carpeta | Funcion |
|---|---|
| `civil3d/` | Plugin .NET 10 para Civil 3D 2027. Comando `CDCRDBEAMNGEXPORT`; lee TIN completas sin modificar el dibujo. |
| `cdcrd_beamng/` | Conversor Python: snapshot o LandXML → heightmap, mascaras, DAE y manifest versionado. |
| `beamng/lua/ge/extensions/editor/` | Herramienta del World Editor: importar terreno y malla; verificar archivos, guardar y auditar resultado. |
| `tools/` | Preparacion de un nivel nuevo en la carpeta del usuario; preservacion de versiones anteriores y rollback. |
| `tests/` | Casos sinteticos de geometria, limites, unidades, formato, hashes y errores de entrada. |

El material de proyectos reales permanece fuera de este repositorio publico. No incluya DWG, snapshots, LandXML ni niveles atribuibles a un proyecto real.

## Requisitos

- Windows con Civil 3D 2027 para exportar desde el dibujo; SDK .NET 10 para compilar el plugin. El conversor puede trabajar con LandXML sin Civil 3D abierto.
- Python 3.10 o superior; NumPy, Pillow y DefusedXML, declarados en `pyproject.toml`.
- BeamNG.drive y su World Editor. El importador fue desarrollado contra las llamadas presentes en drive 0.39.4; la disponibilidad en otras versiones debe comprobarse.
- Blender es opcional para inspeccion/edicion; el conversor escribe COLLADA directamente.

Desde esta carpeta:

```powershell
python -m pip install .
.\civil3d\instalar.ps1
```

El instalador genera `%APPDATA%\Autodesk\ApplicationPlugins\CDCRD-BeamNG.bundle`, separado de cualquier puente MCP existente. Conserva DLL y manifiestos anteriores. Civil 3D toma el nuevo plugin al reiniciar; guarde su trabajo antes de hacerlo.

## Flujo desde Civil 3D

Antes de convertir, puede validar las fuentes sin crear un paquete ni abrir Civil 3D o BeamNG:

```powershell
python -m cdcrd_beamng validate --snapshot .\examples\snapshot-synthetic.json
```

Desde la raíz del repositorio, la CLI común delega en ese mismo validador:

```powershell
.\herramientas-locales\cdcrd.ps1 validar-intercambio --modulo beamng `
  --snapshot .\civil3d-beamng\examples\snapshot-synthetic.json --json
```

Se reutilizan los lectores de snapshot/LandXML de `build`. El resultado es JSON
`cdcrd.interchange-validation/1`: salida 0 si el contrato es válido y 1 si falla.
Valida unidades, orden declarado de coordenadas, geometría numérica, IDs y
referencias. No verifica CRS, coincidencia física del origen ni conexión con las
aplicaciones. Véanse [alcance, casos rechazados y pruebas](docs/VALIDACION-INTERCAMBIOS.md).

1. Ejecute `CDCRDBEAMNGEXPORT`; seleccione terreno y superficie final del corredor. El comando exige metros en AutoCAD y en los ajustes Civil.
2. Incluya alineamiento/perfil cuando quiera una guia de materiales. El ancho indicado es informativo: no reconstruye ni modifica el peralte de la malla. La seleccion de superficies no identifica automaticamente los codigos del corredor.
3. Guarde un JSON nuevo fuera del repositorio publico.
4. Convierta e instale un nivel nuevo:

```powershell
.\tools\convertir-e-instalar.ps1 `
  -Snapshot 'D:\proyecto\snapshot.json' `
  -Output 'D:\proyecto\paquete_r01' `
  -LevelId 'mi_carretera_r01'
```

Seleccione ese nivel en Freeroam y pulse F11 para abrir el World Editor. En **Window → Importar Civil 3D**, seleccione `/levels/mi_carretera_r01/manifest.json`, importe y guarde. Vuelva a cargar el nivel antes de evaluar el resultado. La importacion se admite solamente en el nivel cuyo ID corresponde al paquete; una revision nueva recibe otro ID.

El parametro opcional `-AutoImport` genera una importacion automatica experimental al abrir el nivel; su nueva logica no ha completado una prueba dentro del motor. Use el flujo manual anterior para esta version. Los cambios de nivel se hacen desde Freeroam: durante las pruebas, forzar una transicion pendiente de la interfaz mediante la API provoco un fallo C++ al limpiar los objetos de la escena.

El snapshot incluye nombres/handles y geometria del proyecto. El plugin exporta datos completos; no simplifica superficies ni completa objetos desactualizados. Consulte [el exportador](civil3d/README.md) para unidades, referencias, perfiles y casos rechazados.

## Flujo con LandXML

Exporte Points and Faces y unidades en metros. LandXML almacena N,E,Z; el conversor obtiene E,N,Z.

```powershell
python -m cdcrd_beamng build `
  --terrain-landxml 'D:\proyecto\terreno.xml' --terrain-surface 'Terreno' `
  --road-landxml 'D:\proyecto\corredor.xml' --road-surface 'Superficie final' `
  --road-guide 'D:\proyecto\guia.json' `
  --output 'D:\proyecto\paquete_r01' --level-id mi_carretera_r01

python -m cdcrd_beamng verify 'D:\proyecto\paquete_r01'
python tools/prepare_drive.py --package 'D:\proyecto\paquete_r01' `
  --user-folder "$env:LOCALAPPDATA\BeamNG\BeamNG.drive\current" `
  --game-folder 'C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive'
```

La guia es JSON: `{"nodes_abs_m":[[E,N,Z,ancho_total],...],"station_m":[...]}`. La lista de estaciones es opcional. El ancho se interpola para asignar materiales a triangulos; sus limites se aproximan por el centroide de cada cara. Sin guia, el corredor recibe tierra. Use `--road-is-drivable` solamente cuando toda la TIN seleccionada sea pavimento. La geometria/cota de la TIN se conserva en ambos casos.

## Geometria y limites

La calzada visual y su `Colmesh-1` contienen todos los vertices y triangulos del TIN exportado, con origen local comun, metros y Z arriba. Esto preserva bombeo, peralte y taludes en esa geometria. El resultado sigue limitado por el modelo Civil y por la conversion numerica del motor.

El terreno utiliza PNG de 16 bits, lado potencia de dos, `row0=maxY`, `flip_y=false` y altura `uint16 * maxHeight / 65536`. El manifest guarda la traslacion inversa, SHA256 binario y SHA256 de hexadecimal ASCII. La segunda codificacion permite verificar en Lua los bytes posteriores a NUL, que la funcion nativa `hashStringSHA256` no procesa como datos binarios. Los huecos recortan celdas intersectadas por el corredor y celdas naturales con cobertura incompleta; las fronteras internas del TIN se conservan mediante huecos. Como el terreno es una rejilla, el limite del hueco puede extenderse hasta la diagonal de la celda. Esa incertidumbre se registra: compruebe los empalmes entre terreno y malla dentro del juego.

El material visual no sustituye la colision. El nivel incluye materiales de pavimento y tierra con Ground Type. La malla física no se simplifica: compruebe rendimiento, normales, transiciones y contacto real de las ruedas. El importador documentado Terrain And Road Importer aplana transversalmente, por lo que este puente utiliza la malla de la superficie final.

No se incluyen todavia extraccion de codigos/secciones de corredor, puentes/tuneles, texturas CAD, señalizacion, trafico, telemetria o ensayos automatizados. El modulo no modifica mapas oficiales ni copia materiales de `tech_ground`.

## Pruebas

```powershell
python -m pip install '.[test]'
python -m pytest tests tools/test_prepare_drive.py
dotnet run --project civil3d/tests/StationSampling.Tests.csproj -c Release
```

Antes de declarar una importacion validada: comprobar norte/escala en cuatro puntos, cotas de corona/bordes/peralte, Ground Type bajo ruedas, ambos sentidos de marcha, huecos/empalmes, guardado y recarga. Mantener evidencia de archivo y evidencia del consumidor separadas.

Para comparar cotas fisicas dentro del motor use `castRayStatic`, utilizado tambien por la logica nativa de colocacion de vehiculos. La consulta de seleccion `castRay` puede devolver terreno en celdas marcadas como huecos, por lo que sus resultados no prueban contacto de ruedas.

Fuentes primarias: [niveles de drive](https://documentation.beamng.com/modding/levels/level_creation/section1/), [terreno](https://documentation.beamng.com/modding/levels/level_formats/terrain/), [COLLADA](https://documentation.beamng.com/modding/levels/export_dae/), [TSStatic](https://documentation.beamng.com/modding/levels/level_classes/tsstatic/), [extensiones del World Editor](https://documentation.beamng.com/world_editor/api_reference/create_editor_tool/), [TIN Autodesk](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/7b0cc1ae-c036-49a5-5a91-38192e3bcc6d.htm).
