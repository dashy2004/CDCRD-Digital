> Referencia ampliada conservada al reorganizar la portada (0.5.23). Las cifras de versiones anteriores son históricas. Consulta el [README actual](README.md) y sus informes para el estado vigente.

<!-- QTO-0522 -->
## Actualización 0.5.22: cubicaciones/QTO

Cuatro herramientas nuevas (catálogo85): volumen TIN y materiales por secciones, con dos fases para formas de corredor. Probadas en Civil3D2027 sobre otra copia, misma instancia. [Contrato, resultados, límites y cinco capturas reales](docs/QTO-0522.md). Targets0.21/PR38 integrada. Pendientes QTO de pago/precios, criterios externos, otras geometrías y verificación de autocarga al próximo arranque normal.

# Servidor MCP de Civil 3D 2027

Entrega **0.5.21**: targets de ancho y cota por API en un corredor nuevo, con origen de solo lectura. Prueba en otra copia: 8 asignaciones, 74 muestras de carril, 8 secciones, guardado/reapertura y 12 archivos protegidos. Módulo opcional **0.1.1**, puente vivo **0.5.17** y catálogo MCP de **81 herramientas**. [Capturas, contrato y resultados](docs/TARGETS-0521.md) - [Baselines 0.5.20](docs/MULTIBASELINE-0520.md) - [Espirales 0.5.19](docs/ESPIRALES-0519.md) - [Peraltes 0.5.18](docs/PERALTES-0518.md).

Conecta un cliente MCP con el **dibujo abierto** en Civil 3D 2027. Dos piezas:

| Pieza | Que es | Donde corre |
|---|---|---|
| `src/server.py` | Servidor MCP por stdio, en Python (igual criterio que [`servidor-mcp`](../servidor-mcp) de ETABS) | proceso del cliente MCP |
| `puente/` | Plugin .NET 10 que escucha JSON-RPC por linea en `127.0.0.1:8760` | dentro de Civil 3D |

```
cliente MCP  --stdio-->  server.py  --TCP JSON-RPC-->  puente .NET
                                                   --Application.Idle-->  hilo principal de Civil 3D
```

El puente lee y escribe los objetos **por reflexion**: no hay una lista fija de clases
compilada. Lo que exponga la version instalada se puede consultar, y
`listar_colecciones` dice cuales existen de verdad en esa instalacion en lugar de
suponerlo a partir de la documentacion.

## Por que un puente propio y no otra cosa

| Opcion | Estado |
|---|---|
| "Instalar la API de Civil 3D" | No existe como paquete. Las APIs de Civil 3D son de escritorio (.NET, COM, Custom Draw, Overrule) y sus ensamblados vienen con el producto: `acdbmgd.dll`, `acmgd.dll`, `accoremgd.dll`, `ACA\AecBaseMgd.dll`, `C3D\AeccDbMgd.dll`, `C3D\AeccPressurePipesMgd.dll`. Se referencian al compilar; no se instalan ni se redistribuyen. |
| Design Automation (nube, APS) | No tiene motor de Civil 3D. La pagina de APS para Civil 3D no ofrece ninguna API en la nube. |
| Autodesk AutoCAD MCP Server (oficial) | Ya viene instalado como bundle (`acmcp.dll`, `aeccmcp.dll`) y expone `discoverAutoCADTypes`, `queryAutoCADObjects`, `aggregateAutoCADObjects`, `manipulateDrawingCanvas`, `updateAutoCADObjects`, `civil3dQueryModifyStyles`. Su cliente documentado es **Autodesk Assistant** y el bundle no trae ejecutable stdio (a diferencia del preview de Revit, que si lo trae), asi que hoy no se consume desde otro cliente MCP. |
| COM de Civil 3D desde Python | No requiere compilar, pero su superficie de escritura es pobre: no cubre corredores ni ensamblajes. |
| **Este puente** | .NET 10 dentro del proceso, API completa, codigo propio y auditable, sin dependencias de terceros. |

## Requisitos

- Civil 3D 2027 (serie **R26.0**) en Windows x64.
- **SDK de .NET 10** para compilar. El runtime 10 llega con Civil 3D 2027; el SDK no.
  `winget install Microsoft.DotNet.SDK.10`.
- Python 3.10+ de 64 bits con `mcp>=1.10,<2` (`pip install -r requirements.txt`).
  El SDK 2.x elimino `mcp.server.fastmcp`; es el fallo numero uno al instalar.

## Instalacion

```powershell
.\instalar.ps1                     # compila y despliega el bundle
.\instalar.ps1 -Probar             # ping al puente
.\instalar.ps1 -MostrarRegistroMCP # JSON para el cliente MCP
py src\prueba_humo.py              # prueba de humo completa
.\instalar-peraltes.ps1           # módulo opcional; no abre ni reinicia Civil
.\instalar-espirales.ps1          # clotoides SCS; tampoco inicia otra instancia
.\instalar-corredores.ps1         # múltiples baselines/regiones; misma instancia
```

El bundle queda en `%APPDATA%\Autodesk\ApplicationPlugins\CDCRD-Civil3D.bundle`, que
es autocarga: no hace falta `NETLOAD` ni Startup Suite, que la seguridad de AutoCAD
puede bloquear en silencio. Comandos dentro de Civil 3D: `CDCRDMCP`, `CDCRDMCPSTOP`,
`CDCRDMCPINFO`.

