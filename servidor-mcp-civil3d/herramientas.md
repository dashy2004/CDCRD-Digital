# Herramientas del servidor MCP de Civil 3D

81 herramientas en la entrega 0.5.21. Los apartados describen los módulos
incorporados en cada etapa; consultar el catálogo MCP para las firmas vigentes.
Las de escritura exigen `confirmar=True`; el servidor pide entonces el token de
aprobacion ligado a esos parametros exactos.

## Estado y descubrimiento

| Herramienta | Parametros | Que devuelve |
|---|---|---|
| `estado_puente` | â€” | puerto, version del puente, si la escritura esta habilitada, ruta del log |
| `info_dibujo` | â€” | ruta del dwg, unidades (`INSUNITS`, `LUNITS`, `MEASUREMENT`), version, `civil3d: true/false` |
| `listar_colecciones` | â€” | miembros reales del `CivilDocument` con conteo, y los alias en espanol |
| `descubrir_tipos` | `coleccion`, `limite_tipos` | conteo de objetos por tipo .NET y clase RX |

`info_dibujo` con `civil3d: false` significa dibujo en AutoCAD puro o API no cargada:
ninguna coleccion de Civil 3D va a responder.

## Lectura

| Herramienta | Parametros | Notas |
|---|---|---|
| `consultar_objetos` | `coleccion`, `tipo`, `capa`, `props`, `handles`, `limite`, `salto` | `props='*'` trae todas las propiedades simples; una propiedad inexistente vuelve en `null` sin romper la consulta |
| `agregar_objetos` | `prop`, `op` (`conteo\|suma\|min\|max\|promedio`), `coleccion`, `tipo` | reporta cuantos objetos tenian valor y cuantos no |
| `inspeccionar_objeto` | `handle`, `ruta`, `valores` | propiedades (lectura/escritura) y metodos con firma, leidos del ensamblado instalado; con `ruta` describe un objeto anidado y con `valores=True` trae el valor actual de cada propiedad |
| `leer_ruta` | `ruta`, `handle`, `profundidad` | lee el valor al final de una ruta de propiedades anidadas; `profundidad` 1-3 expande lo que de otro modo sale como `{tipo, texto}` |
| `invocar_metodo` | `metodo`, `handle`, `args`, `ruta`, `profundidad`, `confirmar` | `Get*`, `Find*`, `Sample*`, `Station*`, `PointLocation`, `ElevationAt`, `Compute*`, `Is*`, `Has*` corren directo; el resto es escritura. Con `ruta` el metodo se invoca sobre el objeto anidado. Parametros `ref`/`out` (`PointLocation(est, 0, null, null)`): el resultado es `{retorno, salidas}` con los valores de salida por nombre (requiere el build del 2026-10-11) |
| `capas` | `nombre` | capas con su estado: apagada, congelada, bloqueada, trazable, color |

### Rutas a objetos anidados

Muchas cosas de Civil 3D no son `DBObject` con handle propio: el analisis de una
superficie, sus propiedades generales, los rangos de elevacion. Se llega a ellas
con `ruta`, una cadena de tramos separados por punto. Cada tramo es una propiedad
o un metodo sin argumentos, con indices opcionales:

```
Analysis
Analysis.ElevationRanges[2].MaximumElevation
GetGeneralProperties()
```

Si un tramo devuelve un `ObjectId` y la ruta sigue, el puente lo abre en la misma
transaccion. Tras un indice ya no se puede escribir en esa posicion, y escribir en
un tipo por valor (struct) se rechaza porque no afectaria al dibujo.

Flujo tipico: `inspeccionar_objeto(handle, ruta='Analysis')` para ver que metodos
existen en esta version, despues `leer_ruta` o `invocar_metodo(..., ruta='Analysis')`.

## Escritura

| Herramienta | Parametros | Notas |
|---|---|---|
| `actualizar_objeto` | `handle`, `cambios` (JSON), `ruta`, `confirmar` | devuelve valor antes/despues por propiedad y el motivo de cada fallo |
| `fijar_capas` | `nombres`, `apagada`, `congelada`, `bloqueada`, `confirmar` | enciende/apaga, congela/descongela y bloquea capas; hace `Regen` al terminar |
| `guardar_dibujo` | `ruta`, `confirmar` | `Database.SaveAs`; sin `ruta` guarda sobre el archivo actual |
| `ejecutar_comando` | `linea`, `confirmar` | requiere `CDCRD_C3D_PERMITIR_COMANDOS=1`; **asincrono**; inutil con dialogos modales |

