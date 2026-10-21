# Catálogo de capacidades y diagnóstico unificado

La CLI y el MCP comparten un registro de **12 módulos** de CDCRD-Digital.
El catálogo describe contratos por módulo; no enumera todos los métodos de las
API ni invoca herramientas de modelado.

## Consultar

Desde la raíz del repositorio, con el entorno instalado:

```powershell
.\herramientas-locales\cdcrd.ps1 capacidades
.\herramientas-locales\cdcrd.ps1 capacidades --modulo civil3d --json
.\herramientas-locales\cdcrd.ps1 estado --json
.\herramientas-locales\cdcrd.ps1 estado --modulo local --config .\herramientas-locales\ejemplos\mcp-diagnostico.json
```

Los dos comandos aceptan `--repo RUTA` y `--modulo ID`. La salida siempre es
JSON UTF-8; `--json` lo hace explícito. Un ID desconocido produce un error,
sin convertirlo silenciosamente en una consulta vacía.

| ID | Módulo |
|---|---|
| `local` | Archivos CAD/IFC/IDS/PDF, CLI y MCP local |
| `normativa` | Corpus normativo con procedencia |
| `revit` | Revit MCP tools |
| `revit-write` | Revit pushbuttons |
| `etabs` | ETABS OAPI y procedimiento |
| `safe` | SAFE OAPI |
| `civil3d` | Puente Civil 3D |
| `autocad` | Puente base AutoCAD |
| `terrain` | Terreno, taludes y secciones |
| `points-survey` | Preparación y verificación COGO/Survey |
| `beamng` | Exportación Civil 3D a BeamNG |
| `losas` | Intercambio Revit/FEM/ETABS |

Cada registro incluye entradas, salidas, operaciones de lectura/escritura,
unidades, aplicación requerida, puntos de entrada, documentación y referencias
a evidencia. `present` solo indica que el archivo existe dentro del repositorio.
La existencia de un informe no implica que sus pruebas se hayan repetido hoy.

`version` se lee de `pyproject.toml` cuando está declarada. Es una versión de
las fuentes, no de la aplicación ni del conector cargado. `version_status`
distingue `source_metadata`, `not_declared` e `invalid`; una versión ausente
permanece `null`. Las referencias simbólicas que salen del repositorio no se leen.

## Interpretar el diagnóstico

`estado` reutiliza el `doctor` existente, que conserva su interfaz. Su bloque
`environment` corresponde exclusivamente al entorno Python de
`herramientas-locales`; no certifica los entornos Python de los otros conectores.

| Campo | Significado |
|---|---|
| `source_available` | Están presentes los puntos de entrada declarados |
| `installed` | `null`: instalación de cada aplicación/conector no comprobada |
| `configured` | Configuración MCP declarada; `null` si no se examinó o no aplica |
| `configuration_invalid` | La entrada MCP existe pero no tiene estructura válida |
| `live_connection` | Siempre `not_checked` en este diagnóstico offline |
| `live_bim_connected` | Siempre `false`: no se estableció una conexión BIM |

Sin `--config`, no se buscan archivos privados globales. Con `--config`, se
acepta un único objeto `mcpServers` de JSON o `mcp_servers` de TOML, hasta 1 MiB.
Una entrada se reconoce por un `command` no vacío y argumentos de texto, o por
un `url` no vacío. Las entradas deshabilitadas se informan como no configuradas.
No se ejecutan comandos, se resuelven credenciales ni se contactan esas URL.
Un ejecutable o una URL declarados pueden no estar disponibles realmente.

Los nombres MCP reconocidos figuran en `mcp_servers` del catálogo. Una
configuración que use nombres personalizados no se identifica por inferencia.
Los comandos, argumentos, URL, variables de entorno y ruta de configuración no
se reproducen en la salida. El diagnóstico heredado sí conserva su información
de entorno Python, incluida la ruta del intérprete; revisarla antes de publicar
un informe real de una máquina.

**Códigos de salida:** `0` si las dependencias locales y fuentes seleccionadas
están presentes y, si se proporcionó configuración, los servidores MCP
seleccionados están declarados correctamente; `1` si alguna de esas comprobaciones
es negativa; `2` ante entradas o ejecución inválidas. Ni `0` ni `ok: true`
declaran una conexión viva ni una validación de ingeniería.

## MCP y compatibilidad

- `ecosistema_capacidades(modulo=None)` usa el mismo catálogo.
- `ecosistema_estado(modulo=None)` reutiliza `doctor` y comprueba las fuentes.

Estos dos accesos MCP no admiten rutas de configuración privada. Los diez
accesos anteriores siguen disponibles, incluido `entorno_diagnosticar`.
El registro vive en `src/cdcrd_local/capabilities.py`; añadir un módulo exige
declarar su contrato y referencias, sin importar ni ejecutar su código.

Las pruebas se describen en [CAPACIDADES-TDD.md](CAPACIDADES-TDD.md).