## Modelo de permisos

- El puente escucha **solo en loopback**. No abre puertos a la red.
- Toda escritura (`actualizar_objeto`, `invocar_metodo` con metodo que no sea de
  lectura, `ejecutar_comando`) exige un **token de un solo uso** ligado al hash de
  metodo + parametros exactos. Un token no sirve para otros parametros ni dos veces.
- `CDCRD_C3D_SOLO_LECTURA=1` apaga toda escritura.
- `ejecutar_comando` esta **apagado** salvo `CDCRD_C3D_PERMITIR_COMANDOS=1`, y es
  asincrono: encola la linea en el documento y vuelve sin el resultado.
- Log del puente: `%LOCALAPPDATA%\CdcrdCivil3dBridge\puente.log`.

## Cobertura por area

Las cuatro areas se cubren con las mismas herramientas genericas, porque la
seleccion de objetos sale de las colecciones del `CivilDocument`:

| Area | Alias | Miembro real en 2027 |
|---|---|---|
| Diseno vial | `alineamientos`, `corredores`, `ensamblajes`, `subensamblajes`, `vistas_perfil` | `GetAlignmentIds`, **`CorridorCollection`**, **`AssemblyCollection`**, **`SubassemblyCollection`**, `GetProfileViewIds` |
| Superficies y movimiento de tierras | `superficies`, `sitios`, `grupos_puntos`, `puntos` | `GetSurfaceIds`, `GetSiteIds`, **`PointGroups`**, **`CogoPoints`** |
| Redes hidrosanitarias | `redes_gravedad`, `redes_presion`, `cuencas` | `GetPipeNetworkIds`, `GetPressurePipeNetworkIds`, `GetCatchmentIds` |
| Planos y cantidades | `grupos_view_frame`, `vistas_seccion`, `estilos` | `GetViewFrameGroupIds`, `GetSectionViewIds`, `Styles` |

En negrita, las familias que en Civil 3D 2027 son **propiedades de coleccion** y no
metodos `GetXxxIds` (verificado en vivo). Cada alias lleva varios candidatos y gana el
primero que exista, asi que el mismo alias sirve si Autodesk cambia la forma.

Los nombres son alias; `listar_colecciones` devuelve el miembro real
(`GetAlignmentIds`, `GetCorridorIds`, ...) con su conteo y acepta cualquiera de los dos.

## Reglas de la plataforma 2027 (documentacion de Autodesk)

- AutoCAD/Civil 3D **2027 = release 26.0**, SDK .NET soportado **10.0**. Por eso el
  bundle declara `SeriesMin="R26.0"` y `SeriesMax="R26.0"` con `Platform="Civil3D"`:
  Autodesk indica exactamente eso para plugins de 2027, y un PackageContents mal
  configurado es causa documentada de caidas al arrancar.
- Civil 3D **no** referencia `Microsoft.AspNetCore.App`. Un plugin que dependa de ese
  framework no carga sin parchear `acdbmgd.runtimeconfig.json` de la instalacion.
  Este puente usa `TcpListener` de la BCL justamente para no tocar nada de eso.
- `SECURELOAD`/`TRUSTEDPATHS`: AutoCAD solo carga codigo de ubicaciones confiables.
  `%APPDATA%\Autodesk\ApplicationPlugins` lo es; por eso el instalador despliega ahi
  y no usa `NETLOAD`.

## Limitaciones conocidas

- **Dialogos modales y modo edicion**: cada peticion se ejecuta en el hilo principal
  desde el evento `Application.Idle`, que solo dispara cuando Civil 3D no esta en un
  comando ni en un dialogo. Si lo esta, la peticion vuelve con el codigo `-32000` a
  los 55 s. No se reintenta en bucle: se cierra el dialogo y se repite.
- **Por que Idle y no `ExecuteInApplicationContext`**: ese metodo cambia de contexto
  de documento a contexto de aplicacion, ambos ya en el hilo principal; no marshala
  desde un hilo de fondo. Llamado desde el hilo del socket ejecuta el delegado en ESE
  hilo: las lecturas simples pasan, pero abrir una transaccion lanza "The calling
  thread cannot access this object because a different thread owns it" y el dialogo
  modal resultante cuelga a Civil 3D. Verificado en vivo el 2026-10-10.
- Los exportes que solo existen como comando con dialogo (LandXML entre ellos) no
  tienen herramienta: `ejecutar_comando` no puede responder dialogos.
- `invocar_metodo` resuelve sobrecargas por cantidad y tipo de argumentos; si hay
  varias compatibles toma la primera que acepte la conversion.
- Civil 3D 2026 y anteriores no estan soportados: el puente compila contra .NET 10 y
  el bundle declara la serie R26.0.
- Validado en vivo el 2026-10-10 contra Civil 3D 2027 en gdcwindows con
  `11 CORREDOR.dwg`: ping, `doc.info`, `civil.colecciones` (10 colecciones con
  objetos), `objects.query` y `types.discover` (3,364 objetos del espacio modelo
  clasificados por tipo .NET y clase RX). Las herramientas de escritura y
  `invocar_metodo` aun no tienen corrida real.

## Herramientas

Catalogo con parametros y ejemplos: [`herramientas.md`](herramientas.md).
