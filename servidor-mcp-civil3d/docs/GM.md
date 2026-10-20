# Geotechnical Modeler (Etapa 4) — herramientas gm_*

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


Puente hacia el plugin oficial C3D-GeoTechModeler-2027 **dentro del mismo
proceso** de Civil 3D: `puente/HandlersGm.cs` resuelve los servicios del GM
por reflexion (contenedor Castle Windsor en `Aecc.Gtm.Domain.IoC`) y los
llama con el mismo patron de transaccion que los presenters del plugin.
Requiere puente >= 0.5.0 y el bundle del GM cargado. Datos geotecnicos
hipoteticos/preliminares.

Requisito comun: un proyecto GM activo (settings guardados en el dibujo;
`gm_diagnosticar` reporta el `project_id`). La base de sondeos es la del GM
(`AGMConnectionString` del Application.config), no los CSV del perfil nativo.

## gm_diagnosticar

Sin parametros. Reporta: ensamblados `Aecc.Gtm.*` cargados, contenedor IoC
inicializado, existencia de `%PROGRAMDATA%\Autodesk\C3D-GeoTechModeler-2027\
Application.config`, superficies del dibujo (en particular `GM - Top
Surface`), superficies con sufijo `.1`, los seis estilos de nombre fijo que
GM exige, hatches huerfanos de la capa `GM-PROF-STICKLOG-2D`, grupos de
`ACAD_GROUP` con miembros borrados (0.5.2) y el `ProjectId`. `problemas`
resume lo que falta; `ok=true` significa que el flujo del GM tiene todo.

El estado residual de corridas anteriores (hatches huerfanos y grupos de
sticklogs viejos) es la causa **verificada** del NRE del GM, que ocurre en el
borrado previo (`DeleteStickLogProfile`), no en la creacion; la ausencia de
`GM - Top Surface` es un segundo camino al mismo sintoma. Ver
`BUG-GM-CreateStickLogProfile.md`.

## gm_reparar

| Parametro | Notas |
|---|---|
| `aplicar` | `False` = simulacion (lista las acciones sin tocar nada) |
| `renombrar_sufijo_1` | renombra `GM - ... .1` al nombre base cuando el base no existe |
| `borrar_hatches_huerfanos` | borra los hatch de `GM-PROF-STICKLOG-2D` |
| `borrar_grupos_muertos` | 0.5.2: borra grupos de `ACAD_GROUP` con miembros borrados (Erase, con `dictremove` de respaldo). Un grupo con miembros vivos fuera de capas `GM-*` se reporta y no se toca |
| `confirmar` | escritura |

Limitacion medida (2026-10-16): al borrar una entidad AutoCAD la quita de
sus grupos, asi que el grupo residual queda **vacio**, no con referencias
nulas. El criterio de `borrar_grupos_muertos` por eso aun no atrapa el caso
real; el ajuste pendiente es detectar grupos **vacios** con prefijo `GM - `
(mas BlockTableRecords sin referencias), como hace
`ProfileService.DeleteOrphanedStickLogObjects` del propio GM.

## gm_crear_perfil_sondeos

Reproduce el panel *Subsurface Profiles* sin UI: borra los perfiles del
alineamiento (comportamiento del propio GM), crea o reusa la vista, llama
`ProfileService.CreateStickLogProfile` y, salvo `solo_perfil=True`, dibuja el
diagrama de sticklogs (`CreateStickLogDiagram` + `Render` + draw order).

| Parametro | Notas |
|---|---|
| `alineamiento` | nombre exacto |
| `vista` | nombre de la vista de perfil (defecto `<alineamiento> - Sondeos`) |
| `origen` | `'[x,y]'`, obligatorio si la vista no existe |
| `exageracion` | vertical, 4.0 por defecto (el GM la escribe en el estilo `GM - Standard`) |
| `estacion_inicio/fin` | defecto: todo el alineamiento |
| `superficie_top` | defecto `GM - Top Surface` |
| `solo_perfil` | `True` se detiene tras `CreateStickLogProfile` |
| `hatch_geologia` | 0.5.2, **False** por defecto: no arma `GeologyHatchStyleConfiguration`. Con `True` el GM abre un MessageBox modal si ningun estrato casa con el config (`ProfileGeologyField` viene vacio) y cuelga el puente. Ver Falla 2 del reporte del bug |

Verificado en vivo 2026-10-16 (build 2069be350f76), tras limpiar el estado
residual del dibujo: `Corte B-B'` con `solo_perfil=True` devuelve
`CreateStickLogProfile OK` en 230 ms, 5 sondeos, y el `DebugLog` del GM llega
hasta `End: ProfileService.CreateStickLogProfile`.

El paso 2 (diagrama, `solo_perfil=False`) falla todavia con
`ValueTuple\`2 no tiene la propiedad Item1`: `CreateStickLogDiagram` devuelve
una tupla de valor y `Item1`/`Item2` son **campos**, no propiedades, asi que
el helper de reflexion del puente no los ve. Corregir en el proximo build
(leer campos antes que propiedades).

Si `CreateStickLogProfile` falla, `perfil_error` trae la excepcion completa
(tipo, mensaje, metodo y pila): es la evidencia del reporte del bug. Con
`GM_DebugLogging_On` (comando del GM, sin dialogo) el log del GM
(`DebugLog_*.txt` en el `DebugLogFilePath` del Application.config) registra
el paso exacto donde murio.

OJO: igual que el boton del GM, **borra todos los perfiles del
alineamiento** antes de crear los suyos. No usar sobre el alineamiento del
perfil estratigrafico nativo sin regenerarlo despues.

## gm_construir_superficies

`StratumService.BuildStratumSurfaces`. `superficie_fondo=True` crea ademas la
superficie del fondo de sondeos. Equivale al boton *Build Surfaces*.

## gm_3d_boreholes

`Borehole3DService.Create3DBoreholes` con los sondeos del proyecto activo:
`altura_rotulo`, `diametro`, `exageracion`, `campo_geologia` (`GeologyCode`).

## gm_stratum_display

Sin parametros: devuelve los settings de visibilidad/exageracion de las
superficies GM. Con `usar_exageracion` y/o `exageracion` los aplica al
`tipo_superficie` (`FullStratum` o `Lens`); requiere `confirmar=True`.

## Errores comunes

- "ensamblado del GM no cargado": el bundle del GM no esta instalado o no
  cargo; revisar `%APPDATA%/../Program Files` ApplicationPlugins.
- "el contenedor IoC del GM no esta inicializado": ningun comando del GM ha
  corrido; ejecutar p. ej. `GM_DebugLogging_On` por `ejecutar_comando`.
- "el dibujo no tiene settings del GM guardados": no hay proyecto GM activo
  en ese dwg; abrir *Manage Data* del GM una vez (UI) o usar otro dwg.
