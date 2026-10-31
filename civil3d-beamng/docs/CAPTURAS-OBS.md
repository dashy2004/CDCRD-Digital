# Tomas de Civil 3D con OBS

La integración propia usa el [protocolo oficial de OBS WebSocket](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
y el cliente externo [obsws-python](https://github.com/aatikturk/obsws-python).
No incorpora el código de esos proyectos. Dependencias fijadas en
`../requirements-tech.txt`; OBS debe estar instalado aparte.

`tools/tech/capturas_obs.py` crea un perfil y una colección propios, conserva
los nombres anteriores y comprueba que siguen seleccionados antes de actuar.
Requiere WebSocket local autenticado. La configuración privada se lee en memoria;
las credenciales no se incluyen en los recibos. No inicia transmisiones.
Las entradas de audio de la colección nueva se silencian; la captura de ventana
también tiene audio desactivado.

## Preparar y comprobar

Importar `CaptureSession` desde `civil3d-beamng/tools/tech` con Python. Ejemplo,
adaptando las rutas locales y un nombre de sesión nuevo:

```python
from capturas_obs import CaptureSession
from pathlib import Path
import time

s = CaptureSession(
    Path.home() / "AppData/Roaming/obs-studio/plugin_config/obs-websocket/config.json",
    ".local/tomas/nueva-sesion", "CDCRD-Civil3D-demo-01")
s.prepare()
s.target("[Drawing1.dwg]")  # Nombre exacto observado en doc.info/ventana
s.snapshot("comprobacion")
with s.recording("00_prueba"):
    time.sleep(8)
s.close()
```

La selección exige exactamente una ventana de `acad.exe`. WGC (método 2) es
obligatorio: en esta máquina el modo automático mostraba la interfaz y dejaba
vacío el área 3D acelerada. La salida es 1920×1080, 30 fps, MKV y calidad HQ.
Verificar el video de prueba con ffprobe y un fotograma antes de grabar trabajos.

Los cambios de `SetProfileParameter` no siempre actualizan el codificador vivo;
el preparador reactiva su perfil. Se confirmó un cierre de OBS 33.0.0/Qt6Core
durante una primera prueba local. Reiniciar OBS con el perfil guardado permitió
la siguiente prueba de 8 segundos, verificada en 1080p/30. Esto no identifica
una causa definitiva ni garantiza otras instalaciones. Ante cierre/timeout,
inspeccionar estado y archivos: no reintentar automáticamente StartRecord.

## Grabar la generación

Después de validar la sesión, ejecutar desde la raíz del repositorio:

```powershell
python civil3d-beamng/examples/calle_demo/filmar.py --apply `
  --template "C:/Templates/metric.dwt" `
  --output ".local/escenas/calle-demo/nueva-grabacion" `
  --obs-config "$env:APPDATA/obs-studio/plugin_config/obs-websocket/config.json" `
  --obs-directory ".local/tomas/nueva-sesion" `
  --obs-session "CDCRD-Civil3D-demo-01"
```

Sin `--apply` solo muestra el plan. Crea un dibujo métrico vacío, conserva los
anteriores y comprueba el documento antes de cada escritura. Las tomas separan
eje, terreno/rasante/corredor, bache/aceras/relieve, bloques y marcas; después
graban general, planta, bache, entorno y una órbita por pasos de inspección.
También incluye acercamiento al bache y vista lateral del relieve.
La órbita no se presenta como animación cinematográfica fluida.

`doc.save` exporta la base de datos a DWG sin renombrar la pestaña abierta:
la selección de ventana utiliza el nombre de `doc.info`, no el DWG exportado.
No cambiar de pestaña mientras se genera; un cambio detiene la siguiente escritura.

`obs-session.json` registra fase, ruta, tamaño y SHA256 de cada toma cerrada.
Una toma puede cerrarse correctamente aunque falle la acción CAD: consultar
`action_completed`. Las fases `start_requested`/`stop_requested` sin conclusión
requieren inspección. No hay reanudación automática de una corrida CAD parcial.
Los recibos no sustituyen la revisión visual ni la comprobación con ffprobe.
Al terminar, `s.restore()` recupera perfil y colección anteriores si no hay salidas
activas y la sesión sigue siendo la nuestra. Los videos y DWG quedan fuera de Git.

## Resultado local del 2026-10-31

Se grabaron 15 tomas de trabajo: cinco etapas de construcción, siete vistas y
tres versiones corregidas de general/planta/órbita. Los MP4 derivados conservan
H.264 sin recodificar, eliminan la pista de audio vacía y permiten edición en
Linux. Los 15 archivos se decodificaron completos sin errores, en 1920×1080/30;
se inspeccionó un fotograma de cada toma. No equivale a reproducción humana
continua de cada video. Se preparó además una previa de 51 segundos sin voz.
OBS quedó sin grabación y con perfil/colección anteriores restaurados.

La suite del proyecto pasó 94 pruebas y 3 subpruebas; una comprobación opcional
de COLLADA se omitió por ausencia de `pycollada`. Ejecutar desde `civil3d-beamng`:
`python -m pytest -o pythonpath=. tests -q`.
