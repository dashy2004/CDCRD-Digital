# Civil 3D Terrain Tools

Herramientas API para crear plataformas con taludes, superficies TIN de corte/relleno y secciones dinámicas. El cálculo geométrico independiente corre en Python; el complemento C# crea y verifica objetos nativos en Civil 3D. Versión experimental 0.2.1, probada en **Civil 3D 2027 / .NET 10 / Windows x64**.

![Excavación sintética verificada](docs/images/excavacion.png)

## Herramientas

| Entrada | Resultado | Control |
|---|---|---|
| `prepare_platform(triangles, Platform(...))` | Malla de plataforma, taludes hasta encuentro con terreno y volúmenes separados | Cobertura del dominio, continuidad en vértices y encuentro interior |
| `TerrainApi.Build(Request)` | `TinSurface` y `TinVolumeSurface`, con factores 1 | Elevaciones nativas en vértices/centroides y volumen independiente |
| `TerrainApi.Sections(Request)` | Alineamiento recto, grupo, líneas de muestreo, secciones y vistas | Fuentes explícitas; estilo propio; H=V; nombres protegidos |
| `TerrainApi.Audit(Request)` | JSON con TIN, volúmenes, COGO y secciones | Lectura del dibujo activo identificado por ruta |
| `profile_at_x` / `section_areas` | Perfiles y áreas separadas de corte/relleno | Integra segmentos lineales y separa cruces de signo |
| `examples/verify_demo.py` | Comparación TIN, secciones y persistencia | Falla si se supera la tolerancia |

El comando **`CDCRDEARTHWORKS`** recibe la ruta absoluta de un JSON con `action: build`, `sections` o `audit`. No necesita el puente MCP ni conexión a Internet. Para integrarlo en otro complemento, use `Cdcrd.Earthworks.TerrainApi` desde el contexto de comando/documento de Civil 3D; el llamador debe garantizar exclusión de escritura y contexto correcto.

## Instalación y ejemplo reproducible

Requiere una instalación local licenciada de Civil 3D 2027, SDK .NET 10 y Python 3.10+. No se distribuyen bibliotecas de Autodesk. Desde esta carpeta, en PowerShell:

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
dotnet build plugin/TerrainTools.csproj -c Release
# Instalación en otra ruta:
# dotnet build plugin/TerrainTools.csproj -c Release -p:Civil3DPath="D:\Autodesk\AutoCAD 2027"

py examples/prepare_demo.py --drawing "C:\TerrainDemo\demo.dwg" `
  --receipts "C:\TerrainDemo\receipts" --requests "C:\TerrainDemo\requests"
```

1. Cree un dibujo **vacío**, configure **AutoCAD `INSUNITS=6` y Civil DrawingUnits=Meters** (Drawing Settings → Units and Zone), guárdelo en la ruta exacta elegida. Trabaje sobre una copia cuando use datos existentes.
2. Cargue `plugin/bin/Release/Cdcrd.Earthworks.dll` con `NETLOAD`. Si aparece el aviso de seguridad, revise el archivo y resuélvalo manualmente. No cambie las políticas de seguridad. Una DLL recompilada no reemplaza automáticamente la que ya está cargada.
3. Ejecute `CDCRDEARTHWORKS` una vez por JSON, en este orden: `build-flat.json`, `build-sloped.json`, `sections-flat.json`, `sections-sloped.json`, `audit.json`. Espere el mensaje final y revise `ok: true` en cada recibo antes del siguiente.
4. Guarde el dibujo, ciérrelo y ábralo de nuevo. Cambie **solo** el `runId` del JSON de auditoría a `demo-reopened` y vuelva a auditar. No repita los JSON de creación.
5. Compruebe los dos estados:

```powershell
py examples/verify_demo.py "C:\TerrainDemo\receipts\demo-reopened-audit.json" `
  --before "C:\TerrainDemo\receipts\demo-audit-audit.json" `
  --output "C:\TerrainDemo\verification.json"
```

Los recibos incluyen la identidad del ensamblado cargado. Un recibo existente se conserva y bloquea la repetición. Un fallo de escritura del recibo **después** de una transacción confirmada puede dejar cambios en el dibujo: en caso de resultado incierto, audite antes de reintentar. El complemento no guarda, cierra ni reabre dibujos por sí mismo.

## Geometría y unidades

Plataforma rectangular paralela a los ejes XY, fondo horizontal `width × length`, cota `elevation`, talud `horizontal_per_vertical` = **H:V**. Desde el borde, las cotas de encuentro son `z0 + d/m` para corte y `z0 - d/m` para relleno; se conserva el terreno cuando está entre ambas. `d` es la máxima distancia exterior normal a los lados. Las esquinas resultan de **intersecciones de planos**, con offsets cuadrados; no son esquinas circulares. La pendiente diagonal tiene una relación H:V distinta de la normal a cada lado.

