# Diagnostico del puente (Etapa 3.6)

## estado_puente

Primera llamada de cualquier sesion: puerto, version, `build` (MVID del DLL
cargado), ruta del DLL, si escritura/comandos estan habilitados y donde esta
el log. Si tras un reinicio `build` no cambia, quedo un `acad.exe` vivo con
el DLL viejo: cerrarlo desde el Administrador de tareas.

## leer_log_puente

`n` ultimas lineas de `%LOCALAPPDATA%\CdcrdCivil3dBridge\puente.log`. No
depende de que Civil 3D este inactivo: es la via para ver que paso cuando una
herramienta vencio por timeout o Civil 3D quedo en un dialogo. El log es
UTF-16: desde un shell, `iconv -f UTF-16LE -t UTF-8 ... | tr -d '\000'`.

## ping_comandos

Comprueba que la cola de comandos (`ejecutar_comando`) responde.

## deshacer

Encola `_.U` n veces. Asincrono: verificar despues con una consulta.

## eventos_dialogo (puente >= 0.5.0)

Detecta dialogos modales abiertos en el proceso de Civil 3D (user32 por
P/Invoke): `modal_abierto=true` cuando la ventana principal esta
deshabilitada, mas la lista de ventanas candidatas (`#32770` de AutoCAD,
WinForms, WPF) con titulo y estado. Uso tipico: una peticion vencio por
timeout -> `eventos_dialogo` dice si hay un modal bloqueando y cual; alguien
lo cierra (control remoto o el operador) y se reintenta.

Limite: si el modal bloquea ademas la bomba de `Application.Idle`, la propia
llamada puede vencer; en ese caso `leer_log_puente` sigue respondiendo (no
pasa por el hilo principal) y es el plan B.
