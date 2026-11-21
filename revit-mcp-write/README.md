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
| 10 | `revit_mep_conectores` | POST | ⚠️ paquete probado en un RVT sintético por código suelto; **endpoint sin corridas reales** |
| 11 | `revit_mep_conectar` | POST | ⚠️ paquete probado en un RVT sintético por código suelto; **endpoint sin corridas reales** |
| 12 | `revit_mep_circuitos` | POST | ⚠️ paquete probado en un RVT sintético por código suelto; **endpoint sin corridas reales** |

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

## Trazado MEP con conexión verificada

Paquete `mep/`: Python puro, con la API de Revit **inyectada** (`DB` y `doc` llegan como
argumentos), válido a la vez para IronPython 3.4 dentro de pyRevit y para CPython en las
pruebas. Los endpoints y las herramientas MCP solo adaptan la entrada; la lógica vive en el
paquete.

> **Alcance de la verificación.** Las firmas se leyeron del binario instalado
> (`mep/API-REVIT-2027.md`), el comportamiento se probó con dobles de la API (`tests/`) y el
> paquete se corrió en Revit 2027 sobre un RVT sintético por el canal de código suelto. Los
> endpoints de Routes y varios caminos del trazado siguen sin probar en vivo: la evidencia y la
> lista de lo pendiente están al final de la sección.

| Herramienta MCP | Endpoint | Función del paquete | Escribe |
|---|---|---|---|
| `revit_mep_conectores` | `POST /mep/conectores` | `auditar_conectores(DB, doc, categorias, ids)` | No |
| `revit_mep_conectar` | `POST /mep/conectar` | `conectar_a_ramal(DB, doc, opciones)` | Sí, con ensayo por defecto |
| `revit_mep_circuitos` | `POST /mep/circuitos` | `crear_circuitos(DB, doc, opciones)` | Sí, con ensayo por defecto |

Las tres aceptan `documento` (título o ruta de un documento **ya abierto**, también en segundo
plano; por defecto el activo). No se abren archivos y no se opera sobre vínculos.

### Contrato de las dos escrituras

- **Ensayo por defecto.** Con `confirmar=false` todo se ejecuta dentro de la transacción, se
  verifica **dentro de ella** (tras `doc.Regenerate()`) y se hace `RollBack`. Solo
  `confirmar=true` explícito hace `Commit`. La respuesta trae `ensayo`, `confirmado` y `estado`
  (el `TransactionStatus` que devolvió Revit). `confirmado` es `true` únicamente si Revit
  devolvió `Committed`. Nada se lee después del `RollBack`: tras un ensayo los ids de la
  respuesta ya no existen (`ids_efimeros: true`).
- **Nunca se guarda el documento.** No hay `Save` ni `SaveAs` en ningún camino; una prueba lo
  comprueba sobre el código fuente.
- **Por lotes.** `lote` (25 por defecto, 1–200) y `desde`. **Una llamada = un lote = una
  transacción con nombre** (`MEP - conectar a ramal`, `MEP - crear circuitos de iluminacion`).
  La respuesta trae `siguiente` (valor de `desde` para continuar, o `null`).
- **Validación antes de abrir transacción.** Ids inexistentes, tipo ambiguo o inexistente,
  pendiente o límites fuera de rango, opción desconocida: error 400 con el motivo y el modelo
  intacto. Un conjunto parcial de ids aborta la llamada.
- **`None` es fallo.** Todo retorno `None` de la API (`Pipe.Create`, `BreakCurve`,
  `New*Fitting`, `ElectricalSystem.Create`…) se convierte en fallo explícito de ese elemento.
- **Un fallo no deja piezas a medias.** Cada conector (o cada circuito) va en su propia
  `SubTransaction`; si algo falla o queda suelto, se revierte solo ese intento y el lote sigue.
- **Sin diálogos.** Un `IFailuresPreprocessor` anota cada advertencia o error de la
  transacción, borra las advertencias y, si hay errores, ordena revertir. Todo vuelve en
  `advertencias`.
- **Ninguna excepción se traga.** Las atrapadas quedan en `errores` (etapa, elemento, tipo,
  mensaje).
- **`ok: true` significa que la operación corrió**, no que todo quedó conectado. Mirar
  `resumen`, `sueltos`, `sin_circuito`, `errores` y `confirmado`.

### Unidades

La API trabaja en pies; el paquete convierte solo con `UnitUtils` y `UnitTypeId`.

