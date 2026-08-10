# SAFE MCP v0.1.0

Servidor MCP para SAFE (CSI), hermano de `servidor-mcp/` (ETABS). Construido
el 2026-08-10 a partir de dos fuentes:

1. El código real de `servidor-mcp/src/` (Etabs.py, oapi.py, comthread.py,
   config.py, server.py), copiado y adaptado en lo que es genérico
   (`comthread.py`, `oapi.py` son idénticos, solo cambia el nombre del
   logger).
2. El SOP interno de la firma (`Pasos.pdf`, sección "Safe", páginas 23-51),
   que define qué operaciones hace un ingeniero manualmente en SAFE y en qué
   orden: exportar desde ETABS, definir materiales/secciones de losa y
   zapata, resorte de suelo, combinaciones, franjas de diseño, correr
   análisis y diseño, revisar presión de contacto y punzonamiento, exportar
   DXF para detallar.

## Estado: primera versión, sin verificar contra una instalación real

Esta sesión no tuvo Windows ni SAFE disponibles. Nada de este código corrió
contra un modelo real. Antes de usarlo en un proyecto:

1. Instalar dependencias: `pip install -r requirements.txt` con el mismo
   intérprete que usa Claude Desktop (ver `instalar-safe.ps1`, que ya
   referencia esa ruta).
2. Abrir SAFE con un modelo cargado.
3. Correr `python diagnose_safe.py`. Este script **no asume el ProgID COM de
   SAFE** (a diferencia de `diagnose_etabs.py`, que ya lo tiene confirmado
   para ETABS): prueba una lista de candidatos y reporta cuál conecta. Si
   ninguno conecta, el script indica cómo buscarlo en el registro de Windows.
4. Copiar el `prog_id` (y `helper_prog_id` si aplica) que reportó el
   diagnóstico a `src/config.json`.
5. Correr `instalar-safe.ps1` para agregar la entrada `safe` a Claude
   Desktop (no toca la entrada `fea` existente).
6. Reiniciar Claude Desktop desde la bandeja (no solo cerrar la ventana) y
   abrir una conversación nueva.

## Qué está verificado y qué no

Verificado por el propio SOP de la firma (no por prueba en vivo de este
código):

- SAFE recibe el modelo desde ETABS vía `Export > Story as SAFE F2K File`
  (ETABS) → `Import > SAFE .f2k Text File` (SAFE). Este servidor todavía no
  automatiza ese paso (no hay `import_f2k` en `Safe.py`); es el primer hueco
  a cerrar una vez que el resto esté probado.
- SAFE tiene "Interactive Database Editing", la misma infraestructura de
  `DatabaseTables` que ya usa el servidor de ETABS (`list_tables`,
  `get_table_data`, `set_table_data`). Es el mecanismo más confiable para
  leer presión de contacto contra el suelo y resultados de punzonamiento,
  y para pegar combinaciones de carga desde la plantilla Excel de la firma.
- Las secciones de losa/zapata en SAFE tienen un tipo (`Slab`, `Drop`,
  `Stiff`, `Footing`) y espesor.
- El resorte de suelo se define como `k = 1.2 × σ_admisible`, con opción
  "Compression Only".

Con confianza razonable pero **sin confirmar en esta instalación** (porque
SAP2000/ETABS/SAFE comparten arquitectura de OAPI para lo genérico):
`PropMaterial`, `PointObj`, `AreaObj`, `LoadPatterns`, `RespCombo`,
`DatabaseTables`.

**No verificado, mejor conjetura, marcado en el código con comentarios
explícitos** — confirmar con `describe_oapi` antes de confiar en el
resultado:

- El ProgID COM de SAFE (`_PROGID_CANDIDATES` en `Safe.py`).
- El nombre exacto del método de `PropArea` para definir secciones de losa
  con `Type=Footing/Drop/Stiff` (`define_slab_section`).
- El namespace y método del resorte de área (`PropAreaSpring`,
  `define_soil_spring` / `assign_area_spring`).
- El namespace de diseño de losa (`DesignConcreteSlab` vs `DesignConcrete`,
  `run_slab_design`).
- El método de exportación a DXF (`export_dxf`).

Cada uno de estos métodos usa `oapi.call` con varias variantes candidatas
(mismo patrón tolerante que ya prueba su valor en el servidor de ETABS): si
la primera falla, prueba la siguiente, y si todas fallan el error dice
exactamente qué se intentó. `describe_oapi(path=..., filter=...)` está
disponible como herramienta MCP para consultar los namespaces y métodos
reales de la instalación antes de corregir cualquier función.

## Verificado en vivo — 2026-08-10

Conexión real confirmada: SAFE v23.3.0, OAPI v2.016, ProgID
`CSI.SAFE.API.ETABSObject` (ya fijado en `config.json`; el sondeo de
`diagnose_safe.py` ya no hace falta en esta máquina). ETABS v23.3.0 también
conectado en paralelo vía el servidor `fea`, misma versión de OAPI — refuerza
que ambos productos comparten arquitectura.

Con `describe_oapi` contra el modelo real se corrigieron 3 bugs y se
confirmaron 4 firmas que antes eran conjetura:

- `list_tables` y `get_table_data` desempaquetaban mal la respuesta de
  `DatabaseTables` (bug real, corregido).
- `set_table_data` perdía un valor de retorno de `ApplyEditedTables` (bug
  real, corregido).
- `define_soil_spring` / `assign_area_spring`: firma confirmada
  (`PropAreaSpring.SetAreaSpringProp`, `AreaObj.SetSpringAssignment`).
- `run_slab_design`: el método real es `DesignConcreteSlab.StartSlabDesign`,
  no `StartDesign` (corregido). Se agregó `get_slab_design_summary` para
  leer el acero resultante por franja.
- `export_dxf` no existía como método dedicado: `cFile` solo tiene
  `ImportFile`/`ExportFile` genéricos con un código numérico de tipo de
  archivo (enum `eFileType`) que la introspección de tipos no expone con
  nombres. Reemplazado por `import_file`/`export_file` genéricos — falta
  el valor numérico exacto para F2K y DXF, que solo sale de la ayuda oficial
  de la OAPI de SAFE (`Help > CSI OAPI Documentation` dentro de SAFE) o de
  prueba y error.

Del lado ETABS (servidor `fea`), confirmado con la misma técnica: existen
`PropFrame.SetModifiers` / `PropArea.SetModifiers` (reducción de inercia,
pendientes de exponer como herramienta), `SapModel.SourceMass` (masa modal,
namespace real distinto del que se había supuesto: no es "MassSource" sino
"SourceMass"), `SapModel.DesignShearWall` (diseño de muros de corte,
pendiente de exponer). No se encontró un namespace de "Panel Zone" con ese
nombre en esta versión — pendiente de ubicar bajo otro nombre o confirmar
que no está expuesto por la OAPI.

## Qué falta (fuera del alcance de esta primera versión)

- `import_f2k`: automatizar el paso "abrir en SAFE el .F2K exportado desde
  ETABS", hoy manual.
- Franjas de diseño (`Design Strips`, SOP pág. 46): no hay ninguna
  herramienta todavía; namespace no identificado.
- Ninguna herramienta de este servidor escribe de vuelta hacia Revit. Ese es
  un frente aparte, ya reportado por separado: las herramientas de Revit
  conectadas hoy en Claude son de solo lectura.
