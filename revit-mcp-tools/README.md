# revit-mcp-tools

Herramientas MCP para Revit que un agente puede ejecutar sin interfaz. Son la
conversión de los pushbuttons de `revit-mcp-write/RevitWrite.extension` a
funciones puras `run(doc, uidoc, DB, P) -> dict`, enviadas por el canal
`POST /revit_mcp/execute_code/` de pyRevit Routes (el mismo que usa
`mcp-server-for-revit-python`). No requiere tocar pyRevit ni reiniciar Revit
para agregar una herramienta.

```
cliente MCP --stdio--> src/server.py --HTTP--> pyRevit Routes (Revit.exe)
                                              /revit_mcp/execute_code/
```

## Requisitos

- Revit 2027 con pyRevit 6.5 (IronPython 3.4) y la extensión
  `mcp-server-for-revit-python` cargada (aporta el endpoint).
- Python 3.10+ con `mcp<2` para el servidor.
- El puerto se descubre por sondeo en 48884..48891 y se cachea.

## Instalación (Claude Desktop)

```json
"revit-tools": {
  "command": "C:\\ruta\\a\\python.exe",
  "args": ["C:\\ruta\\a\\CDCRD-Digital\\revit-mcp-tools\\src\\server.py"]
}
```

## Herramientas

| Tool | Origen | Estado |
|---|---|---|
| `revit_estado` | `_Estado` | verificada |
| `revit_inventario` | `_Inventario` | verificada |
| `revit_vigas` | `_Vigas` | verificada |
| `revit_losas_muros` | `_LosasMuros` | verificada |
| `revit_guardar_modelo` | `GuardarModelo` | escrita (no se ejecutó en la conversión) |
| `revit_material_vigas` | `MaterialVigas` | verificada en `dry_run` |
| `revit_sin_hatch_material` | `SinHatchConcreto` | escrita |
| `revit_tags_vigas` | `TagsVigas` | verificada (idempotente) |
| `revit_tags_elementos` | nueva (columnas 45°, losas, muros) | verificada |
| `revit_color_acero` | `ColorAcero` | escrita, sin acero en el modelo de prueba |
| `revit_porticos_por_eje` | `CrearVistaPorticoD` + `VistasPorticoVC` | verificada |
| `revit_cotas_ejes` | nueva | verificada |
| `revit_exportar_hojas` | nueva | verificada (DXF) |
| `revit_acero_vigas` | `GenerarAceroVigas`, regla como parámetro | `dry_run` verificado; creación sin verificar |
| `revit_acero_columnas` | nueva (regla por caras; `AceroColumnasC6` solo copiaba) | `dry_run` verificado; creación sin verificar |
| `revit_ejecutar_tool` | genérica: cualquier `tools/<name>.py` | verificada por el harness |
| `revit_listar_tools` | — | — |

Todas las tools de escritura abren una sola transacción con rollback y
devuelven conteos verificables. Ninguna guarda: llamar `revit_guardar_modelo`
después de cada escritura (regla heredada del pushbutton GuardarModelo).

## Agregar una herramienta

1. Crear `src/tools/<nombre>.py` con docstring y `def run(doc, uidoc, DB, P)`.
   IronPython 3.4: sin f-strings ni anotaciones. Helpers de `_common.py`
   disponibles sin importar (`collector`, `tx`, `find_view`, `eidv`, `mm`…).
2. Probar con `revit_ejecutar_tool(name, params)` o con el harness de
   `execute_revit_code` (leer el archivo, concatenar `_common`, ejecutar).
3. Registrar un wrapper tipado en `server.py` si va a usarse seguido.

## Reglas de armado como datos

`acero_vigas` y `acero_columnas` no traen ningún armado embebido: la regla
(cantidades, diámetros, espaciamientos, zonas) llega en cada llamada, o por
nivel / por tipo. Las verificaciones de reglamento (espaciamiento máximo de
estribos en zona confinada y central, separación libre mínima entre barras)
se calculan con límites por defecto tipo ACI 318 y se devuelven como texto;
para otro reglamento se pasan `limites` explícitos. Con `dry_run=True`
(default) devuelven geometría y verificaciones sin escribir.

## Pendientes de conversión

Del panel original quedan sin convertir: `_Constraints`, `_Zapatas`,
`Borrado`, `Faltantes`, `Reemplazo`, `SubirColumnas`, `ArmarZapatas`,
`MoverZapatas`, `TiposZapata`, `Solape`, `SolapeDiag`, `VistaAcero`,
`CrearV4`, `DividirVigasEnColumnas`, `_ArmarV2`. Fuera de este repo, en la
extensión de proyecto, quedan `LosasAligeradas` (1 742 líneas) y
`AceroLosasAligeradas` (2 863), que dependen de leer bovedillas de un CAD y
de una tabla del plano; su conversión exige primero separar la lectura del
CAD (entrada) de la colocación (salida) y parametrizar la tabla.
