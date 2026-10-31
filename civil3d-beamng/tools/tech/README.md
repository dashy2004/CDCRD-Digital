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

`--connections` fija la partición del archivo y debe mantenerse al reanudar.
`--workers` controla las peticiones simultáneas (por defecto, hasta dos). Así se
puede reducir la concurrencia sin descartar partes. `download-partition.json`
impide reutilizar partes con otra partición. No ejecutar dos instaladores sobre
el mismo trabajo. Tras un HTTP 503, conservar las partes y comprobar primero si
ya existe un ZIP completo en el equipo o en la Papelera.

## Usar un ZIP local recuperado

Recuperar solo el archivo identificado, conservando el original de la Papelera.
Comprobar tamaño, SHA256 de origen/copia y CRC del ZIP antes de utilizarlo. El
hash comprueba integridad de la copia; no sustituye la verificación de origen.
El instalador acepta el archivo recuperado sin consultar la URL personal:

```powershell
python civil3d-beamng/tools/tech/descargar_build.py `
  --job .local/tech-job --archive .local/BeamNG.tech.zip `
  --sha256 <SHA256_VERIFICADO> --license <RUTA_PRIVADA_TECH_KEY> `
  --destination <DIRECTORIO_NUEVO>
```

Esta modalidad requiere `archive-size.json` con los tamaños inspeccionados,
revalida el SHA256, rechaza rutas inseguras y comprueba CRC al extraer. Conserva
el ZIP y las partes de descargas anteriores; no usa `build-download.private.json`.
Exige espacio para el contenido descomprimido y 5 GB de margen. Si falla, conserva
la instalación parcial para inspección y rechaza sobrescribirla en otro intento.
No inicia el ejecutable: comprobar su versión y firma del editor antes de abrirlo.

## Filmar incidentes ilustrativos

`film_events.py` conecta una instancia Tech ya abierta, comprueba su carpeta de
usuario y nivel autorizado, y crea un escenario nuevo con trayectorias ScriptAI.
Registra posición, velocidad, orientación, freno y daño del vehículo junto con el
recibo OBS. Las trayectorias usan estaciones y offsets del eje exportado; el viaje
en sentido contrario conserva tiempos crecientes. No reconstruye un accidente
real ni acredita lesiones, causalidad o exactitud física de un mod.

La configuración JSON privada necesita `snapshot`, `manifest`, `user`, `port`,
`allowed_levels`, `output` y `events`. Cada evento define `vehicles` (id, model,
start, end, speed en m/s; config, offset, offsets y color opcionales), además de
`brake_station`, `max_seconds`, `hold_after_damage` y `stop_after_damage` cuando
corresponda. `camera_pos` y `camera_target` son [estación, offset derecho, altura].
Para una calle lateral, un vehículo puede sustituir `start`, `end` y los offsets
por `path_abs_m: [[E,N,Z], ...]`. Son coordenadas absolutas del mismo dibujo CAD;
el ejecutor resta el origen del paquete, orienta el vehículo según el primer
segmento y calcula tiempos acumulados a partir de `speed` (m/s). Rechaza puntos
no finitos, segmentos sin longitud horizontal y velocidades no positivas antes
de conectarse al motor. `lift` desplaza verticalmente la aparición y la ruta.
La velocidad configurada es un objetivo de ScriptAI: usar la telemetría para
informar la velocidad realmente alcanzada.
`background: true` deja un vehículo nativo estacionado con frenos aplicados,
sin IMU y fuera del criterio de fin por daño. La orientación de aparición usa
la convención del motor (cero hacia -Y); se comprueba contra el primer segmento
antes de comenzar. `illustrative_daylight: true` aplica iluminación uniforme
al nivel de la toma para facilitar una presentación didáctica.
Para OBS: `obs_config`, `obs_directory` y `obs_name` deben identificar una sesión
aislada preparada con `CaptureSession`; `game_audio: true` captura únicamente el
audio de la ventana seleccionada. El micrófono y el audio global siguen como estén
configurados en esa colección: comprobar que permanezcan silenciados.

```powershell
python civil3d-beamng/tools/tech/film_events.py .local/incident-config.json `
  --event rear --camera driver --label CDX_VR_TAKE01 --record --vr `
  --ready-file .local/ready-take01.flag
