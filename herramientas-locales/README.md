# Herramientas locales AI + BIM + CDCRD

Núcleo gratuito ejecutable en Windows, separado de las sesiones Revit/ETABS/SAFE.
Incluye una CLI y un servidor MCP de 10 herramientas para que un cliente de IA
trabaje con archivos del repo. No incluye un modelo de IA ni una interfaz web.

## Instalación

Se requiere [uv](https://docs.astral.sh/uv/getting-started/installation/).
Desde la raíz del repositorio, en PowerShell:

```powershell
.\herramientas-locales\instalar.ps1 -Pruebas
.\herramientas-locales\cdcrd.ps1 doctor
```

El instalador crea `herramientas-locales/.venv`, usa Python 3.13 y las versiones
de `uv.lock`. No cambia los paquetes globales. Si la política de PowerShell
bloquea el script, puede ejecutarse en un proceso temporal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\herramientas-locales\instalar.ps1 -Pruebas
```

Para otros sistemas, desde esta carpeta: `uv sync --locked --python 3.13`,
seguido de `uv run --frozen cdcrd-local doctor`. La instalación y las pruebas
registradas en [VERIFICACION.md](VERIFICACION.md) corresponden a Windows.

## Funciones disponibles

| Operación | Implementación y alcance |
|---|---|
| JSON → DXF | ezdxf: polígonos, capas, cotas nativas y notas; unidades `m` o `mm` |
| Inspección DXF | Entidades, capas, unidades, límites y auditoría |
| DXF → SVG/PNG/PDF | Vista del espacio modelo mediante Matplotlib sin interfaz gráfica |
| Inspección IFC | IfcOpenShell: esquema, clases, inventario y unidades declaradas |
| IFC + IDS → HTML | IfcTester: requisitos de información; estados passed/failed/incomplete |
| PDF → PNG | PDFium: una página elegida; 36–300 DPI, máximo 50 millones de píxeles |
| Inspección PDF | Páginas, medidas en puntos y texto inicial; sin OCR |
| Búsqueda CDCRD | SQLite FTS5 sobre los cinco volúmenes; cláusula, título, volumen, páginas y archivo |
| Verificadores CDCRD | Adaptadores a seis scripts existentes con sus fuentes y resultados originales |

Las salidas se crean exclusivamente: un archivo existente produce un error.
IfcClash, Pint, Pydantic y Shapely también están instalados; IfcClash queda
disponible como biblioteca, sin flujo de interferencias añadido en esta versión.

## Ejemplo de plano reproducible

Desde la raíz del repo:

```powershell
.\herramientas-locales\cdcrd.ps1 generar-dxf .\herramientas-locales\ejemplos\planta-ejemplo.json .\herramientas-locales\salidas\planta.dxf
.\herramientas-locales\cdcrd.ps1 inspeccionar-dxf .\herramientas-locales\salidas\planta.dxf
.\herramientas-locales\cdcrd.ps1 preview-dxf .\herramientas-locales\salidas\planta.dxf .\herramientas-locales\salidas\planta.png
.\herramientas-locales\cdcrd.ps1 preview-dxf .\herramientas-locales\salidas\planta.dxf .\herramientas-locales\salidas\planta.pdf
.\herramientas-locales\cdcrd.ps1 preview-pdf .\herramientas-locales\salidas\planta.pdf .\herramientas-locales\salidas\pagina.png
```

El JSON de entrada declara `name`, `units`, `outlines`, `dimensions` y `notes`.
Cada contorno tiene `id`, `points` y una capa opcional; las cotas tienen `p1`,
`p2` y `offset`; las notas tienen `text` y `position`. Se rechazan números no
finitos, polígonos inválidos, IDs repetidos y campos desconocidos. Las cotas
utilizan los extremos recibidos, sin inferir ajustes a los contornos.

Este esquema describe primitivas 2D y es distinto de `proyecto.json` de Revit.
El ejemplo es una planta sintética de 6 × 4 m con anotación prevista para 1:50;
el preview ajusta el encuadre, sin garantizar escala de impresión. No incorpora
cajetín, láminas ni dimensionamiento de armaduras. La apariencia y las cotas
deben revisarse también en el CAD destinatario antes de entregar un plano.

## Consulta y verificación normativa

```powershell
.\herramientas-locales\cdcrd.ps1 buscar "2.10.11" --volumen 1
.\herramientas-locales\cdcrd.ps1 buscar "cargas vivas" --limite 5
.\herramientas-locales\cdcrd.ps1 verificar masa_modal .\herramientas-locales\ejemplos\masa-modal.json
```

Una consulta numérica recupera coincidencias exactas; las palabras usan búsqueda
AND con ranking textual. Los IDs duplicados se conservan por volumen, archivo
y ocurrencia. El texto puede truncarse a 2,500 caracteres, con indicador
explícito. `fuente_pdf` y `version_codigo` conservan los metadatos del corpus;
pueden ser nulos cuando el archivo no los declara. La búsqueda no selecciona
el régimen normativo de un expediente ni inventa fuentes ausentes.

Chequeos disponibles: `deriva`, `escalado_cortante`, `torsion`,
`irregularidades_verticales`, `masa_modal`, `zapata`. Cada entrada debe seguir
el contrato del script correspondiente en `herramientas/`. Los adaptadores
conservan sus límites; no convierten esos chequeos en una revisión integral.
La CLI devuelve 0 para una operación de archivos exitosa y 2 ante errores
de entrada/ejecución. IDS devuelve 1 para fallo o resultado incompleto.
Los verificadores CDCRD conservan el código de salida del script original:
hay que leer su resultado y alcance; en particular, el script de zapatas
devuelve 0 al ejecutarse incluso si reporta chequeos incompletos o fallidos.

Para IFC/IDS:

```powershell
.\herramientas-locales\cdcrd.ps1 inspeccionar-ifc .\modelo.ifc
.\herramientas-locales\cdcrd.ps1 validar-ids .\modelo.ifc .\herramientas-locales\salidas\ids.html --ids .\requisitos.ids
```

## Conectar un cliente de IA

El instalador genera `herramientas-locales/.local/mcp-config.json` con rutas de
esta máquina. Añadir la entrada `cdcrd-local` a la configuración MCP del cliente
que utilice servidores **stdio**, conservando sus entradas existentes. Esta
instalación genera el fragmento; no activa automáticamente todos los clientes.

Herramientas: `entorno_diagnosticar`, `cdcrd_buscar`, `cdcrd_verificar`,
`cad_generar_plano`, `cad_inspeccionar`, `cad_previsualizar`, `ifc_inspeccionar`,
`ifc_validar_ids`, `pdf_inspeccionar`, `pdf_previsualizar`.

El servidor acepta entradas dentro del repo y escribe exclusivamente bajo
`herramientas-locales/salidas`. Las rutas de salida MCP son relativas a esa
carpeta. La CLI permite rutas explícitas. Ni el entorno, ni las salidas, ni la
configuración local se publican en Git. Para iniciar manualmente:

```powershell
.\herramientas-locales\cdcrd.ps1 mcp
```

## Próximas incorporaciones

La [investigación](../docs/INVESTIGACION-HERRAMIENTAS-2026-10-08.md) y la
[matriz](../docs/MATRIZ-HERRAMIENTAS.csv) distinguen opciones evaluadas de
funciones instaladas. Ubuntu/WSL2, una VM completa, ODA para DWG, LibreCAD,
OCR y Ollama requieren instalaciones adicionales y quedan para una etapa
posterior. RVT y archivos nativos CSI siguen usando las aplicaciones y
conectores existentes. PDF→CAD/BIM y DWG→DXF no se implementan aquí.