| Campo | Sentido | Unidad |
|---|---|---|
| `pendiente` | entrada | m/m, adimensional (`0.02` = 2 %); `0` para redes a presión. De 0 a 0.5 |
| `diametro_mm`, `salida_mm`, `tramo_minimo_mm`, `margen_extremo_mm` | entrada | mm |
| `limite_va` | entrada | VA. **Obligatorio, sin valor por defecto** |
| `diametro_mm` | salida | mm (solo tubería redonda) |
| `radio_interno_pies` | salida | pies (valor interno sin convertir) |
| `posicion_m`, `entronque_m` | salida | m, `[x, y, z]` en coordenadas internas del modelo |
| `carga_va`, `carga_va_calculada` | salida | VA |
| `tension_v`, `linea_linea_v`, `linea_tierra_v` | salida | V |

### `revit_mep_conectores` — auditoría (solo lectura)

Por elemento y en total: conectores, libres, dominio (`tuberia`, `electrico`, `ducto`),
clasificación y nombre del sistema, y diámetro. `IsConnected` se consulta solo en conectores
físicos (`End`, `Curve`, `Physical`); los lógicos se cuentan con `conectado: null`. El detalle
se limita con `max_elementos`; los totales recorren siempre todo el alcance.

Complementa a `revit_mep_conectividad` de `revit-mcp-tools` (hallazgos por disciplina): aquí
el detalle es por conector y admite una lista de ids.

```python
revit_mep_conectores(categorias=["OST_PlumbingFixtures", "OST_Sprinklers"])
# {"totales": {"elementos": 12, "conectores": 30, "libres": 12,
#              "por_dominio": {"tuberia": {"total": 30, "libres": 12}},
#              "por_diametro_mm": {"50.00": 12, "15.00": 18}, ...},
#  "elementos": [{"id": 1001, "total": 3, "libres": 1, "conectores": [
#      {"indice": 0, "dominio": "tuberia", "clasificacion": "Sanitary",
#       "libre": true, "diametro_mm": 50.0, "posicion_m": [2.0, 1.0, 0.6], ...}]}]}
```

### `revit_mep_conectar` — aparatos o rociadores a un ramal

Por cada conector físico de tubería del aparato que esté libre y cuya clasificación
(`PipeSystemType`) coincida con la del tipo de sistema pedido:

1. Elige el ramal candidato más cercano y calcula el **entronque**: el punto del eje del
   ramal más próximo en planta. Si cae fuera del tramo o a menos de `margen_extremo_mm` de un
   extremo, falla con motivo; no lo desplaza.
2. Traza: tramo de salida recto (solo si el conector no es vertical), **bajante o montante**
   hasta la cota que da la pendiente, y tramo horizontal hasta el entronque. La pendiente se
   construye con la cota de los extremos: el tramo **sube al alejarse del ramal**.
3. Une al aparato con `Connector.ConnectTo` (misma dirección y diámetro),
   `NewTransitionFitting` (distinto diámetro) o `NewElbowFitting` (distinta dirección); une los
   tramos con codos; une al ramal con **te** (`PlumbingUtils.BreakCurve` + `NewTeeFitting`) o
   con `NewTakeoffFitting` si `union="takeoff"`.
4. `doc.Regenerate()` y verificación de `IsConnected` en **cada** conector implicado: el del
   aparato, los dos extremos de cada tramo nuevo, todos los de cada accesorio y los del ramal
   en el entronque. Al final del lote se regenera y se verifica todo otra vez.

`sueltos` lista cada conector sin conectar: `elemento`, `rol` (`aparato`, `tramo_nuevo`,
`accesorio`, `ramal`), `conector` (índice), `posicion_m`, `motivo` y `revertido`. Con
`revertir_sueltos=true` (por defecto) el trazado de un conector con algo suelto se deshace y
no se confirma; con `false` se conserva para inspeccionarlo.

La te parte el ramal: para el lote siguiente hay que pasar `ramales=<ramales_siguientes>`.

```python
# 1) ensayo: nada queda en el modelo
r = revit_mep_conectar(categoria="OST_PlumbingFixtures", ramal=345678,
                       tipo_tuberia="PVC sanitario", tipo_sistema="Sanitario",
                       pendiente=0.02, lote=10)
# r["resumen"]  -> {"conectado": 9, "fallido": 1, "sueltos": 0}
# r["conexiones"][i] -> {"aparato": 1001, "conector": 0, "estado": "conectado",
#     "ramal": 345678, "tuberias": [..], "accesorios": [..],
#     "union_aparato": "ConnectTo", "entronque_m": [2.0, 0.0, 0.0], "diametro_mm": 50.0}

# 2) confirmar el mismo lote y seguir con el siguiente
r = revit_mep_conectar(categoria="OST_PlumbingFixtures", ramal=345678,
                       tipo_tuberia="PVC sanitario", tipo_sistema="Sanitario",
                       pendiente=0.02, lote=10, confirmar=True)
revit_mep_conectar(categoria="OST_PlumbingFixtures", ramales=r["ramales_siguientes"],
                   tipo_tuberia="PVC sanitario", tipo_sistema="Sanitario",
                   pendiente=0.02, lote=10, desde=r["siguiente"], confirmar=True)
```

