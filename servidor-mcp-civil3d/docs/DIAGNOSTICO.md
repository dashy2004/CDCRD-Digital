# Diagnostico y recuperacion del puente

## Secuencia segura

1. Confirmar turno exclusivo, PID de Civil 3D y dibujo esperado. No consultar ni
   modificar un original como prueba de recuperacion.
2. Consultar `estado_puente` (`ping`), `estado_cola` (`diag.cola`) y
   `eventos_dialogo` (`diag.dialogos`). Estos metodos responden desde el socket:
   un `ping` correcto no acredita disponibilidad del hilo principal.
3. Si hay solicitudes activas, revisar sus identificadores y esperar su estado
   final antes de continuar. Si hay un dialogo, identificar su texto y resolver
   la condicion concreta; no cerrarlo a ciegas.
4. Con la cola libre, llamar `ping_comandos(timeout_ms=3000)` (`diag.ping`).
   Si vence, conservar el diagnostico y revisar la sesion; no encadenar lecturas
   o escrituras que necesitan el mismo hilo. Si responde `inactivo=true`,
   consultar `doc.info` y comprobar ruta, producto y unidades antes de operar.

La sonda, la cola y los dialogos ayudan a localizar el bloqueo, pero no bastan
para atribuir una causa a un incidente anterior. Registrar el resultado real y
separar las hipotesis de lo confirmado.

## estado_puente

Primera llamada de cualquier sesion: puerto, version, `build` (MVID del DLL
cargado), ruta del DLL, si escritura/comandos estan habilitados y donde esta
el log. Comparar el PID que escucha en el puerto y la ruta/build cargados con
la instalacion esperada. Un `build` sin cambios no demuestra por si solo que
quedo una instancia anterior: tambien puede haberse cargado el mismo DLL.

## leer_log_puente

`n` ultimas lineas de `%LOCALAPPDATA%\CdcrdCivil3dBridge\puente.log`. No
depende de que Civil 3D este inactivo: es la via para ver que paso cuando una
herramienta vencio por timeout o Civil 3D quedo en un dialogo. El codigo actual
escribe UTF-8 sin BOM; puede leerse con `Get-Content -Encoding utf8` en
PowerShell. `leer_log_puente` (`diag.log`) tambien se sirve desde el socket.

## ping_comandos

`diag.ping` encola una funcion que devuelve `ok` en `Application.Idle`, con
timeout entre 200 y 30000 ms. No ejecuta un comando CAD, no toca el dibujo y no
acredita la finalizacion de un comando anterior. `inactivo=true` confirma que
esa sonda se despacho durante la espera; no garantiza disponibilidad futura.
`inactivo=false` indica que no se despacho a tiempo, sin identificar por si
solo la causa.

## Timeouts, cola y recibos

Tras un timeout, no repetir automaticamente una escritura. Consultar
`estado_cola` y buscar el `request_id` del error:

- `cancelada` / `cancelada_antes_de_ejecutar=true`: ese despacho no comenzo y no
  ejecutara su funcion al regresar Idle. Resolver primero la causa del bloqueo
  y verificar el dibujo antes de plantear otro intento.
- `ejecutando` / `resultado_incierto=true`: la operacion comenzo. Esperar su
  finalizacion y releer el resultado; no se puede afirmar que fue cancelada.
- `terminada`: revisar el campo `error` y comprobar el dibujo. Para `cmd.run`,
  solo acredita que el comando fue encolado, no que termino.

Para `ejecutar_comando_seguido`, consultar su ticket con `consultar_comando`
(`cmd.estado`), que responde desde el socket. Un recibo de fin del comando no
sustituye la verificacion de la geometria. Un timeout de transporte, un recibo
ausente o un reinicio no prueban que una escritura no ocurrio. Los historiales
son limitados y no persisten entre sesiones; guardar la evidencia antes de
reiniciar.

## deshacer

Encola `_.U` n veces. Asincrono: verificar despues con una consulta. No usarlo
como recuperacion generica de un timeout: podria deshacer una operacion ajena.

## eventos_dialogo (puente >= 0.5.0)

Detecta dialogos modales abiertos en el proceso de Civil 3D (user32 por
P/Invoke): `modal_abierto=true` cuando la ventana principal esta
deshabilitada, mas la lista de ventanas candidatas (`#32770` de AutoCAD,
WinForms, WPF) con titulo y estado. Desde 0.5.2 se sirve desde el hilo del
socket, usando user32 sin consultar la API de AutoCAD; no depende de Idle.
Los dialogos clasicos incluyen sus textos cuando estan disponibles.

`modal_abierto=false` solo indica que la ventana principal esta habilitada.
No prueba ausencia de comandos ni disponibilidad del hilo principal. La lista
de ventanas tampoco confirma que cada candidata sea modal. Resolver una
condicion de UI no autoriza repetir una escritura sin comprobar cola y recibos.

## Reinicio y recarga

`CDCRDMCP` inicia el servidor si hace falta; repetirlo cuando ya esta suscrito
no reconstruye la suscripcion a Idle. `CDCRDMCPSTOP` detiene el servidor TCP;
no descarga el DLL. Una nueva compilacion del puente requiere un cierre y
arranque normales para cargar el build instalado. El servidor MCP Python es
otro proceso: recargarlo y comprobar su catalogo no reemplaza esa verificacion.

Antes de reiniciar, identificar exactamente el PID, puerto y documentos de la
instancia, comprobar que no hay llamadas en curso ni en cola y guardar su
evidencia. Reiniciar solo la instancia de prueba, sin originales abiertos ni
trabajo sin guardar. Si no se puede comprobar ese estado, no cerrar ni matar
el proceso. Nunca usar `taskkill` generico sobre `acad.exe` ni cerrar otras
instancias por nombre. Tras el arranque, repetir la secuencia segura y verificar
el nuevo PID, build y dibujo antes de reanudar el trabajo.
