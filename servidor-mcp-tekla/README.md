# Tekla MCP

Servidor MCP para Tekla Structures. Permite a un agente crear y consultar un modelo físico
(ejes, vigas, columnas, placas, tornillos, soldaduras), generar informes y capturar la pantalla
para documentar guías y memorias.

Probado en Tekla Structures 2026 SP5 (licencia Educational), Windows 11, Python 3.14.

## Cómo funciona

```
agente ──MCP──> src/server.py ──JSON por stdin──> puente/TeklaPuente.exe ──Open API──> Tekla abierto
```

Tekla Open API es .NET Framework, así que el servidor no la carga desde Python: llama a un
ejecutable de consola que recibe un comando JSON y devuelve una respuesta JSON. Tekla debe estar
abierto con un modelo cargado; Open API no arranca el programa.

## Instalación

```powershell
pip install -r requirements.txt
.\puente\compilar.ps1            # usa csc de .NET Framework 4 y la instalación local de Tekla
```

`compilar.ps1` copia `TeklaStructures.exe.config` junto al ejecutable para que resuelva los
ensamblados de Tekla. El `.exe` no se versiona: se compila en cada máquina.

Registro en el cliente MCP:

```json
{ "mcpServers": { "tekla": { "command": "python", "args": ["<repo>\\servidor-mcp-tekla\\src\\server.py"] } } }
```

## Carpetas donde se permite escribir

Las herramientas que modifican el modelo comprueban antes que el modelo abierto esté dentro de una
carpeta permitida. Por defecto solo `%TEMP%\tekla-mcp-pruebas`. Para trabajar en otra carpeta:

- `src/config.json` → `tekla.rutas_permitidas`, o
- variable de entorno `TEKLA_MCP_RUTAS` (rutas separadas por `;`).

Las lecturas (`tekla_estado`, `tekla_listar_piezas`, selección, vista, captura) funcionan sobre
cualquier modelo.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `tekla_estado` | Modelo abierto, ruta, versión y número de piezas |
| `tekla_crear_modelo` | Modelo monousuario nuevo; `aceptar_licencia_educativa` responde al aviso de guardado |
| `tekla_abrir_modelo` · `tekla_guardar` | Abrir y guardar |
| `tekla_copiar_catalogos` | Copia `profdb.bin`, `matdb.bin`, `screwdb.db`, `assdb.db` al modelo y lo reabre |
| `tekla_definir_ejes` | Crea o modifica la cuadrícula rectangular |
| `tekla_crear_piezas` | Vigas y columnas en lote |
| `tekla_crear_placa` | Placa de contorno |
| `tekla_crear_tornillos` | Grupo de tornillos en matriz entre dos piezas; devuelve las posiciones |
| `tekla_crear_soldadura` | Filete entre dos piezas |
| `tekla_listar_piezas` | Piezas con caja del sólido, longitud y peso; tornillos y soldaduras con id |
| `tekla_borrar` | Borra objetos por id |
| `tekla_seleccionar` · `tekla_ajustar_vista` | Selección y área de trabajo/zoom de las vistas |
| `tekla_crear_informe` | Informe de los objetos indicados con una plantilla del entorno |
| `capturar_ventana` | PNG de la ventana de Tekla (o de ETABS, SAFE…), completa o por región |
| `tekla_dialogos` · `tekla_responder_dialogo` | Lista y responde diálogos que bloquean a Open API |

Unidades: milímetros y kilogramos. Los puntos son `[x, y, z]` en coordenadas globales.

## Lo que hay que saber

- **Un diálogo modal deja a Open API esperando.** Si una herramienta no responde en 120 s, el error
  incluye el texto y los botones del diálogo abierto. Con licencia educativa, Tekla pregunta antes
  de guardar un modelo nuevo.
- **Un modelo nuevo puede no tener catálogos.** Sin `screwdb.db` y `assdb.db` el grupo de tornillos
  se crea vacío; sin `profdb.bin` no existen los perfiles W. `tekla_copiar_catalogos` los trae de la
  carpeta `Catalogs` del entorno (por ejemplo `Imperial\General\Catalogs` para A325N).
- **Los ids cambian al reabrir el modelo.** Vuelva a listar antes de borrar o seleccionar.
- **Los perfiles se colocan por su línea de referencia.** El servidor no recorta ni despunta: una
  secundaria que llega al alma de otra viga queda con las alas superpuestas hasta que se modele el
  despunte.
- `tekla_abrir_modelo` descarta los cambios sin guardar del modelo actual.

## Pruebas

```powershell
pip install -r requirements-dev.txt
py -m pytest tests -q                       # unitarias, no necesitan Tekla
py tests\vivo\prueba_es16.py <Catalogs común> <Catalogs imperial>   # con Tekla abierto
```

La prueba viva reproduce una unión de alma (W16X26 a W21X44, placa A36 de ¼ in, tres tornillos
A325N de ⅝ in a 3 in, filete de 3/16 in), guarda, reabre y relee. Resultado del 26-11-2026: tres
piezas, un grupo con tres tornillos en Z = 139,85 · 63,65 · −12,55 mm, una soldadura de 4,76 mm.

## Pendiente

- Despuntes y cortes (`Fitting`, `CutPlane`, `BooleanPart`).
- Componentes del catálogo (placa de extremo, placa base) con `Connection`.
- Anclajes, placas plegadas y armado.
- Listado de normas y diámetros de tornillo disponibles en el modelo.
- Planos (`Tekla.Structures.Drawing`).