Lo que **no** hace: no dimensiona, no evita interferencias, no entronca en ramales verticales,
no resuelve un aparato situado sobre el eje del ramal, no ajusta el entronque para que quepa
y no crea el sistema ni el ramal. Cada uno de esos casos devuelve un fallo con motivo.

### `revit_mep_circuitos` — luminarias a circuitos de potencia

1. Lee cada luminaria: conector eléctrico de potencia, circuito existente, **carga aparente**
   (`RBS_ELEC_APPARENT_LOAD`, buscada en el conector, la instancia y el tipo, en ese orden),
   tensión y polos. **No se inventa ninguna carga.**
2. Descarta con motivo: `sin_conector_electrico`, `ya_en_circuito`, `sin_carga`,
   `sin_tension_o_polos`, `incompatible_con_tablero` (tensión o polos fuera del sistema de
   distribución del tablero), `excede_limite` (una sola supera `limite_va`),
   `supera_max_circuitos`, `error_api`.
3. Agrupa en el orden recibido sin superar `limite_va` ni `max_luminarias`; solo comparten
   circuito las de iguales polos y tensión.
4. Por circuito: `ElectricalSystem.Create(doc, ids, PowerCircuit)`, `SelectPanel(tablero)`,
   `Regenerate` y verificación: el circuito quedó en el tablero pedido y contiene todas sus
   luminarias. Devuelve `id`, `numero`, `carga_va` (leída del circuito), `carga_va_calculada`,
   `dentro_del_limite` y `elementos`. Si la carga que calcula Revit supera `limite_va`, el
   circuito se revierte y sus luminarias quedan en `sin_circuito` con motivo.

**Lotes al confirmar.** Cada llamada recalcula el plan sin las luminarias que ya tienen
circuito. Por eso `desde` solo sirve en ensayo: al confirmar hay que repetir la misma llamada
con `desde=0` hasta que `siguiente` sea `null` (con `confirmar=True`, `siguiente` vale `0`
mientras queden circuitos por crear, y un `desde` distinto de cero se rechaza).
`max_circuitos` se aplica al plan de cada llamada.

```python
revit_mep_circuitos(tablero="TA-1", limite_va=1440.0, nivel="Nivel 2",
                    max_luminarias=12)               # ensayo
# {"ensayo": true, "confirmado": false, "circuitos_planeados": 4,
#  "circuitos": [{"id": 9001, "numero": "1", "carga_va": 1400.0,
#                 "dentro_del_limite": true, "elementos": [..]}, ...],
#  "sin_circuito": [{"id": 2002, "motivo": "sin_carga", "detalle": "..."}]}
```

### Canal de código suelto, sin reiniciar Revit

Los endpoints nuevos viven en `startup.py` y exigen reiniciar Revit. El paquete no: cualquier
canal que ejecute IronPython con `doc` disponible puede importarlo en el momento.

```python
import sys
carpeta = r"<ruta-del-repo>/revit-mcp-write"      # la carpeta que contiene 'mep'
if carpeta not in sys.path:
    sys.path.insert(0, carpeta)
from Autodesk.Revit import DB
from mep import ejecutar

resultado = ejecutar.correr("conectar", {
    "aparatos": [1001, 1002], "ramal": 345678, "tipo_tuberia": "PVC sanitario",
    "tipo_sistema": "Sanitario", "pendiente": 0.02}, doc, DB)    # ensayo
```

`correr(operacion, opciones, doc, DB)` admite `"conectores"`, `"conectar"` y `"circuitos"`, y
nunca lanza: una entrada inválida devuelve `{"ok": false, "error": ...}`. Tras editar el
paquete, `ejecutar.recargar()` descarta los módulos importados para que el siguiente `import`
lea el código del disco.

`startup.py` busca la carpeta que contiene `mep/` en este orden: variable de entorno
`REVITWRITE_MEP_DIR`, la carpeta que contiene a `RevitWrite.extension` (el repo), la propia
extensión y su `lib/`. Si la extensión se **copió** en vez de enlazarse, hay que copiar
también `mep/` o definir la variable.

### Pruebas

```console
py -m pytest revit-mcp-write/tests -q
```

