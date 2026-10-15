# Geotechnical Modeler (Etapa 4) — herramientas gm_*

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
Surface`, cuya ausencia es la causa directa del NRE de
`CreateStickLogProfile`; ver `BUG-GM-CreateStickLogProfile.md`), superficies
con sufijo `.1`, los seis estilos de nombre fijo que GM exige, hatches
huerfanos de la capa `GM-PROF-STICKLOG-2D` y el `ProjectId`. `problemas`
resume lo que falta; `ok=true` significa que el flujo del GM tiene todo.

## gm_reparar

| Parametro | Notas |
|---|---|
| `aplicar` | `False` = simulacion (lista las acciones sin tocar nada) |
| `renombrar_sufijo_1` | renombra `GM - ... .1` al nombre base cuando el base no existe |
| `borrar_hatches_huerfanos` | borra los hatch de `GM-PROF-STICKLOG-2D` |
| `confirmar` | escritura |

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
| `solo_perfil` | `True` se detiene tras `CreateStickLogProfile` (repro del bug) |

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
