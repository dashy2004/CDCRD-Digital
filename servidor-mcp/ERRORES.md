# Errores verificados del servidor MCP — registro y reglas

Este archivo complementa `AUDITORIA-2026-08-07.md` (auditoría de código) y las "Limitaciones
conocidas" del README principal. Ahí está el diagnóstico final; acá está **cómo se llegó a
cada uno**: el error real, cómo se detectó, y la regla que deja para quien use o extienda este
servidor. Instalación paso a paso con sus propios fallos ya documentados: `instalacion/INSTALACION.md`.

Cada entrada nació de una corrida real contra ETABS 23.3.0 / OAPI 2.016, no de lectura de
documentación. Se conservan los números `E-NNN` originales por trazabilidad interna; no son
correlativos porque el archivo completo cubre también instalación y otros proyectos que no
aplican aquí.

## Formato
```
### E-NNN — Título en una línea
**Qué pasó**: el hecho.
**Causa raíz**: por qué pasó.
**Regla**: instrucción generalizable.
```

---

## Semántica de las herramientas de escritura sobre tablas

### E-024 / E-028 — `set_table_data` reemplaza la tabla entera, no solo las filas enviadas
**Qué pasó**: escribir 2 filas de `Frame Assignments - Section Properties` y releer mostró que
una fila de control, no incluida en el envío, conservaba su valor — pero era el valor **por
defecto**, así que el test no distinguía "se preservó" de "se borró y volvió al default". Con
un valor de control distinto del default (probado sobre `Area Assignments - Section
Properties`), quedó claro: **cada llamada reemplaza la tabla completa**. Escribir 3184 filas en
7 tandas de 500 borra las tandas anteriores; hay que escribir todo en una sola llamada.
**Causa raíz**: el mensaje de retorno (`"Tabla escrita: N fila(s)"`) describe cuántas filas se
*enviaron*, no si ETABS las *aplicó* ni si preservó lo que no se tocó. `ApplyEditedTables`
devuelve conteos de error/warning que el wrapper no propaga.
**Regla**: para tablas grandes, acumular todas las filas y escribir en una sola llamada. Para
verificar que una escritura se aplicó (no solo que se envió), releer la tabla después. Un test
de "¿se borra lo que no escribo?" necesita un valor de control distinto del default en ambas
hipótesis, o no distingue nada.

### E-023 — `run_concrete_design` / `run_steel_design` "ejecutados" no significa resultados legibles
**Qué pasó**: el comando devuelve `"Diseño ejecutado con código 'ACI 318-19'"` sin error. Las
tablas de resultado (`Concrete Beam Design Summary`, `Concrete Column Design Summary`, `Design
Forces - Columns`, `Joint Design Reactions`) fallan con `ret=1` o devuelven solo los nombres de
campo, sin un solo valor de `PMMRatio` ni de `Status`.
**Causa raíz**: el código de retorno del comando de diseño no dice nada sobre si el diseño
pasó, falló, o es ilegible — son preguntas independientes. Confundir "corrió sin error" con
"hay un resultado que se puede leer" es el error.
**Regla**: tratar el diseño (ACI/AISC vía este servidor) como no verificado hasta encontrar un
camino de lectura que funcione contra la instalación propia. Hoy no lo hay confirmado — es una
limitación abierta, no una que se vaya a resolver leyendo la documentación de la OAPI.

---

## Semántica de los filtros geométricos

### E-029 — `elevations=[...]` selecciona por "todos los extremos en la lista", no "vive en esa cota"
**Qué pasó**: `assign_frame_distributed_load` y `assign_area_uniform_load` con la lista
completa de cotas de un edificio de muchos niveles capturaron diagonales y muros que **no**
estaban en un solo nivel — porque sus dos extremos, cada uno en un nivel distinto, estaban
ambos en la lista pasada. Una carga de fachada calculada para el perímetro cayó también sobre
elementos diagonales que no debían recibirla.
**Causa raíz**: la semántica real es "todos los extremos del objeto están en la lista de
cotas", no "el objeto vive en esa cota". El ejemplo de la propia documentación (`elevations=[3,
6]` para "niveles intermedios") refuerza la lectura intuitiva pero equivocada.
**Regla**: comparar siempre el conteo de objetos afectados que la herramienta devuelve contra
el esperado, antes de seguir — es gratis y lo delata al instante. Para modelos con elementos
que saltan de nivel (diagonales, muros altos), pasar **cotas alternadas** (nunca dos niveles
consecutivos en la misma llamada) excluye por construcción cualquier elemento que abarque más
de un piso, sin depender de tener clara la regla de matcheo.

---

## Ejecución de análisis y control de procesos largos

### E-030 — Un timeout de `run_analysis` no significa que el análisis no arrancó
**Qué pasó**: `run_analysis` devolvió `Request timed out`. Se interpretó como "no arrancó" y
se volvió a llamar. En realidad ETABS ejecuta el análisis como **proceso separado** y sigue
respondiendo a otras llamadas COM mientras corre — la segunda llamada intentó tocar archivos
temporales que la primera ya tenía abiertos y produjo `FILE OPERATION ERROR # 232`, dejando el
solver colgado sin responder a Cancel.
**Causa raíz**: se usó "¿responde COM?" como prueba de "¿terminó el análisis?". No es la misma
pregunta. La señal correcta está en el archivo `.LOG` del modelo, que crece mientras el solver
itera.
**Regla**: ante un timeout de transporte sobre una operación larga y no idempotente
(`run_analysis` es el caso obvio, pero aplica a cualquier operación de este tipo), no reintentar
nunca por ese motivo solo. Medir una señal externa de progreso — tamaño de `.LOG`, en dos
instantes separados por más que el período esperado de esa señal — antes de decidir si sigue
corriendo o está colgado de verdad (colgado = delta cero entre las dos medidas).