## Vista

| Herramienta | Parametros | Notas |
|---|---|---|
| `seleccionar` | `handles`, `coleccion` | deja la seleccion implicita en Civil 3D |
| `zoom` | `handles`, `coleccion`, `extension`, `margen` | encuadra por API (`ViewTableRecord`), no por comando |

## Atajos

| Herramienta | Parametros |
|---|---|
| `listar` | `area`: `alineamientos`, `superficies`, `corredores`, `redes_gravedad`, `redes_presion`, `puntos`, `grupos_view_frame`, `vistas_perfil` |

En Civil 3D 2027, corredores, ensamblajes, subensamblajes, puntos COGO y grupos de
puntos viven en propiedades de coleccion (`CorridorCollection`, `AssemblyCollection`,
`SubassemblyCollection`, `CogoPoints`, `PointGroups`), no en metodos `GetXxxIds`. Los
alias resuelven ambas formas; `listar_colecciones` dice cual existe en la instalacion.

## Recetas

**Longitud total de alineamientos del proyecto**

```
agregar_objetos(coleccion='alineamientos', prop='Length', op='suma')
```

**Estaciones inicial y final de cada eje**

```
consultar_objetos(coleccion='alineamientos',
                  props='Name,Length,StartingStation,EndingStation')
```

**Cota de terreno en un punto (superficie)**

```
listar(area='superficies')                       -> handle de la superficie
inspeccionar_objeto(handle='1A2B')               -> confirma la firma real
invocar_metodo(handle='1A2B', metodo='FindElevationAtXY', args='405123.5;2048771.0')
```

**Estructuras de una red por gravedad**

```
listar(area='redes_gravedad')                    -> handle de la red
inspeccionar_objeto(handle='...')                -> metodos GetPipeIds / GetStructureIds
invocar_metodo(handle='...', metodo='GetPipeIds')
consultar_objetos(handles='<los handles devueltos>', props='*')
```

**Renombrar un alineamiento (escritura)**

```
actualizar_objeto(handle='7F3C', cambios='{"Name":"EJE-PRINCIPAL"}')          -> pide confirmacion
actualizar_objeto(handle='7F3C', cambios='{"Name":"EJE-PRINCIPAL"}', confirmar=True)
```

## Codigos de error del puente

| Codigo | Significado | Que hacer |
|---|---|---|
| `sin_puente` | nadie escucha en el puerto | abrir Civil 3D 2027; `CDCRDMCP` si no autoarranco |
| `-32000` | Civil 3D no respondio en 55 s | hay un comando, dialogo modal o modo edicion abierto: cerrarlo, no reintentar en bucle |
| `-32001` | no hay dibujo o no hay `CivilDocument` | abrir un dwg de Civil 3D |
| `-32002` | token de aprobacion invalido | repetir con `confirmar=True` (el token se liga a los parametros exactos) |
| `-32003` | operacion prohibida por configuracion | `CDCRD_C3D_SOLO_LECTURA` o comandos deshabilitados |
| `-32602` | parametros o firma que no encajan | `inspeccionar_objeto` para ver la firma real |

## Scripts sobre el puente

Desde 0.5.17: `crear_ensamblaje_cunetas_bermas` crea carriles con cuatro capas, bermas sin capas y cunetas trapezoidales a ambos lados. Pendientes de berma m/m y caras de cuneta H/V; requiere `confirmar=True`, admite `simular=True`. Se conecta con `crear_corredor_calzada` y `crear_secciones_corredor`. [ParÃ¡metros, lÃ­mites, capturas y pruebas](docs/CUNETAS-BERMAS-0517.md).

| Script | Que hace |
|---|---|
| `src/perfil.py` | cota de superficie por progresiva sobre un alineamiento y comparacion contra un perfil nativo; CSV/JSON; `tests/test_perfil.py` sin CAD |
| `pruebas/arnes_invocar/correr.py` | compila `Invocar`/`Coerce` de Handlers.cs con .NET 10 y prueba ref/out sin Civil 3D |

