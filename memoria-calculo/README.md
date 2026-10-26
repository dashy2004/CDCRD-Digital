# Memorias de diseño — versión 0.1

Genera una **memoria revisable** en HTML, Word editable y PDF desde un expediente JSON y documentos existentes. Conserva valores, unidades, referencias y pendientes; empaqueta las fuentes con SHA-256 y comprueba que no cambiaron durante la generación. No abre ETABS/SAFE ni modifica modelos.

El primer perfil es `structural_concrete_frame_v1`. El documento es un borrador si falta una declaración necesaria. `ready_for_review` significa cobertura documental declarada: **nunca aprobación del diseño ni vigencia comprobada del análisis**. Los números del ejemplo son inventados.

## Inicio en Windows

GENERAL — ejecutar desde la raíz de este repositorio. La carpeta de salida debe ser nueva y quedar fuera de las raíces de fuentes. No use como salida una carpeta de proyectos existente.

```powershell
$RepoRoot = (Get-Location).Path
$ExampleOutput = Join-Path $env:TEMP ('cdcrd-memoria-' + [guid]::NewGuid().ToString('N'))
py -3.12 -m venv (Join-Path $RepoRoot 'memoria-calculo/.venv')
$MemoriaPython = Join-Path $RepoRoot 'memoria-calculo/.venv/Scripts/python.exe'
& $MemoriaPython -m pip install -e './memoria-calculo[dev]'
& $MemoriaPython -m cdcrd_memoria.cli demo --output $ExampleOutput
```

`demo` crea `inputs/`, `expediente.json` y `paquete/`. Este último contiene:

| Archivo | Uso |
|---|---|
| `memoria.docx` | Cuerpo editable e inventario de anexos; no convierte las páginas PDF en texto Word |
| `memoria.pdf` | Cuerpo, índice con rangos globales, anexos seleccionados y marcadores |
| `memoria.html` | Vista local escapada, sin scripts ni recursos externos |
| `expediente.json` | Expediente portable, con rutas relativas a las copias en `fuentes/` |
| `presentacion.json` | Contenido común utilizado por los tres formatos |
| `validacion.json` | Cobertura calculada, datos pendientes y límites de revisión |
| `manifest.json` | Hashes de entradas/salidas, versión, conservación de fuentes y paginación PDF |
| `fuentes/` | Copias exactas de las evidencias; pueden contener información privada |

Si una operación falla, conserva `INCOMPLETE` y no se entrega un manifiesto de éxito. Para reintentar, seleccione otra salida; la herramienta no limpia ni sobrescribe paquetes anteriores.

## Trabajar con un expediente

Rutas de fuentes y `source_roots` relativas a la carpeta del expediente. Una raíz debe ser una carpeta existente. Configure raíces específicas (`inputs/`), no todo el disco. Cada fuente requiere su SHA-256 esperado. Un hash comprueba identidad de bytes, no autenticidad ni corrección técnica.

```powershell
& $MemoriaPython -m cdcrd_memoria.cli validate './memoria-calculo/examples/expediente.json'
& $MemoriaPython -m cdcrd_memoria.cli inspect './memoria-calculo/examples/expediente.json'
& $MemoriaPython -m cdcrd_memoria.cli prepare './memoria-calculo/examples/expediente.json'
& $MemoriaPython -m cdcrd_memoria.cli render './memoria-calculo/examples/expediente.json' --output $ExampleOutput
```

Use una salida distinta si ya ejecutó el ejemplo `demo`. `validate` y `prepare` son puros: **no leen ni certifican fuentes**. `inspect` comprueba los archivos y `render` repite la comprobación, copia evidencias y vuelve a comprobar los originales. Código de salida: 0 operación correcta, 2 error; un borrador válido puede retornar 0 aunque tenga pendientes.

El esquema generado está en [schemas/expediente.schema.json](schemas/expediente.schema.json). `cdcrd-memoria schema` imprime el mismo contrato. Reglas principales:

- Números finitos y unidades explícitas; `null` con motivo para valores ausentes. El texto descriptivo requiere unidad `texto`; una cadena como `"123"` no sustituye un número JSON. No se redondea para presentación, no se convierten unidades ni se ejecutan fórmulas. Se usa precisión numérica JSON/Python (no aritmética decimal arbitraria).
- Cada valor transcrito indica fuente y localizador. `verified` es una declaración del responsable, no una verificación automática del generador.
- Todo resultado presente identifica modelo/revisión, caso, sistema de coordenadas, ejes, componente y origen. Los ejes locales se conservan; no existe transformación implícita a globales. La estación necesita unidad.
- Puede haber varios modelos; dos revisiones del mismo ID de modelo no se mezclan. IDs de registros duplicados y referencias rotas se rechazan.
- La edición normativa se declara, no se sustituye por una edición considerada actual. Una exclusión `not_applicable` necesita motivo, revisor y evidencia.
- El generador mantiene `engineering_approval=false` y `analysis_freshness=unverified`, incluso con toda la cobertura declarada.

## Importar la captura ETABS existente

Registre primero el archivo `cdcrd-etabs-capture/1` como una fuente JSON con su hash y tipo `snapshot`. Luego:

