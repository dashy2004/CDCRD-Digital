# Cuencas de aportación: crear, parámetros hidrológicos y estructura de descarga — 0.5.26

Tres operaciones sobre las cuencas (`Catchment`, ensamblado `AeccDbMgd`) de Civil 3D 2027: listarlas con sus parámetros, crear una desde un contorno y una superficie, y escribir parámetros hidrológicos o asociarla a una estructura de red de gravedad. Módulo opcional `Cdcrd.Cuencas.V1` **0.2.0**, comando `CDCRDCUENCASV1`, instalado con `instalar-cuencas.ps1`. [fable], 2026-11-21.

El módulo no calcula hidrología y **no supone ningún coeficiente**: coeficiente de escorrentía, tc, número de curva y trayectoria de flujo entran como parámetros. Lo que no se indica queda con el valor que asignó Civil, y la respuesta lo dice.

## Uso

```python
listar_cuencas(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO)
crear_cuenca(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, nombre="C-01", grupo="PLUVIAL", superficie="TERRENO",
    polilinea="71B3", coeficiente_escorrentia=0.85, trayectoria="[[190,110],[120,70],[60,30],[10,5]]", simular=True, confirmar=True)
actualizar_cuenca(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, cuenca="C-01", tc_min=12,
    estructura="RED PLUVIAL/Structure - (3)", simular=False, confirmar=True)
```

## Contrato

**Transporte.** Solicitud inmutable con SHA-256, PID y documento exactos, vencimiento de 3 minutos y recibo ligado; solicitudes y recibos en `%LOCALAPPDATA%\CdcrdCivil3dBridge\cuencas`, no junto al dibujo. Escrituras con `confirmar=True`, simulación por defecto (`simular=True` ejecuta, verifica y aborta la transacción). Dibujo en metros. El servidor comprueba antes la versión del módulo cargado y se niega con una anterior a 0.2.0.

**Listar.** Por cuenca: `nombre`, `grupo`, `area_m2`, `area_ha`, `perimetro_m`, `superficie`, `coeficiente_escorrentia`, `metodo_escorrentia`, `tc_min`, `tc_h`, `metodo_tc`, `longitud_flujo_m`, `pendiente_media`, `punto_descarga`, `punto_mas_distante`, `numero_curva`, `area_impermeable`, `red`, `estructura`, `estructura_handle` y `segmentos_flujo` (tipo TR-55, longitud, pendiente, Manning y `tiempo_min` de cada segmento). Una propiedad que la API no entrega para esa cuenca vuelve `null`.

**Crear.** `nombre` (único en el dibujo), `grupo` (se crea si no existe), `superficie` y el contorno: `contorno` `[[x, y], ...]` o `polilinea`, handle de una polilínea ligera o 3D **cerrada** y sin arcos (de la 3D solo la planta; la polilínea no se consume). Estilo: el indicado en `estilo` o el primero del dibujo. Después aplica los parámetros dados y verifica:

1. el área de la cuenca (`Area2d`) coincide con la del contorno calculada aparte (tolerancia 0,01 m² o 1 ppm);
2. cada parámetro pedido, releído, es el pedido.

Si algo no coincide es error y no se guarda nada. La respuesta trae `parametros_pedidos` y `parametros_de_civil` (los que quedaron con el valor por defecto de Civil; el coeficiente de escorrentía, por ejemplo, nace en 0,5).

**Actualizar.** `cuenca` (nombre o handle) y al menos un parámetro; cambia solo lo indicado y devuelve `antes` y `despues`.

**Parámetros que se escriben.**

| Parámetro | Efecto | Nota |
|---|---|---|
| `coeficiente_escorrentia` | `RunoffCoefficient` | 0 a 1 |
| `tc_min` | `TimeOfConcentration`, método de usuario | minutos; ver unidades |
| `metodo_tc` | `TimeOfConcentrationCalculationMethod` | `TR55`, `usuario`, `Kirpich`, `FAA`; `tc_min` solo con `usuario` |
| `trayectoria` | `SetFlowPath` | `[[x, y] o [x, y, z], ...]` del punto más distante a la descarga; sin `z` se toma de la superficie |
| `estructura` | `ReferenceDischargeObjectId` | handle, nombre único o `red/estructura` |
| `numero_curva` | `CompositeCurveNumber` | Civil solo lo admite con método de escorrentía SCS, SBUH o SWMM con infiltración por número de curva; con otro método devuelve su propio error |
| `superficie` | `ReferenceSurfaceId` | solo en actualizar |

