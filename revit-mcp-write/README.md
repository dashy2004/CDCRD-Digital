# revit-mcp-write

Herramientas para automatizar Autodesk Revit 2027 desde un agente. Dos canales:

1. **Pushbuttons de pyRevit** que hacen el trabajo y escriben JSON a disco. **Es el canal
   recomendado.** El agente lee el JSON del disco y decide el paso siguiente.
2. **Servidor MCP sobre [pyRevit Routes](https://pyrevitlabs.notion.site/)** para consulta
   interactiva. **Deprecado**: ver abajo.

Escrito para trabajo estructural real (columnas de hormigón y su despiece de acero), pero
la mecánica es genérica.

## ⚠️ Routes deprecado — usar pushbuttons

Tras ~20 arranques de Revit en dos días de trabajo, **el servidor HTTP dentro del proceso de
Revit resultó ser el factor común de unas 5 caídas duras**. Los scripts de pushbutton
completaron 6 de 6 corridas, incluida una que creó 192 columnas con 1876 sets de acero; las
caídas llegaban *después* de completar, con retardo — la firma de un hilo de fondo muriendo,
no del script en curso.

```
pyrevit configs routes disable
```

Los pushbuttons no dependen de Routes. El agente pierde consulta en vivo y la recupera
leyendo los JSON que los botones dejan en `_log/`. Detalle en el histórico de errores del
proyecto (E-049, E-050).

**Cuándo conviene cada canal:**

| | Endpoint (Routes) | Pushbutton |
|---|---|---|
| Hilo | Servidor, fuera del contexto de API | UI de Revit, contexto válido |
| Iterar | Exige reiniciar Revit | Relee el código en cada click |
| Salida | HTTP | Archivo JSON en disco |
| Volumen | Respuesta grande = respuesta cara | Sin límite práctico |
| Con el servidor caído | No sirve | Sigue funcionando |
| Estabilidad medida | ~5 caídas | 6/6 corridas OK |

## Los pushbuttons

| Botón | Qué hace | Escribe |
|---|---|---|
| `Estado` | Puerto real y endpoints registrados, desde dentro del proceso | — |
| `Inventario` | Columnas con coordenadas, niveles, offsets, bbox y acero hospedado | `inventario.json` |
| `Constraints` | Estado de constraints de cada set de acero | `constraints.json` |
| `Reemplazo` | Copia columnas maestras con su acero a la posición de otras | `reemplazo.json` |
| `Borrado` | Borra por identidad de familia/tipo, con confirmación y conteos | `borrado.json` |
| `Faltantes` | Repone columnas desde un plan en JSON | `faltantes_resultado.json` |

**Patrón común a todos** (ver `Constraints` como referencia):

- Fases numeradas, con la última alcanzada guardada en el JSON (`phase_reached`)
- Una unidad de prueba antes del lote: si algo mata el proceso, se lleva una y no todas
- Log incremental con `flush` + `os.fsync` **antes** de cada llamada riesgosa, no después
- El JSON se escribe **siempre**, completo o no
- Los que escriben marcan su obra (`Comments`), así son idempotentes y pueden limpiarla
- Verificación final **releyendo el modelo**, nunca contando lo que se pidió

## Acero de vigas (6-Vigas.panel) — hallazgos 2026-08-21

Auditoría posterior a dos corridas "exitosas" (ArmarV2: 33 vigas/297 sets;
GenerarAceroVigas: 228 vigas/2052 sets, ambas con `verificacion.coincide:
true` en su JSON) encontró que **ninguno de esos elementos seguía en el
modelo** al re-consultar. Causa: el `.rvt` no se guardó después de correr
los scripts y Revit se cerró/crasheó antes del siguiente guardado — el
JSON de un pushbutton describe la sesión en memoria, no lo que quedó en
disco. Se agregó `GuardarModelo.pushbutton` (solo `doc.Save()`, sin
SaveAs) y la instrucción es correrlo después de **cada** botón de
escritura, no al final del día — no hay forma de saber de antemano cuál
corrida precede a la próxima caída.

Bugs de código encontrados y corregidos en `ArmarV2` y `GenerarAceroVigas`:

- **`"cant"` nunca se usaba**: los diccionarios de armado traían un conteo
  de barras (2 arriba, 3-4 abajo, etc.) que solo se leía para el catálogo
  de diámetros, nunca para crear más de una barra por posición. Cada viga
  quedaba con 1 barra por capa en vez de las 2-4 reales. Se agregó
  `crear_grupo_recta()` + `offsets_y()`: reparte "cant" barras paralelas a
  lo ancho útil de la viga.
- **"En C/Lado" reinterpretado**: el JSON de referencia trae
  `acero_inferior_adicional_apoyo: "2Ø1/2\" En C/Lado"` como valor casi
  constante en los 10 pórticos digitalizados (a diferencia del adicional
  superior de apoyo, que sí varía mucho por eje/nivel: Adic.2Ø1" a
  Adic.6Ø1"). Un valor tan uniforme no encaja con refuerzo local de apoyo;
  se remodeló como acero de piel continuo (`LATERAL_PIEL`/`lateral`): una
  barra de 1/2" en cada cara, a todo lo largo, a media altura real
  (bounding box), no dos tramos cortos cerca de cada apoyo.
- **Verificación de forma (Shape Name)**: se pidió confirmar que estribos
  usan la forma "T1" y las barras rectas "00"/"0". La firma real de
  `CreateFromCurves` en esta instalación no expone un parámetro de forma
  explícito (depende de `useExistingShapeIfPossible=True` reutilizando una
  forma existente si la geometría calza), así que no se puede forzar desde
  fuera sin una API distinta. Se agregó verificación releída
  (`LookupParameter("Shape Name")`, misma convención que usa
  `ColorAcero.pushbutton`) volcada en `result["verificacion_formas"]` de
  cada JSON de salida — dato de auditoría, no garantía.

Pendiente real: correr ambos botones de nuevo con el fix, **guardar**, y
releer `verificacion_formas` del JSON de salida para confirmar contra el
modelo si "T1"/"00" efectivamente se están reutilizando o si Revit está
creando formas nuevas con otro nombre.

## Estado de verificación

Este proyecto distingue **"el código existe"** de **"corrió contra un modelo real y devolvió
datos contrastados"**. La tabla dice lo segundo.

| # | Herramienta | Verbo | Estado |
|---|---|---|---|
| 1 | `revit_status` | GET | ✅ verificado |
| 2 | `revit_levels` | GET | ✅ verificado |
| 3 | `revit_columns` | GET | ✅ verificado |
| 4 | `revit_rebar` | GET | ✅ verificado |
| 5 | `revit_find` | POST | ✅ verificado |
| 6 | `revit_reflect` | POST | ✅ verificado |
| 7 | `revit_delete` | POST | ⚠️ **sin corridas reales** |
| 8 | `revit_copy` | POST | ✅ verificado |
| 9 | `revit_set_param` | POST | ✅ verificado |

**`revit_delete` no corrió nunca. No lo uses contra un modelo que te importe.**

### Evidencia de las dos escrituras verificadas

Piloto del 2026-08-13 sobre una copia de un modelo real (231 columnas, 65 sets de acero):

1. `revit_copy` de una columna **más sus 11 sets de acero en la misma llamada**, con traslación
   horizontal. Resultado releído: 76 sets, y los 11 nuevos con `host_id` de la **columna copiada**.
   El acero se re-hospeda solo cuando anfitrión y hospedados viajan juntos.
2. `revit_set_param` de `Top Offset = -2.78871 ft` sobre la copia, para bajar su altura de
   4,00 m a 3,15 m.

Relectura de los 11 sets, contra la predicción hecha **antes** de escribir:

| | Predicho | Real |
|---|---:|---:|
| Longitudinales (`Fixed Number`) | 10.1680 ft | **10.1680 ft** |
| Estribos (`Maximum Spacing`) | 32 barras | **32 barras** |

Los 11 sets se adaptaron, ninguno quedó fijo. El comportamiento se separa por layout rule:

- **`Fixed Number`** → cambia la **longitud** de cada barra, conserva la cantidad (9, 9, 2, 2).
- **`Maximum Spacing`** → conserva la longitud (es el perímetro del estribo, la sección no cambió)
  y recalcula la **cantidad**: 41 → 32, que es `ceil(3099/100)+1`.

Conclusión de ingeniería: con el acero amarrado por constraints a caras del anfitrión, **un juego
maestro por tipo de columna alcanza**; no hace falta uno por cada altura de entrepiso.

## Instalación

1. **Habilitar Routes** (viene apagado de fábrica) y **reiniciar Revit**:

   ```
   pyrevit configs routes enable
   pyrevit configs routes port 48884
   ```

   El servidor solo arranca al cargar el addin. Sin reinicio no levanta.

2. **Registrar la extensión**: copiar o enlazar `RevitWrite.extension` a una carpeta de
   extensiones de pyRevit.

3. **Registrar el MCP** en el cliente, apuntando a `src/server.py` con un Python 3.
   El servidor MCP habla HTTP con Revit; no necesita la API de Revit.

4. **Verificar**: botón `RevitWrite → Servidor → Estado`. Muestra el puerto real y los
   endpoints registrados, consultando desde dentro del proceso de Revit.

## Herramientas

### Consulta

| Herramienta | Devuelve |
|---|---|
| `revit_status()` | Documento abierto, ruta y conteos de niveles, columnas y acero |
| `revit_levels()` | Niveles con cota en pies y metros, de abajo hacia arriba |
| `revit_columns()` | Columnas estructurales: id, familia, tipo, Mark, nivel |
| `revit_rebar()` | Sets de acero: id, anfitrión, tipo de barra, forma, cantidad, longitud, layout rule |
| `revit_find(category, family, type_name, level)` | Instancias filtradas. Para armar conjuntos de ids sin adivinar |
| `revit_reflect(type_name, member)` | **Firma real** de un tipo de la API de *esta* instalación: métodos, estático o no, retorno y parámetros |

`revit_reflect` es la más valiosa para trabajo nuevo: convierte cada duda de firma en una
consulta en vez de un ciclo de prueba y error con reinicio. La API de Revit cambia nombres
entre versiones; escribir contra la API recordada es la causa de fallo más común.

### Escritura

| Herramienta | Hace |
|---|---|
| `revit_delete(ids)` | Borra por id, en transacción |
| `revit_copy(ids, dx, dy, dz)` | `ElementTransformUtils.CopyElements` con desplazamiento vectorial |
| `revit_set_param(name, ids, value)` | Fija un parámetro y **relee para verificar** |

Notas de uso:

- **`revit_copy` copia exactamente los ids que recibe.** Para que lo hospedado (acero, por
  ejemplo) viaje con su anfitrión, hay que pasar **anfitrión + hospedados en la misma llamada**.
- **`revit_copy` desplaza por vector, no coloca en un destino.** Hoy `revit_columns` no
  devuelve coordenadas, así que llevar un elemento a la posición de otro no es posible sin
  extender el endpoint.
- **`revit_set_param` relee después de escribir** y devuelve `verified`. Una escritura que no
  lanza excepción no es una escritura que aplicó.

## Contrato de diseño

Derivado de errores reales, no de estilo:

1. **Ningún fallback silencioso.** Si falta un prerrequisito de identidad (familia, tipo,
   nivel), el endpoint responde 4xx/5xx con el motivo. Nunca sustituye por "el primero
   disponible" — en geometría estructural, la familia **es** el resultado, y sustituirla
   produce un entregable que parece correcto y no lo es.
2. **Toda escritura va en `Transaction` explícita**, con `RollBack` ante excepción.
3. **Conjuntos parciales se abortan.** Si de N ids pedidos faltan algunos, no se opera sobre
   los que están: se devuelve 404 con la lista faltante.
4. **El log envuelve también los imports.** Un fallo en fase de import no debe saltarse el
   bloque que escribe el log.
5. **Las respuestas informan lo que pasó, no lo que se pidió.** Nunca se afirma éxito desde la
   propia entrada.

## Gotchas del host

Verificados leyendo el código de pyRevit 6.5.3 y por corridas reales, no por documentación.

### IronPython rompe el POST con `application/json`

`routes/server/server.py` hace `json.loads(data)` sobre los bytes crudos del cuerpo cuando el
`Content-Type` es `application/json`. En IronPython 3.4 `json.loads` **no acepta bytes**:
HTTP 500 con `the JSON object must be str, not 'bytes'`.

**Workaround sin parchear pyRevit**: el cliente manda `Content-Type: text/plain; charset=utf-8`
y el endpoint decodifica y parsea del lado de Revit. Es lo que hace `src/server.py`.

Corolario general: cuando el host corre IronPython, no asumir el comportamiento de la
librería estándar de CPython. `json.loads(bytes)`, encoding implícito y `str`/`bytes` son
justamente donde IronPython diverge.

### `pyrevit reload` con el servidor activo tumba Revit

Verificado con dos caídas consecutivas. El patrón: `startup.py` recarga y loguea sin error,
el servidor deja de escuchar en todo el rango, y Revit cae detrás. Recargar extensiones
mientras un servidor HTTP está escuchando deja el socket y el AppDomain inconsistentes.

**Todo cambio en `startup.py` exige cerrar y reabrir Revit.** Los pushbuttons sí toleran
`reload`: su `script.py` se lee en cada click.

### El servidor tarda en aceptar conexiones

| Señal del sondeo | Significa |
|---|---|
| `URLError` en todo el rango | Todavía no levantó |
| `RemoteDisconnected` en un puerto | Arrancando: algo escucha y corta |
| Respuesta JSON | Listo |

No diagnosticar antes de ~2 minutos desde abrir Revit.

### El puerto configurado es un piso

`serverinfo._get_next_available_port` arranca en el configurado y sube al primero libre. Con
dos instancias de Revit, la segunda toma el siguiente. **Sondear un rango**, no asumir.

## Endpoint o pushbutton

| | Endpoint (Routes) | Pushbutton |
|---|---|---|
| Hilo | Servidor, fuera del contexto de API | UI de Revit, contexto válido |
| Iterar | Exige reiniciar Revit | Relee en cada click |
| Salida | HTTP | Archivo en disco |
| Con el servidor caído | No sirve | Sigue funcionando |

Para volcados grandes, para API que quiera contexto de UI, y para iterar rápido, conviene el
pushbutton. `Constraints.pushbutton` es el patrón de referencia:

- Fases numeradas, con la última alcanzada guardada en el JSON de salida
- **Una unidad de prueba antes del lote**: si algo mata el proceso, se lleva una y no todas
- Log incremental con `flush` + `os.fsync` **antes** de cada llamada riesgosa, no después
- El JSON se escribe siempre, completo o no

El último punto es el que convierte un crash en diagnóstico. Un volcado parcial con la fase
alcanzada es un dato; un archivo ausente no dice nada.

## Estructura

```
revit-mcp-write/
├── src/server.py              # servidor MCP: 9 herramientas, descubre el puerto
├── RevitWrite.extension/
│   ├── startup.py             # endpoints de Routes (cambios = reiniciar Revit)
│   └── RevitWrite.tab/Servidor.panel/
│       ├── Estado.pushbutton/         # puerto real y endpoints registrados
│       └── Constraints.pushbutton/    # volcado de constraints de Rebar a JSON
└── _log/                      # log de la extensión y salidas JSON
```

## Licencia y alcance

Herramienta interna publicada como referencia. No es un producto: la tabla de verificación de
arriba es la medida real de en qué se puede confiar.
