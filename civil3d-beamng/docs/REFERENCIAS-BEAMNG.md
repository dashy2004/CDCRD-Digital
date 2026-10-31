# APIs y repositorios de referencia para BeamNG

Consulta: 2026-10-31. Las fuentes son de BeamNG o de los mantenedores originales.
Esta recopilación enlaza sus recursos; no incorpora su código al repositorio.

## Qué usar para la escena de la calle

| Necesidad | Fuente original | Uso previsto en CDCRD |
|---|---|---|
| Objetos, terreno y herramientas del editor | [World Editor API](https://documentation.beamng.com/world_editor/api_reference/) y [crear una extensión](https://documentation.beamng.com/world_editor/api_reference/create_editor_tool/) | Primera opción para Drive. Ampliar nuestro importador Lua, comprobando las llamadas en la versión instalada. |
| Organizar módulos y eventos Lua | [Extensions](https://documentation.beamng.com/modding/programming/extensions/) y [Virtual Machines](https://documentation.beamng.com/modding/programming/virtualmachines/) | Separar lógica de escena y lógica del vehículo; usar los mecanismos del motor. |
| Control externo de escenarios, vehículos y sensores con Python | [BeamNG/BeamNGpy](https://github.com/BeamNG/BeamNGpy) | Dependencia oficial para **BeamNG.tech**. No escribir otro cliente equivalente ni prometer compatibilidad con Drive. |
| Cámaras para el anuncio | [Path Camera](https://documentation.beamng.com/tutorials/camera/path_cam/) | Preparar trayectorias y tiempos de cámara propios; usar el sistema existente. |
| Repetir una pasada del vehículo | [Replay](https://documentation.beamng.com/getting_started/replay/) | Guardar la simulación en RPL y elegir tomas; RPL no es un archivo de video. |
| Automatizar la grabación de video | [obsproject/obs-websocket](https://github.com/obsproject/obs-websocket) | Integración opcional con OBS. Es un proyecto externo, no una API de BeamNG. |
| Telemetría mediante protocolos | [Protocols](https://documentation.beamng.com/modding/protocols/) | Consultar los formatos existentes antes de definir uno propio; no asumir que sustituyen el control de escenarios. |
| Integración de robótica o sensores ROS 2 | [BeamNG/beamng-ros2-integration](https://github.com/BeamNG/beamng-ros2-integration) | Referencia opcional para Tech; no necesaria para la primera escena publicitaria. |

La API del World Editor está organizada en Lua. La documentación oficial remite
también a los archivos API de la instalación para completar firmas y detalles.
Consultar esos archivos localmente no implica redistribuirlos. [Fuente](https://documentation.beamng.com/world_editor/api_reference/).

BeamNGpy declara BeamNG.tech como requisito. La tabla consultada relaciona Tech
0.39 con BeamNGpy 1.36; esa relación **no certifica Drive 0.40.4**. Verificar la
[tabla oficial de compatibilidad](https://github.com/BeamNG/BeamNGpy/blob/master/COMPATIBILITY.md)
al integrar una versión. Este módulo conserva Drive como destino y no añade
BeamNGpy a las dependencias del conversor. El entorno opcional de
[herramientas Tech](../tools/tech/README.md) instala el SDK por separado.

## Licencias y atribución

| Recurso | Autor / mantenedor | Licencia del código consultada | Tratamiento actual |
|---|---|---|---|
| BeamNGpy | BeamNG GmbH | [MIT](https://github.com/BeamNG/BeamNGpy/blob/master/LICENSE.txt) | Referencia; si se integra Tech, instalar como dependencia externa y fijar versión compatible. |
| BeamNG ROS 2 | BeamNG GmbH | [MIT](https://github.com/BeamNG/beamng-ros2-integration/blob/main/LICENSE.txt) | Referencia, sin copiar sus paquetes. |
| obs-websocket | OBS Project y colaboradores | [GPL-2.0, según el repositorio](https://github.com/obsproject/obs-websocket/blob/master/LICENSE) | Referencia a su API; sin importar su implementación. |
| obsws-python | aatikturk y colaboradores | [GPL-3.0-only](https://github.com/aatikturk/obsws-python/blob/main/LICENSE) | Cliente Python externo para OBS, instalado como dependencia opcional; no se copia su código. |
| Motor, Lua instalado y recursos del juego | BeamNG GmbH y autores de cada recurso | No se asigna la licencia MIT de BeamNGpy al juego | No incluir código del motor, vehículos, mapas ni texturas originales en este repositorio. |

Enlazar reconoce la fuente; si más adelante se incorpora código ajeno, se deberá
registrar archivo, autor, versión/commit, licencia y modificaciones, y conservar
los avisos exigidos por esa licencia. Un enlace no sustituye esos avisos.
Las licencias de los repositorios y las condiciones de uso del simulador son
cuestiones distintas.

## Código propio que sí corresponde desarrollar

El trabajo específico de CDCRD está en la geometría e interoperabilidad:

- Leer la TIN de Civil 3D con unidades, fronteras y procedencia.
- Convertir esa geometría en el paquete de intercambio y validar sus hashes.
- Importar el paquete con nuestro [adaptador Lua](../beamng/lua/ge/extensions/editor/cdcrdCivilImport.lua).
- Coordinar una demostración de calle/bache con parámetros, recibos y comprobaciones.
- Conectar cámaras, replay o grabación a las APIs originales cuando se verifiquen
  sus firmas y comportamiento en la versión instalada.

El importador actual usa objetos del motor como TerrainBlock, TSStatic y SimGroup,
y guarda a través del editor. Son llamadas a la instalación de BeamNG, no una
implementación del motor incluida en CDCRD.

Primero se comprobará la carga, guardado, recarga y colisión de la nueva calle en
Drive. La automatización de vehículo, replay y cámara queda pendiente de esa
comprobación. La consulta de documentación no acredita una prueba dentro del motor.