Todos los datos deben estar en metros, con un datum vertical coherente. `build` y `sections` rechazan tanto INSUNITS incompatible como Civil DrawingUnits distinto de Meters antes de abrir una transacción. No convierten coordenadas ni corrigen unidades automáticamente. `audit` permite leer dibujos incompatibles para diagnosticarlos: informa ambas unidades, `metricDrawingUnits` y las expresiones de los estilos usados por las vistas de sección. Un indicador métrico del dibujo no garantiza por sí solo unidades métricas en las etiquetas. El dominio es un rectángulo mayor que la plataforma y debe contener completamente el encuentro con terreno. El TIN de entrada debe ser continuo, sin solapes, huecos ni triángulos degenerados. La comprobación de área no sustituye una validación topológica: un hueco y un solape de igual área podrían compensarse.

La malla se obtiene recortando cada triángulo por las regiones planas, por el dominio y por los cruces corte/relleno. Se integra cada porción como área por diferencia media de elevación. La malla nativa conserva las aristas mediante `AddFrom3DFaces`. Tolerancias: XY redondeado a 1e-8 m, Z a 1e-9 m; comprobación nativa de elevación 1e-6 m; volumen predeterminado 0,0001 m³. No hay factores de esponjamiento o compactación.

## Demostración y evidencia

Toda la galería usa **geometría ficticia local**, reproducible mediante el ejemplo. Son vistas exportadas por el motor de trazado de Civil 3D, presentadas con títulos y leyendas; no son capturas del escritorio. No se publican modelos de clientes, rutas personales ni coordenadas de levantamientos.

| Caso | Fondo / plataforma | Talud normal H:V | Corte TIN (m³) | Relleno TIN (m³) |
|---|---:|---:|---:|---:|
| Excavación sobre terreno Z=10 | Z=8; 12×6 m | 1,5:1 | 276,000000 | 0 |
| Relleno sobre terreno Z=10 | Z=12; 12×6 m | 1,5:1 | 0 | 276,000000 |
| Mixto sobre Z=10+0,05X | Z=10; 12×6 m | 2:1 | 6,444444 | 6,444444 |

Para los dos casos de profundidad constante: `V = W L h + m(W+L)h² + (4/3)m²h³ = 276 m³`. La verificación por áreas extremas promedio de secciones es una aproximación diferente del TIN; debe estudiarse la convergencia del intervalo. El ejemplo utiliza 0,25 m.

![Relleno sintético](docs/images/relleno.png)
![Plataforma mixta sintética](docs/images/mixta.png)
![Secciones nativas](docs/images/secciones.png)
![Verificación de volúmenes](docs/images/verificacion.png)

Resultados y procedencia: [verificación nativa](docs/native-verification.json), [contrato API](docs/API.md), [alcance de las pruebas](docs/VALIDACION.md).

La corrección 0.2.1 verifica las unidades de AutoCAD, Civil y las vistas de sección. Evidencia actual: [regresión métrica](docs/native-units-verification.json) y [sección exportada](docs/images/unidades-metricas.png). La galería 0.2.0 anterior se conserva como antecedente.

## Alcance actual

Son ejercicios geométricos y herramientas de automatización; la relación de talud elegida no acredita estabilidad geotécnica ni constituye diseño de excavación. No se generan `Grading`, feature lines, corredores, cubicaciones por materiales o bases Survey. No se interpretan automáticamente descripciones COGO ni se modifica su clasificación. Los módulos de terreno existentes pueden aportar el TIN, y este paquete trabaja con sus triángulos y su superficie base explícita.

Las superficies son independientes de la geometría de la plataforma en Python: editar los parámetros requiere una nueva ejecución con un namespace nuevo, o implementar una actualización futura. Las superficies de volumen y las secciones nativas sí mantienen referencias a sus fuentes. El constructor de secciones implementa únicamente un alineamiento recto. Los estilos se derivan de los primeros estilos disponibles; la estación del título y las cotas y títulos de los cinco ejes de las vistas nuevas se fijan explícitamente en metros sobre una copia propia del estilo. Los estilos de otros objetos se conservan. Revise la representación al cambiar de plantilla; la escala de anotación global se conserva. En la demo validada se ajustó manualmente a 0,1.

## Referencias API

- Autodesk: [AddFrom3DFaces, puntos y aristas](https://help.autodesk.com/cloudhelp/2022/ENU/Civil3D-API/files/html/18153f60-edbb-0c03-c125-933f768c59b7.htm).
- Autodesk: [fuentes de secciones](https://help.autodesk.com/cloudhelp/2018/ENU/Civil3D-DevGuide/files/GUID-611DE133-40A0-4F0F-8622-1489561AEC27.htm).
- Autodesk: [SectionView.Create](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/9911016a-842d-c899-5bb0-bf09bdc9db18.htm).
- Autodesk: [SectionPoint](https://help.autodesk.com/cloudhelp/2026/ENU/Civil3D-API/files/html/c19d4bb4-c946-9c3e-34f3-5c1a78903702.htm).

Las firmas también se compilaron y ejecutaron contra las bibliotecas instaladas de Civil 3D 2027; no se afirma compatibilidad con otras versiones.