Con dobles de la API (`tests/dobles.py`: conectores con `IsConnected` controlable,
transacciones con deshacer real, llamadas configurables para devolver `None`, lanzar o dejar
una unión suelta). Cubren validación, auditoría, ensayo y confirmación, sueltos, `None`,
lotes, nombre de transacción, ausencia de `Save` y agrupación por VA.

### Prueba en vivo sobre un RVT sintético (2026-11-21)

Revit 2027, canal de código suelto, documento abierto **en segundo plano** (no el activo).
Modelo creado para la prueba desde la plantilla métrica de sistemas del producto con familias de
su biblioteca: tres ramales (contra incendios 50 mm, sanitario 100 mm, agua fría 25 mm), 6
rociadores colgantes, 3 inodoros de tanque, 12 luminarias de 100 VA a 120 V y un tablero
120/208 V sobre un muro. Cada resultado se comprobó además con una lectura propia, fuera del
paquete.

| Caso | Resultado |
|---|---|
| Auditoría de 22 elementos | 30 conectores, 25 libres; dominio, clasificación y diámetro correctos |
| 6 rociadores al ramal, ensayo | 6 conectados con te (`BreakCurve` + `NewTeeFitting`), 0 sueltos; `RolledBack`, documento sin modificar y sin tuberías nuevas |
| Los mismos, `confirmar=True` | `Committed`; 6 de 6 conectores con `IsConnected` y en el sistema del ramal; `ramales_siguientes` con los 7 tramos |
| 3 inodoros al colector sanitario, pendiente 0,02 | conectados; tramo horizontal de 1,214 m con 0,0243 m de desnivel (0,0200); el conector de agua fría se omite con motivo |
| 3 inodoros al ramal de agua fría, pendiente 0 | conectados; el conector sanitario, ya unido, se omite con motivo |
| Extremos de tubería abiertos tras todo | 6: solo los dos de cada ramal original |
| Circuitos, `limite_va=400`, ensayo | 3 circuitos planeados de 4 luminarias y 400,0 VA según Revit; `RolledBack`, 0 sistemas en el modelo |
| Circuitos confirmados en dos llamadas (`lote=2`, luego el resto con `desde=0`) | 3 circuitos en el tablero, 400,0 VA cada uno; ninguna luminaria sin circuito |

La vista 3D exportada se revisó en imagen. Lo que la prueba corrigió o confirmó:

- `DistributionSysType.VoltageLineToGround/LineToLine` guardan **voltios**, no unidades
  internas (el tipo «120» da mínimo 110 y máximo 130); convertirlos descartaba todas las
  luminarias por «tensión fuera de rango». Los valores del conector (`GetMEPConnectorInfo`) sí
  son internos: 1291,67 = 120 V y 1076,39 = 100 VA.
- Las transacciones, las `SubTransaction` con `Regenerate` y el `IFailuresPreprocessor`
  definido en IronPython 3.4 funcionan sobre un documento en segundo plano.
- `Connector.ConnectTo` basta para unir al aparato cuando dirección y diámetro coinciden.

### Segunda prueba en vivo (2026-11-21, copia sintética ampliada)

Misma sesión y mismo método (documento en segundo plano), sobre una copia del modelo con tres
ramales más, 41 rociadores y 12 luminarias añadidos para la prueba.

| Caso | Resultado |
|---|---|
| Lote de 32 rociadores en una llamada (`lote=40`), te | ensayo 1,9 s y confirmación 2,3 s; 32 de 32 conectados, 0 sueltos; lectura propia: ningún rociador con conector libre y solo los dos extremos del ramal abiertos |
| `union="takeoff"` con un tipo de tubería **sin** takeoff en sus preferencias de enrutamiento | 4 de 4 `fallido` con el mensaje de Revit («No routing preference for takeoff set for this PipeType»); nada creado |
| `union="takeoff"` con un tipo que sí lo tiene (accesorio de la biblioteca del producto) | 4 de 4 conectados; cada takeoff refiere al ramal pedido y el rociador queda en el sistema del ramal |
| Conector realmente suelto (se desconectó el aparato tras la unión, dentro de la subtransacción) | con `revertir_sueltos=True`: `suelto_revertido`, dos filas en `sueltos` (aparato y tramo) y ninguna tubería nueva de ese aparato; con `False`: estado `suelto` y los demás conectados |
| `diametro_mm=25` con conector de 15 mm | **falló** como estaba escrito: Revit rechaza `NewTransitionFitting` contra el conector de un aparato («The owner should be (flex) duct or pipe»). Corregido: tramo corto del diámetro del conector y transición entre dos tuberías. Tras el cambio, 2 de 2 conectados con tubos de 15, 25 y 25 mm |
| Rociador a la cota del ramal (codo junto al aparato) | conectado con `NewElbowFitting` |
| Herramientas MCP reales (`revit_mep_conectores`, `revit_mep_conectar`, `revit_mep_circuitos`) por un cliente MCP contra `src/server.py`, con `documento` apuntando al modelo en segundo plano | auditoría, ensayo y confirmación de 2 rociadores, error 400 con motivo para una pendiente fuera de rango, y 12 luminarias en 3 circuitos de 400 VA; comprobado con lectura propia |

