# Que falta / limitaciones conocidas

## Actualizacion local 0.5.6 — 2026-10-20

Corregidos y probados: lectura de campos ValueTuple en Invocar/PropGm,
limpieza de grupos vacios cuyo nombre empieza por `GM - ` y cancelacion
atomica de solicitudes que vencen antes de comenzar. Las operaciones ya
iniciadas NO se anuncian canceladas: el error incluye request_id y resultado
incierto; `diag.cola` / `estado_cola` permite consultar su finalizacion.
El historial conserva los ultimos 64 despachos, sin guardar parametros ni
resultados. Un despacho cmd.run terminado sigue significando comando encolado,
no CommandEnded. No reintentar automaticamente ante timeout de transporte.

Validacion: 110 pruebas Python, 24 comprobaciones .NET + 100 carreras y humo
0.5.6 en Civil 3D 2027 sobre DWG sintetico. La prueba TCP de escritura vencida
no borro el grupo al volver Idle. El borrado posterior con aplicacion explicita
conservo grupos ajenos, GM vivos y mixtos. El contrato ValueTuple se probo con
Invocar/PropGm/InvocarGm del DLL cargado y un productor sintetico; no se ejecuto
el flujo completo del GM sobre sondeos de proyecto.

Instrucciones reproducibles: [pruebas 0.5.6](PRUEBAS-056.md).
Codigo y evidencia permanecen locales; no se publico esta correccion.
Los pendientes historicos que figuran debajo deben leerse con esta actualizacion.


Estado al 2026-10-16 (puente **0.5.2** compilado, instalado y verificado en
vivo, build `2069be350f76`). Complementa `PENDIENTES.md` (backlog por
prioridad).

## Limites del puente

- **Un reinicio por build.** Cada compilacion del DLL exige cerrar y reabrir
  Civil 3D; `instalar.ps1` puede instalarse con Civil 3D abierto y el
  reinicio toma el build nuevo. Si `estado_puente` no cambia de `build`,
  quedo un `acad.exe` vivo.
- **El servidor MCP Python no se recarga solo.** Cambios en `src/*.py` se
  prueban por script TCP (`src/puente_cliente.py`), no por las herramientas
  `mcp__...` de la app, hasta reiniciar la app de Claude.
- **Dialogos modales congelan las peticiones** (vencen a 55 s): el modal
  bloquea la ventana principal y la bomba de `Application.Idle` no dispara.
  Desde 0.5.2 `eventos_dialogo` se sirve **en el hilo del socket** (solo
  user32) y responde igual, con el titulo y los textos de los dialogos
  `#32770`; `leer_log_puente` sigue siendo el otro diagnostico que no
  depende del hilo principal. `ejecutar_comando` es asincrono y no sirve
  para comandos que abren dialogos.
- **SECURELOAD con el `.lsp` temporal.** `ejecutar_lisp` escribe un `.lsp` en
  `%LOCALAPPDATA%\Temp\cdcrd_lisp` y lo carga con `(load ...)`. Si esa
  carpeta no esta en TRUSTEDPATHS, AutoCAD abre
  *"Security - Unsigned Executable File"* y cuelga el puente hasta que
  alguien pulse un boton. Salidas: agregar la carpeta a TRUSTEDPATHS, o
  mandar el codigo corto directo por `ejecutar_comando` (ojo: ~256
  caracteres por linea y se rompen los acentos).
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

- El flujo del GM tiene **dos** fallas documentadas en
  `BUG-GM-CreateStickLogProfile.md`: (1) `NullReferenceException` en el
  borrado previo (`DeleteStickLogProfile` -> `StickLogDiagram.Delete` ->
  `ProfileStickLog.Delete` -> `ObjectId.GetObject`) cuando el dibujo tiene
  sticklogs residuales de una corrida interrumpida, y (2) un **MessageBox
  modal** dentro de `GeologyHatchingService.AssignHatchStylesToBoreholeStrata`
  cuando ningun estrato casa con `GeologyHatchStyle.config`, que cuelga
  cualquier llamada por API. Mitigacion: limpiar el estado residual y dejar
  `hatch_geologia=False`. Con eso `CreateStickLogProfile` **pasa** (verificado
  2026-10-16, `Corte B-B'`, 5 sondeos, 230 ms).
- El paso 2 del perfil de sondeos (diagrama de sticklogs) sigue fallando por
  un defecto **del puente**: `CreateStickLogDiagram` devuelve un `ValueTuple`
  y la reflexion del puente busca `Item1` como propiedad en vez de campo.
- El flujo nativo (perfil estratigrafico 3.2 + isometricos 3.4) es el camino
  oficial del proyecto y no depende del GM.
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

## Verificado en vivo

- v0.4.0/0.4.1: `isometrico_sondeos_3d`, `copiar_a_3d`, `crear_layout`.
- v0.5.1 (2026-10-15): `exportar_vista(layout=...)` con el fix de
  `SetPlotCentered` (lamina A3, sin workaround), `eventos_dialogo`,
  `gm_diagnosticar`, `gm_reparar` (simulacion), suite de humo del perfil
  13/13, `aplanar_dibujo` (126.186 entidades).
- v0.5.2 (2026-10-16): `eventos_dialogo` desde el hilo del socket (detecto el
  modal de SECURELOAD con sus textos), `gm_diagnosticar` con conteo de
  grupos, `gm_reparar` con `borrar_grupos_muertos` (simulacion) y
  `gm_crear_perfil_sondeos` con `solo_perfil=True` -> OK.

## Pendiente de verificar en vivo (proximo build)

- `gm_reparar borrar_grupos_muertos` con un caso real (ajustar el criterio a
  grupos **vacios** con prefijo `GM - `; la prueba positiva de
  `pruebas/humo_v052.py` quedo sin correr).
- Paso 2 del perfil de sondeos (`CreateStickLogDiagram`) tras corregir la
  lectura de campos de `ValueTuple`.
- `aplanar_dibujo` y la suite de humo del perfil contra el DLL 0.5.2.
