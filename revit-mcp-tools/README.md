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

## Herramientas agregadas 2026-09-06: modelar, verificar, documentar, exportar

Con estas el agente ya no depende de un modelo hecho por alguien: lo levanta
desde cero, lo mira, lo documenta y lo pasa a ETABS. Todas probadas en vivo
en Revit 2027 sobre un proyecto nuevo (receta `ejemplos/residencial-4n`,
30 pasos, 233 elementos) y sobre una copia de un modelo real.

### Verificación y documentación

| Tool | Qué hace | Nota |
|---|---|---|
| `revit_ver_vista` | exporta vistas o láminas a PNG para leerlas con visión | ninguna salida gráfica se da por buena sin mirarla |
| `revit_vista_3d` | vista 3D isométrica con caja de sección alrededor de lo marcado | para mirar lo que otra tool acaba de crear |
| `revit_auditar` | advertencias agrupadas, niveles sin planta, ejes invisibles, elementos sin nivel, rooms sin cerrar o que se fugan, vistas fuera de lámina, inventario por marca | solo lectura |
| `revit_vistas_planta` | una planta estructural / de piso / de cielo por nivel; sin underlay; corte y recorte al edificio | |
| `revit_tablas` | tablas de planificación por categoría; en `dry_run` lista los campos disponibles; CSV | |
| `revit_laminas` | láminas con cajetín; planta + tablas en franja derecha; detecta desborde y ajusta la escala | `reserved_right_mm` para la columna del cajetín |
| `revit_exportar_pdf` | láminas a PDF con el exportador nativo | rasterizar y mirar antes de entregar |
| `revit_exportar_ifc` | IFC4 / IFC2x3, opcionalmente solo lo visible en una vista 3D | |
| `revit_rooms` | crea rooms en los recintos cerrados de un nivel, los nombra por punto, informa áreas y fugas | |

### Modelado desde cero (todas con `dry_run=True` por defecto y marca en `Comments`)

| Tool | Qué hace | Trampa que resuelve |
|---|---|---|
| `revit_niveles_ejes` | niveles y ejes desde una rejilla corta o lista explícita | `Grid.Create` nace sin extensión vertical y no se ve en ninguna planta: maximiza y fija extremos |
| `revit_familias_cargar` | carga `.rfa` por ruta relativa a la biblioteca de Revit | no recorre los 7 575 archivos de la biblioteca |
| `revit_tipos` | duplica tipos de columna, viga, zapata, losa y muro y fija b/h o espesor | `Duplicate()` devuelve `ElementType`: se relee por Id; cada dimensión se lee de vuelta |
| `revit_columnas` | columnas en intersecciones de ejes o puntos, nivel base y tope | escribe los desfases aunque sean 0: si no, queda un Top Offset residual y las columnas del último nivel sobresalen |
| `revit_vigas_crear` | vigas por tramos entre ejes, `por_ejes` o líneas; informa extremos reales vs pedidos | autojoin mueve la `LocationCurve` |
| `revit_losas_crear` | losas por contorno, envolvente de ejes o celda; espesor releído | el espesor no se hereda del nombre del tipo |
| `revit_muros_crear` | muros por líneas o tramos de ejes, entre niveles; ancho releído | |
| `revit_zapatas` | zapata bajo cada columna del nivel más bajo; informa el hueco columna-zapata | la Z del punto se suma al nivel en `NewFamilyInstance` de fundaciones |
| `revit_borrar_por_marca` | borra lo creado por un agente (marca) y datums por nombre | niveles y ejes no tienen `Comments` |

### Puente Revit → ETABS

| Tool | Qué hace |
|---|---|
| `revit_exportar_proyecto` | escribe `proyecto.json` (esquema `docs/ESQUEMA-PROYECTO.md`) en metros, con bloque `etabs` traducido a los argumentos de `fea`: `set_stories`, `define_concrete_material`, `define_rect_section`, `create_objects_by_coordinates` |

Receta completa y runner sin cliente MCP: `ejemplos/residencial-4n/` y
`ejemplos/correr_receta.py`.

### Idempotencia y limpieza

Cada tool de creación pregunta primero qué hay (columna en el mismo punto y
nivel, viga con los mismos extremos, losa con el mismo centro y área, zapata
en el mismo punto) y lo salta; la segunda corrida crea 0. Lo creado lleva
`Comments = AGENTE:<tipo>:<etiqueta>`; `revit_borrar_por_marca` lo quita sin
tocar el resto. Los `except` que silencian cuentan y se devuelven en
`excepciones`: un filtro que se traga la excepción es exactamente el caso que
después no aparece en el reporte.

## Agregar una herramienta

1. Crear `src/tools/<nombre>.py` con docstring y `def run(doc, uidoc, DB, P)`.
   IronPython 3.4: sin f-strings ni anotaciones. Helpers de `_common.py`
   disponibles sin importar (`collector`, `tx`, `find_view`, `eidv`, `mm`,
   `ft`, `need_level`, `need_symbol`, `grids_info`, `grid_point`,
   `grid_segments`, `mark`, `has_mark`, `set_param`, `param_mm`, `dup_type`,
   `fix_datum`, `leave_view`, `errs`/`note`…).
2. Probar con `revit_ejecutar_tool(name, params)` o con el harness de
   `execute_revit_code` (leer el archivo, concatenar `_common`, ejecutar).
3. Registrar un wrapper tipado en `server.py` si va a usarse seguido.
4. Si crea algo: `dry_run=True` por defecto, marca en `Comments`, releer lo
   creado y devolverlo, y mirar el resultado con `revit_ver_vista`.

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
