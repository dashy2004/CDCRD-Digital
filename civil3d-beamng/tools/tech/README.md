# Entorno opcional para BeamNG.tech y grabación

Estas son dependencias de sus autores, no implementaciones copiadas en CDCRD.
El conversor para Drive conserva su entorno independiente.

Desde la raíz del repositorio:

```powershell
python -m venv .local/venvs/beamng-tech
.local/venvs/beamng-tech/Scripts/python.exe -m pip install -r civil3d-beamng/tools/tech/requirements.txt
.local/venvs/beamng-tech/Scripts/python.exe -m pip check
.local/venvs/beamng-tech/Scripts/python.exe civil3d-beamng/tools/tech/diagnostico.py
```

BeamNGpy 1.36 corresponde a **Tech 0.39**, según la
[tabla oficial](https://github.com/BeamNG/BeamNGpy/blob/master/COMPATIBILITY.md).
Antes de conectar, comprobar la versión del ejecutable Tech y elegir el SDK
correspondiente. Instalar el SDK no instala ni activa el simulador.
El archivo personal `tech.key` pertenece a la instalación privada del simulador.
Nunca incluirlo, ni el enlace personal de descarga, en Git.

OBS 28 o posterior incluye [obs-websocket](https://github.com/obsproject/obs-websocket).
El cliente [obsws-python](https://github.com/aatikturk/obsws-python) se instala
separadamente desde PyPI. Mantener autenticación activada. Para comprobar una
instancia local de OBS ya abierta, agregar al diagnóstico `--obs-config` con la
ruta privada de su configuración. El diagnóstico solo consulta versión y estado;
no inicia grabación, emisión ni captura de pantalla.

Las herramientas World Editor, Path Camera, Replay y ScriptAI se usan dentro del
simulador; no son paquetes Python que deban instalarse por separado. ROS 2 queda
fuera de esta primera animación. Ver [fuentes y licencias](../../docs/REFERENCIAS-BEAMNG.md).

Al validar una instalación, conservar `pip freeze`, versión del motor y recibo
de ejecución en `.local/`. La compatibilidad del SDK no prueba la importación,
la física del bache, las cámaras ni la grabación del escenario.

## Descarga privada opcional

`descargar_build.py` recibe una carpeta privada con `build-download.private.json`
(campo `url`, enlace personal HTTPS de api.beamng.com) y `archive-size.json`
(`zip_bytes` y `uncompressed_bytes`, inspeccionados en el ZIP oficial). También
recibe la ruta local de `tech.key` y un destino de instalación que todavía no existe.
El directorio del trabajo debe estar en el mismo volumen que la instalación.

El ejecutor conserva partes para inspección tras un fallo, comprueba los rangos
HTTP, tamaños y rutas del ZIP, verifica CRC al extraer y copia la licencia al
directorio raíz del motor. `install-status.json` distingue descarga, extracción
e instalación. No inicia el motor ni acredita la activación de la licencia.
Guardar estos archivos en una carpeta privada ignorada, nunca en Git ni en BRAIN.

El número de conexiones admite 1–8. Antes de ejecutarlo, comprobar espacio para
las partes, ZIP ensamblado, instalación y margen. No instalar encima de Drive.