```

`--vr` requiere Vulkan, un runtime OpenXR previamente seleccionado y una escena
OBS `<obs_name>-VR` con una referencia al mismo origen de ventana. Desactiva los
límites de FPS, activa OpenXR y comprueba una sesión ejecutándose antes de grabar.
Se conserva la selección de runtime del sistema. `--ready-file` debe ser una ruta
nueva: con VR, el operador crea el archivo **después** de recibir confirmación de quien
lleva el visor. Sin VR sirve como puerta de inspección visual y puede crearlo
el operador después de revisar el encuadre. `participant_ready` solo acredita
la confirmación del participante cuando también se utiliza `--vr`.
El escenario espera pausado hasta 15 minutos, centra la vista en VR y
deja tres segundos antes de mover los vehículos. Nunca crear el marcador por el
mero paso del tiempo. Sin marcador, el ejecutor comienza de inmediato.

Al terminar, detiene OBS, pausa la física y desactiva ScriptAI; conserva el motor
abierto y VR en su estado actual. Las tomas y recibos anteriores no se sobrescriben.
`--pov-vehicle` elige otro vehículo configurado para la cámara de conductor.
Los mods se obtienen de sus autores y se instalan privadamente: este repositorio
no redistribuye vehículos ni recursos del fabricante.

### Personajes visuales en escenas sin contacto

`people_meshes.py` convierte un JSON privado de poses inspeccionadas en Blender
en fotogramas COLLADA y materiales. El JSON contiene `vertices`, `triangles`
y un nombre de material por triángulo en cada pose. Revisar escala, orientación,
pies, desplazamiento y licencia del modelo antes de exportar; no se incluyen
modelos de terceros en el repositorio.

`cdcrdVisualPeople.lua` carga `art/actors/poses.json` dentro de un nivel `cdx_`
coincidente con la configuración. `visual_people` coloca un adulto y estudiantes
genéricos; los estudiantes caminan 7.9 m hacia -Y a 1.25 m/s, con un ciclo de
25 poses a 24 fps y transición de altura a la acera. Estos parámetros son de
puesta en escena. `start_s` inicia el cruce por tiempo; `wait_for_stop: true`
espera la orden de freno y una velocidad del vehículo inferior a 0.2 m/s.
Las posiciones y el reloj se guardan junto a la telemetría.

Los actores tienen colisión desactivada: permiten ilustrar cruces sin contacto,
pero no simular atropellos, fuerzas sobre peatones ni lesiones. La propuesta
de señalización y la conducta de los participantes no constituyen un diseño
vial validado. Al terminar el nivel se eliminan solo los actores de esta extensión.
# Repeticiones con AdvancedIMU

`film_events.py` acepta `imu.defaults` y `imu.vehicles` en la configuración local.
Conserva todos los lotes de AdvancedIMU en el recibo de la toma y el origen del
reloj de simulación. Ejemplo de montaje (parámetros de BeamNGpy):

```json
{"imu":{"defaults":{"physics_update_time":0.005,"gfx_update_time":0.05,
 "pos":[0,0,0.7],"dir":[0,-1,0],"up":[0,0,1],"is_using_gravity":false,
 "is_send_immediately":false,"is_allow_wheel_nodes":false,
 "is_visualised":false,"is_snapping_desired":true,"is_force_inside_triangle":true}}}
```

`imu_report.py recibo.json salida_nueva` necesita NumPy y Matplotlib. Exporta CSV,
PNG, SVG, resumen JSON y picos. Comprueba reloj creciente, huecos, finitud y base
ortonormal. Los ejes del montaje anterior son **longitudinal, vertical, lateral**,
en ese orden; no XYZ longitudinal/lateral/vertical. La aceleración se expresa en
m/s² y g (9.80665 m/s²). El giro se conserva en mundo y se proyecta a la base local:
en la implementación Tech 0.39, `angVel`/`angAccel` son vectores globales.

La media de cinco muestras es un filtro editorial explícito (25 ms a 200 Hz), no
una clase de filtrado para homologación de choques. Se excluyen los primeros 0.5 s
de los picos, conservándolos en el CSV. La masa de la lectura corresponde al punto
interpolado del sensor, no a toda la masa del vehículo. No se obtiene fuerza de
choque multiplicando esa masa ni se infieren lesiones de la aceleración de carrocería.
La marca de daño es una observación del sondeo de telemetría, no el instante exacto
del contacto. El video y el tiempo de simulación tienen relojes distintos; el recibo
actual no certifica sincronización a nivel de fotograma.

Prueba viva: dos vehículos por escena, 200 Hz sin huecos, calibración en reposo y
dos choques programados sin VR. La captura visual requiere revisión: un video
codificado correctamente puede contener una ventana minimizada o una imagen vacía.

Fuentes: [Advanced IMU](https://www.docs.beamng.com/beamng_tech/sensors/advanced-imu/),
[BeamNGpy](https://github.com/BeamNG/BeamNGpy/blob/master/src/beamngpy/sensors/advanced_IMU.py).
