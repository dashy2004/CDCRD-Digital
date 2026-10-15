# Que falta / limitaciones conocidas

Estado al 2026-10-15 (puente 0.5.0 en fuente; 0.4.1 cargado hasta el
reinicio del build final). Complementa `PENDIENTES.md` (backlog por
prioridad).

## Limites del puente

- **Un reinicio por build.** Cada compilacion del DLL exige cerrar y reabrir
  Civil 3D; `instalar.ps1` puede instalarse con Civil 3D abierto y el
  reinicio toma el build nuevo. Si `estado_puente` no cambia de `build`,
  quedo un `acad.exe` vivo.
- **El servidor MCP Python no se recarga solo.** Cambios en `src/*.py` se
  prueban por script TCP (`src/puente_cliente.py`), no por las herramientas
  `mcp__...` de la app, hasta reiniciar la app de Claude.
- **Dialogos modales congelan las peticiones** (vencen a 55 s). Diagnostico:
  `eventos_dialogo` / `leer_log_puente`. `ejecutar_comando` es asincrono y
  no sirve para comandos que abren dialogos.
- **La grilla de la vista de perfil se dibuja encima de los HatchAreas
  nativos** y ese orden interno no es controlable por API (los rellenos no
  son entidades independientes reordenables). Salida aplicada: estilo de
  vista propio con grilla tenue (`grilla_tenue`, `grilla_color_aci`,
  `estilo_vista_base` del spec del perfil estratigrafico).
- **SQLite sobre carpeta montada da `disk I/O error`**: el
  `GeotechnicalModeler.db` se copia a local antes de leerlo.
- **Plots por ventana salen casi vacios**: exportar siempre por vista
  guardada o por layout.
- **Layouts no se plotean centrados** (`SetPlotCentered` es `eInvalidInput`
  con `PlotType.Layout`): el puente plotea el layout desde su origen a 1:1.
- `cmd.run` sigue siendo dispara-y-olvida (sin captura de resultado por
  `CommandEnded`); getvar/setvar y lotes transaccionales con undo como
  unidad siguen en el backlog (P2).

## Geotechnical Modeler

- `ProfileService.CreateStickLogProfile` del GM tiene un
  `NullReferenceException` documentado en
  `BUG-GM-CreateStickLogProfile.md`; `gm_diagnosticar` revisa las
  precondiciones conocidas y `gm_crear_perfil_sondeos` captura la excepcion
  completa como evidencia. El flujo nativo (perfil estratigrafico 3.2 +
  isometricos 3.4) es el camino oficial del proyecto y no depende del GM.
- Las herramientas `gm_*` requieren que el contenedor IoC del GM este
  inicializado (algun comando del GM corrido en la sesion) y un proyecto GM
  activo en el dibujo.
- `gm_crear_perfil_sondeos` (como el propio GM) **borra todos los perfiles
  del alineamiento** antes de crear los suyos.
- Export 3D del GM (`Export3DService`) no esta expuesto todavia: su firma
  exige `StratumVisibilityDisplaySettings` armado desde la UI; evaluar si
  hace falta cuando el resto este verificado.

## Fuera de alcance (por decision)

- QGIS (3.5): se evaluara con un MCP de QGIS existente, no en este puente.
- Redes hidrosanitarias y planos/cantidades: backlog P2 en `PENDIENTES.md`.

## Pendiente de verificar en vivo (tras el proximo reinicio)

- `exportar_vista(layout=...)` con el fix de `SetPlotCentered` (lamina A3).
- Las seis herramientas `gm_*` y `eventos_dialogo` (DLL 0.5.0).
- `isometrico_sondeos_3d` ya quedo verificado en v0.4.0; `copiar_a_3d` y
  `crear_layout` quedaron verificados en vivo con v0.4.1 el 2026-10-15
  (el export del layout es lo unico que espera el build).