Área, perímetro y longitud de flujo no se escriben: son resultados de la geometría (contorno y trayectoria).

## Lo que expone la API instalada

Comprobado por reflexión de `AeccDbMgd.dll` y por el compilador (atributos de obsolescencia):

- `Catchment.Create(nombre, estiloId, grupoId, superficieId, Point3dCollection)` y `CatchmentGroupCollection.GetCatchmentGroups(db)` con `Add`, `Contains` e indexador por nombre.
- `ReferencePipeNetworkId` es de **solo lectura** en esta versión (`set` marcado como error): la asociación se hace con `ReferenceDischargeObjectId` y Civil deriva la red. `ReferencePipeNetworkStructureId` y `...Name` están obsoletos a favor de `ReferenceDischargeObjectId` / `...Name`.
- `CurveNumber` está obsoleto a favor de `CompositeCurveNumber`; `ManningsCoefficient` de la cuenca está retirado (el Manning va por segmento de flujo) y `HydrologicallyMostDistantLength` se sustituye por `FlowPathLength`.
- `SetFlowPath(Point3dCollection)` está marcado obsoleto con el texto «Use FlowPath.SetPath», pero `FlowPath` no define `SetPath` en el ensamblado instalado: esa sobrecarga es el único modo de fijar la trayectoria y es la que se usa.
- El nombre del grupo (`CatchmentGroup.Name`) no figura en los metadatos de referencia y sí existe en ejecución; se lee por reflexión.

**Unidades de tiempo.** La API guarda los tiempos de la cuenca en **horas**, sea cual sea la unidad de tiempo de los ajustes del dibujo. Evidencia: con una trayectoria de un solo segmento de flujo concentrado superficial de 208,64 m y pendiente 0,0298, TR-55 da 0,849 m/s y 4,09 min; `TimeOfConcentration` devolvió 0,0682 con los ajustes en minutos. El módulo recibe y devuelve minutos (`tc_min`, `tiempo_min`) y conserva `tc_h` como lectura directa.

## Resultados en un dibujo sintético

Dibujo desechable creado de la plantilla métrica del producto: superficie TIN de 200 × 120 m con cuatro cotas de esquina y una red de gravedad de dos estructuras creada con el módulo de drenaje.

| Caso | Resultado |
|---|---|
| Listar sin cuencas | lista vacía, 0 grupos |
| Simular desde vértices, sin parámetros | área 6 600 m² = contorno; todos los parámetros en `parametros_de_civil`; tras abortar no queda cuenca ni grupo |
| Confirmar desde polilínea cerrada con coeficiente 0,85 y trayectoria | área 24 000 m², coeficiente releído 0,85, longitud de flujo 208,64 m, tc TR-55 4,09 min |
| Actualizar `tc_min=12` | `tc_h` 0,2, método de usuario; `antes` y `despues` en la respuesta |
| Asociar a una estructura por `red/estructura` (simulado) y por handle (confirmado) | `red` y `estructura` releídas; la simulación no dejó cambio |
| Estructura inexistente, nombre de cuenca repetido, `tc_min` con `metodo_tc=TR55` | rechazados |
| `numero_curva` con método de escorrentía racional | error de Civil, nada guardado |

Salida gráfica revisada en imagen (contorno, trayectoria hasta la estructura y redes).

Offline: 17 pruebas Python (`tests/test_cuencas.py`), compilación con 0 errores y 0 advertencias.

## Límites

- Contornos de tramos rectos; sin arcos ni islas. No delimita cuencas desde la superficie (análisis de gotas de agua): el contorno lo da el llamador.
- No borra ni renombra cuencas, no cambia de grupo, no crea etiquetas.
- No edita segmentos de flujo (tipo, Manning, superficie): con `metodo_tc=TR55` Civil calcula con sus valores por defecto de segmento, que son suyos y no un criterio de diseño. Para un tc de proyecto, calcularlo fuera y pasarlo en `tc_min`.
- No valida que la estructura esté dentro o cerca de la cuenca.

## Reproducción

Copia desechable cuyo nombre empiece por `CDCRD_QA`, abierta como documento activo.

```powershell
py pruebas/humo_cuencas.py --drawing <copia> --pid <PID> --etapa listar
py pruebas/humo_cuencas.py --drawing <copia> --pid <PID> --etapa crear --nombre C-01 --grupo QA --superficie <nombre> --polilinea <handle> --coeficiente 0.85 [--confirmar]
py pruebas/humo_cuencas.py --drawing <copia> --pid <PID> --etapa actualizar --cuenca C-01 --tc 12 --estructura <red/estructura> [--confirmar]
```