---

## Modelado con geometría generada por script

### E-032 — Verificar el conteo de nudos no verifica que el modelo esté conectado
**Qué pasó**: un modelo grande generado por script pasó el chequeo de nudos deduplicados (el
número exacto esperado) pero tenía dos subconjuntos sin conectar entre sí — piezas que
arrancaban en una cota donde ningún otro elemento del modelo tenía un nudo. El análisis corrió
completo y falló en el solver por autovalores negativos (mecanismo), no por un error de
geometría visible.
**Causa raíz**: el conteo de nudos verifica transcripción ("¿se crearon los puntos que se
mandaron a crear?"), no conectividad ("¿cada pieza toca a la siguiente?"). Esa segunda
pregunta requiere el mapa nudo → elementos incidentes, que no formaba parte de la salida del
generador.
**Regla**: todo generador de geometría para análisis estructural debería emitir, junto con la
geometría, el censo de nudos con un solo elemento incidente (extremos libres) y la lista de
componentes conexas del grafo de elementos. Un extremo libre se justifica explícitamente
(apoyo, borde real de la estructura) o es un defecto a corregir antes de correr el análisis —
más barato que un ciclo de solver completo para descubrirlo.

---

## Diagnóstico de conexión y despliegue

### E-014 — Fallo de conexión COM con código verificado: revisar privilegios primero
**Qué pasó**: con el servidor y el archivo ya verificados, `get_model_info` seguía devolviendo
"No hay conexión con ETABS" pese a que ETABS estaba abierto con un modelo cargado.
**Causa raíz**: Claude Desktop (o el cliente MCP) y ETABS corriendo en distinto nivel de
privilegio (uno como Administrador, el otro no) aíslan `GetActiveObject` sin lanzar un error
explicativo.
**Regla**: ante un fallo de conexión COM con el entorno aparentemente correcto, revisar primero
si ambos procesos corren al mismo nivel de privilegio, antes de seguir reintentando la misma
llamada. Ya está en `instalacion/INSTALACION.md`, paso 3 — se repite acá porque fue la causa
final de la instalación original, después de que todo lo demás ya estaba correcto.

### E-015 / E-016 — Herramientas "faltantes" pueden ser de despliegue, no de código
**Qué pasó**: el servidor exponía 10 herramientas en vez de las ~54 actuales. El diagnóstico
inicial ("hay que escribirlas") era falso: el código ya las tenía, en la carpeta correcta —el
`command`/`args` del cliente apuntaba a una copia anterior en otra ruta.
**Causa raíz**: una capacidad ausente en un servidor MCP tiene tres causas posibles y no se
distinguieron: (1) el código no existe, (2) existe pero el cliente apunta a otra copia, (3)
existe y está registrado pero el proceso no se reinició. Confundirlas manda a reescribir código
que ya existe.
**Regla**: ante una herramienta ausente, verificar en ese orden: `grep` del nombre en el
código de la copia real; ruta exacta en el config del cliente (`args`); reinicio completo del
cliente desde el ícono de bandeja, no solo cerrar la ventana.

---

## Nota de método

Todas las entradas anteriores comparten una forma: **la herramienta ya devolvía la evidencia
que habría delatado el problema** (un conteo, un archivo que crece, un valor de control), y en
cada caso se prefirió la lectura de la documentación o la interpretación intuitiva por encima
de medir. La contramedida no es "prestar más atención" — es un paso explícito: antes de
reportar cierre sobre cualquier escritura, filtro o ejecución larga, comparar el resultado
devuelto contra lo esperado, y si no coincide, no seguir.
