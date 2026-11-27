# Las tools de pilotes como "plugin": opciones sobre el flujo real (claude, 2026-11-02)

Pregunta de Emil: además de tools MCP, ¿pueden convertirse en plugins o algo parecido?
Flujo real de la oficina: Claude Desktop/Cowork y Codex como agentes, SAFE/ETABS/Revit
vivos en una sola máquina, Excel como entregable para el geotecnista y el firmante,
BRAIN como memoria y `CDCRD-Digital` público. Lo que ya existe y se reutiliza: el servidor
MCP de SAFE (`Safe.py`), el criterio puro (`pilotes.py`, `pilotes_xlsx.py`), la extensión
pyRevit (`plugin-losas`) y el servidor de ETABS (`servidor-mcp`).

Hallazgos que condicionan las opciones (comprobados en esta máquina):

- **SAFE 23 admite plugins de CSI.** El typelib `SAFEv1` declara `cPluginContract`
  (`Main(SapModel, ISapPlugin)`) y `cPluginCallback` (`Finish`, `ErrorFlag`), igual que
  ETABS, y hay `SAFEv1.dll` + `SAFEv1.comhost.dll` en `NativeAPI\x64`. Un plugin es un
  DLL .NET que SAFE carga desde Tools > Add/Show Plug-ins y que recibe `SapModel` ya
  conectado: botón dentro del programa, sin COM externo.
- **FastMCP sirve por HTTP además de stdio** (`mcp.run(transport="streamable-http")`):
  el mismo servidor puede recibir llamadas de un botón de Excel, de un plugin de SAFE o de
  un script, no solo de Claude.
- **El criterio es puro:** `pilotes.py` y `pilotes_xlsx.py` no saben de COM. Cualquier
  envoltorio (CLI, plugin, Excel) reutiliza exactamente el código que pasó los 266 tests
  y la corrida viva.

## Opciones, de más a menos recomendable para este flujo

| # | Forma | Qué sería | Esfuerzo | Para quién |
|---|---|---|---|---|
| 1 | **Plugin de Claude Code / Cowork** en `CDCRD-Digital` (`.claude-plugin/` con el servidor MCP de SAFE, skills y un hook) | Un `/pilotes` que guía el procedimiento completo (abrir copia → `get_pile_spacing` → analizar → `get_pile_axial_reactions` → `export_pile_check_xlsx` → nota en BRAIN) y un hook `PreToolUse` que bloquea `File.Save` y `save_model` sobre modelos de proyecto. El skill lleva el criterio R-024 escrito: Cowork y Codex lo ejecutan igual. | Bajo: manifiesto + SKILL.md + hook; nada de código nuevo. | Claude y Codex (ambos hablan MCP). |
| 2 | **CLI `cdcrd-safe`** sobre la misma clase `Safe` (lo que hizo la sonda de hoy sin servidor) | `cdcrd-safe pilotes --fdb modelo.FDB --q-adm 833.6 --xlsx salida.xlsx` abre, lee y exporta sin LLM; en lote para los cuatro bloques. Añadiendo `scan_sf_model` (lector del `.$sf`) audita modelos cerrados sin abrir SAFE. | Bajo-medio: `argparse` + reutilizar `_informe_*`; `scan_sf_model` aparte. | Codex, scripts, revisiones nocturnas. |
| 3 | **Plugin dentro de SAFE** (DLL .NET con `cPluginContract`) | Botón "CDCRD Pilotes" en Tools de SAFE que lanza el Python del servidor (o llama por HTTP al MCP) y abre el Excel al terminar; el ingeniero no sale de SAFE ni toca Claude. Precedente propio: pyRevit en Revit. | Medio: proyecto C# mínimo + puente a Python (proceso) o cliente HTTP; firmar y registrar el DLL. | El modelador y el firmante, sin agentes. |
| 4 | **Excel conectado**: el libro con un botón "Actualizar desde SAFE" (VBA o Office Script) que llama al servidor MCP por HTTP y rellena las hojas | Convierte el entregable en algo vivo: cambia el modelo, pulsa, y el libro se actualiza con la misma lógica. | Medio: exponer `export_pile_check_xlsx`/JSON por HTTP y escribir el cliente VBA. Riesgo: macros y seguridad de Office. | Geotecnista / revisor. |
| 5 | **Artefacto web** (página HTML desde el JSON de las tools): plano interactivo de pilotes coloreado por S/B y ratio, con filtro por cabezal | Lectura visual del mismo resultado; útil para la reunión con el geotecnista. Claude lo genera desde el JSON en segundos. | Bajo por pieza, pero no es reutilizable sin empaquetarlo. | Reuniones, informes. |
| 6 | **Cruce con ETABS/Revit** | ETABS: las reacciones de columna del `servidor-mcp` son la demanda que baja a SAFE; una tool que las compare con las reacciones de pilote cierra el circuito ETABS→SAFE. Revit: pyRevit que lea el Excel y marque en el modelo los pilotes "revisar"/"candidato" (pinta, no borra). | Medio-alto; depende de tener los dos modelos coherentes. | Modelador. |

## Recomendación

1. **Hacer ya el 1 y el 2**: son días, no semanas, y encajan con cómo trabaja la oficina
   (agentes + MCP + repo público). El plugin de Claude Code deja el procedimiento escrito y
   bloquea el `Save`; la CLI permite correr los cuatro bloques en lote y es el camino
   natural para `scan_sf_model`.
2. **Probar el 3 con un plugin vacío** que solo muestre un mensaje: confirma que SAFE 23
   carga `cPluginContract` (en ETABS está probado; en SAFE solo está en el typelib). Si
   carga, el botón "CDCRD Pilotes" es el que más valor da al ingeniero que no usa agentes.
3. El 4 y el 5 son capas sobre lo mismo; conviene tenerlas después de que el criterio se
   haya validado con el geotecnista (p. ej. el margen del 90 % para candidatos y el uso de
   85 t × ξ como admisible reducida).

Reglas que ninguna forma puede romper: solo lectura del modelo, criterio en un solo sitio
(`pilotes.py` / `pilotes_xlsx.py`), nada de nombres de proyecto en el repo público, y la
hoja reporta: no decide por el ingeniero firmante ni por el geotecnista.