## Grupos de puntos y superficies (v0.5.3 a 0.5.5)

| Herramienta MCP | Metodo del puente | Que hace |
| --- | --- | --- |
| `grupos_de_puntos` | `puntos.grupos` | Lista los grupos con su conteo y su consulta vigente. |
| `crear_grupo_puntos` | `puntos.grupo_crear` | Crea o reescribe un grupo con membresia por consulta (StandardPointGroupQuery: IncludeRawDescriptions, IncludeNumbers, IncludeNames y sus excluir). Opcionalmente sobrescribe el estilo de punto y el de etiqueta. |
| `crear_superficie` | `superficie.crear` | TinSurface.Create con estilo y capa; idempotente por nombre. |
| `superficie_agregar_grupos` | `superficie.grupos` | Agrega grupos de puntos a la definicion de la superficie y reconstruye; devuelve las estadisticas de Civil 3D. |

Las herramientas MCP nuevas solo aparecen cuando el cliente reinicia el servidor
Python. Mientras tanto, lo mismo se hace con los metodos genericos, porque desde
v0.5.4 `Coerce` construye argumentos que antes eran inexpresables:

- un **handle hexadecimal** se convierte a `ObjectId`, asi que
  `invocar_metodo(handle=<superficie>, ruta='PointGroupsDefinition', metodo='AddPointGroup', args=['<handle del grupo>'])`
  y `actualizar_objeto(<superficie>, {'StyleId': '<handle del estilo>'})` funcionan;
- un **objeto JSON pasado como texto** se convierte en una instancia con sus
  propiedades fijadas, eligiendo la unica subclase concreta del parametro o la que
  diga la clave `$tipo`:
  `invocar_metodo(handle=<grupo>, metodo='SetQuery', args=['{"$tipo":"StandardPointGroupQuery","IncludeRawDescriptions":"ACERA*"}'])`;
- una **lista** se convierte en Point3dCollection, ObjectIdCollection o cualquier
  coleccion con constructor vacio y `Add` de un argumento.

Ojo: `JsonToClr` del puente revienta con un objeto JSON crudo dentro de `args`
("The node must be of type 'JsonValue'") hasta v0.5.5 inclusive; por eso la query
va como texto. Corregido en fuente despues de 0.5.5.

## Múltiples baselines y regiones (0.5.20)

- `crear_corredor_multibaseline`: corredor nuevo, perfiles/ejes independientes y lista ordenada de regiones; cada una define ensamblaje, intervalo, frecuencia, extras y target TIN. Simulación por defecto, confirmación requerida.
- `leer_corredor_multibaseline`: verifica contrato Xrecord propio, muestras y Top; marca el ensamblaje devuelto en límites compartidos.
- `crear_secciones_multibaseline`: baseline explícita, normales y estaciones verificadas, H=V; rechaza huecos/límites compartidos.

Requiere módulo `Cdcrd.Corredores.V4`0.1.3 en la instancia existente. Catálogo total78. [Contrato, ejemplos y evidencia](docs/MULTIBASELINE-0520.md).

## Targets de ancho y cota (0.5.21)

- `listar_targets_corredor(dibujo, pid, corredor)`: slots por baseline/región/subensamblaje, tipo y referencias.
- `crear_corredor_con_targets(dibujo, pid, corredor_origen, nombre, asignaciones, simular=True, confirmar=False)`: nuevo corredor y Top; origen propio multibaseline de solo lectura. Ancho con alineamiento lateral; cota con perfil de ese eje, o del eje baseline si no hay target de ancho.
- `leer_targets_ancho_cota(dibujo, pid, corredor)`: contrato propio y verificación de ETW/Top. Usar este lector para el nuevo corredor, cuyo target no vacío rechaza el lector multibaseline anterior.

Requiere `Cdcrd.Targets.V2` 0.1.1. Un target por slot, metros, sin ecuaciones, objetos locales y carriles de corona. Simulación por defecto y confirmación requerida. Tras timeout consultar recibo; no reenviar. [Contrato, reproducción y evidencia](docs/TARGETS-0521.md).