```powershell
& $MemoriaPython -m cdcrd_memoria.cli import-etabs './expediente.json' --source-id CAPTURE --output './memoria-importada'
```

El comando crea otro paquete. Importa inventario (niveles, nudos, barras, losas, muros y patrones), unidades declaradas y alturas/cotas expresadas en metros por el esquema de captura. No deduce derivas, espectros, P-Delta, punzonamiento ni esfuerzos a partir del inventario. Datos no capturados quedan ausentes. Cada observación importada queda pendiente de cotejo. Reimportar el mismo ID genera un error por duplicidad; revise y prepare otra revisión deliberadamente.

El adaptador lee JSON existente; no llama `_select_output_cases`, `RunAnalysis`, `Save`, COM ni ningún setter. Véase el [auditor ETABS](../servidor-mcp/docs/AUDITOR-ETABS.md).

## MCP local

El paquete instala `cdcrd-memoria-mcp` y también admite `python -m cdcrd_memoria.server`. Usa stdio, sin puerto HTTP y sin modificar automáticamente la configuración de sus clientes.

```toml
[mcp_servers.memoria_calculo]
command = 'C:\ruta\CDCRD-Digital\memoria-calculo\.venv\Scripts\python.exe'
args = ['-m', 'cdcrd_memoria.server']
```

Sustituya la ruta por su entorno. No se debe añadir esta configuración a ciegas a una sesión activa: primero instale el paquete y compruebe su CLI.

| Herramienta | Entradas | Efecto |
|---|---|---|
| `memoria_inspeccionar_fuentes` | `expediente`, `base_directory`, `limits` opcional | Lee archivos registrados y comprueba hashes/límites |
| `memoria_validar_expediente` | `expediente` | Valida contrato/cobertura sin acceder al disco |
| `memoria_preparar` | `expediente`, `template_id` opcional | Devuelve presentación común sin escribir |
| `memoria_generar` | `expediente`, `base_directory`, `output_directory`, `formats` opcional | Crea paquete nuevo; formatos `html`, `docx`, `pdf` |

`base_directory` debe ser la carpeta desde la que se resuelven las rutas relativas del JSON. Las anotaciones MCP distinguen las tres lecturas de la generación de archivos. La prueba de integración inicia un servidor real por stdio, lista las cuatro herramientas y las invoca.

## Límites de entrada y anexos

Solo archivos explícitos: JSON, CSV, TXT, PDF, PNG y JPEG. No se recorren carpetas, descomprimen archivos, ejecutan macros ni recalculan Excel. Esta versión no extrae automáticamente el contenido de Word/Excel históricos ni convierte imágenes en figuras de cálculo; deben transcribirse con evidencia o incluirse en un anexo PDF preparado por el responsable.

Topes duros: 100 archivos, 256 MiB por archivo, 512 MiB en conjunto, JSON de 8 MiB y PDF ensamblado de hasta 2000 páginas. `limits` admite `files`, `file_bytes` y `total_bytes` solo para reducirlos. Los límites de bytes/páginas no constituyen una cuota de CPU/RAM frente a un PDF malicioso; procese documentos de procedencia confiable en un directorio controlado.

Los anexos PDF cifrados o inválidos se rechazan. También se rechazan campos de formulario, notas, sellos y otras anotaciones visibles o desconocidas: eliminarlas podría borrar evidencia. Prepare una copia aplanada y revisada antes de registrarla. `pages` usa numeración original desde 1 y permite una selección ordenada sin duplicados. El ensamblado elimina enlaces sin apariencia, acciones y adjuntos; añade una franja inferior para numeración global sin cubrir el contenido original. Las copias bajo `fuentes/` conservan los bytes originales (y sus posibles contenidos activos): la herramienta no las ejecuta ni las abre en una aplicación. La numeración y firma originales no se presentan como firma del documento compuesto.

Las guardas resuelven rutas/enlaces y rechazan salidas dentro de las fuentes, existentes o que las contengan. No sustituyen un sandbox ante un atacante que reescriba el sistema de archivos simultáneamente. No publique paquetes reales en este repositorio: pueden contener datos privados en fuentes, títulos y localizadores.

## Verificación y alcance pendiente

```powershell
& $MemoriaPython -m pytest memoria-calculo/tests -q
& $MemoriaPython -m ruff check memoria-calculo
```

La CI ejecuta las pruebas del paquete en Linux y Windows. Las pruebas cubren el contrato, ejes girados, revisiones incompatibles, fuentes cambiantes, rutas, paquetes incompletos, anexos y MCP stdio. La comprobación visual del ejemplo se documenta en [docs/VALIDACION.md](docs/VALIDACION.md).

Seguimiento: [#41](https://github.com/dashy2004/CDCRD-Digital/issues/41). Quedan el piloto con un proyecto autorizado y revisión profesional, ampliación de capturas ETABS/SAFE, perfiles adicionales, figuras y extracción controlada de memorias históricas. Dependencias nativas: #14, #15, #18, #20, #21, #29 y #30. No se cierran mediante la creación de documentos.