La corrida MCP usó los endpoints `/mep/*` de este `startup.py` registrados en la sesión abierta,
sin reiniciar Revit. La carga normal al arrancar Revit sigue sin observarse.

Otro hallazgo de la prueba: `ElementId.Value` es `System.Int64` en IronPython y el paquete lo
rechazaba como «no entero»; ahora lo acepta.

### Estado de los hallazgos de revisión

1. *La verificación del takeoff no probaba la unión con el ramal.* **Cerrado**: además de
   `IsConnected`, se exige que un conector del takeoff refiera al ramal pedido; si no, el
   conector se informa como suelto. No bloquea.
2. *No hay `Regenerate` entre fijar el diámetro y comparar radios.* **Cerrado**: la decisión
   ya no lee el radio del tramo nuevo; compara el diámetro pedido con el del conector.
3. *Los conectores del aparato se leen una vez y se reutilizan tras las subtransacciones.*
   **Abierto, no bloquea** el uso con aparatos de un conector por sistema (rociadores, inodoros
   con sanitario y agua fría: sin fallos en dos pruebas). Sin probar con aparatos de varios
   conectores del mismo sistema.

   **Caso de prueba pendiente** (sobre una copia sintética, nunca sobre un modelo de trabajo):

   - Aparato: una familia con dos conectores de tubería del mismo sistema, por ejemplo un
     lavamanos doble con dos bocas de agua fría o un colector con dos entradas.
   - Operación: `revit_mep_conectar` con ese aparato y un ramal, primero en ensayo y luego con
     `confirmar=True`, en un lote donde otro aparato falle para que haya una subtransacción
     revertida entre los dos conectores.
   - Se espera: una fila por conector, cada una con su propio `conector` y estado; los dos
     conectores quedan unidos al ramal al releerlos con `revit_mep_conectores`, y ninguna fila
     informa un conector que ya no existe o que pertenece a la subtransacción revertida.
   - Hasta que pase, los aparatos con varios conectores del mismo sistema se conectan de uno en
     uno y se relee cada resultado.

Condición de uso que sí importa: el tipo de tubería debe tener en sus preferencias de
enrutamiento la te, el codo, la transición y, si se pide, el takeoff. Si falta, el conector
queda `fallido` con el mensaje de Revit y no se crea nada.

### Sigue sin probar en vivo

1. La carga de los endpoints al arrancar Revit (lo probado es su registro en la sesión abierta).
2. Aparatos con varios conectores del **mismo** sistema y ramales con pendiente propia.
3. Que el preprocesador de fallos reciba advertencias en el `RollBack` del ensayo.
4. Luminarias de 277 V o de dos y tres polos.
5. Lotes de cientos de elementos (32 aparatos tardan unos 2 s).

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
├── src/server.py              # servidor MCP: 12 herramientas, descubre el puerto
├── RevitWrite.extension/
│   ├── startup.py             # endpoints de Routes (cambios = reiniciar Revit)
│   └── RevitWrite.tab/        # paneles de pushbuttons (Leer, Columnas, Acero…)
├── mep/                       # trazado MEP: Python puro, API de Revit inyectada
│   ├── auditoria.py           # auditar_conectores (solo lectura)
│   ├── trazado.py             # conectar_a_ramal
│   ├── circuitos.py           # crear_circuitos
│   ├── geometria.py           # cálculo del trazado, sin API
│   ├── transaccion.py         # ensayo/confirmar, subtransacciones, fallos sin diálogo
│   ├── base.py                # ids, unidades, conectores, validación
│   ├── ejecutar.py            # correr(operacion, opciones, doc, DB)
│   └── API-REVIT-2027.md      # firmas leídas del binario instalado
├── tests/                     # pytest con dobles de la API (sin Revit)
└── _log/                      # log de la extensión y salidas JSON
```

## Licencia y alcance

Herramienta interna publicada como referencia. No es un producto: la tabla de verificación de
arriba es la medida real de en qué se puede confiar.
