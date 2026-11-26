# Tekla MCP

Servidor MCP para Tekla Structures. Permite a un agente crear y consultar un modelo físico
(ejes, vigas, columnas, placas, tornillos, soldaduras, despuntes y uniones del catálogo), numerar,
crear planos e informes y capturar la pantalla para documentar guías y memorias.

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

Los archivos que el servidor escribe (capturas, informes) también deben caer dentro de esas
carpetas; un informe con ruta relativa va a la carpeta del modelo.

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
| `tekla_ajustar_extremo` | Lleva el extremo de una pieza a un plano |
| `tekla_cortar_plano` | Corta una pieza por un plano (se elimina el lado de la normal) |
| `tekla_despuntar` | Despunte rectangular: resta una caja alineada con los ejes globales |
| `tekla_cortar_con_pieza` | Resta a una pieza el volumen de otra |
| `tekla_crear_componente` | Unión del catálogo entre una principal y sus secundarias (144, 146…) |
| `tekla_crear_detalle` | Detalle del catálogo sobre una pieza (1004 placa base con anclajes…) |
| `tekla_catalogo_componentes` | Busca componentes por título, nombre o número |
| `tekla_normas_tornillos` | Normas y diámetros de tornillo del catálogo del modelo |
| `tekla_numerar` | Numera el modelo (macro temporal en la carpeta del modelo) |
| `tekla_listar_planos` · `tekla_crear_plano` | Planos existentes; plano de pieza o de conjunto |
| `tekla_listar_piezas` | Piezas con caja del sólido, longitud, peso bruto y neto; tornillos, soldaduras y componentes con id |
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
- **Los perfiles se colocan por su línea de referencia.** Nada se recorta solo: una secundaria que
  llega al alma de otra viga queda con las alas superpuestas hasta que se ajusta el extremo y se
  despunta, o se inserta una unión del catálogo que lo haga.
- **`peso_kg` es el peso bruto** (no baja con un despunte); `peso_neto_kg` descuenta los cortes.
- **Open API no numera.** `tekla_numerar` escribe `mcp_numerar.cs` en la carpeta del modelo, lo lanza
  con `Operation.RunMacro` y lo borra. Sin numeración al día, `tekla_crear_plano` se niega.
- **Los componentes salen con el archivo de atributos `standard`.** Para otras medidas, pase
  `atributos` con los nombres internos de los campos del diálogo, o un archivo guardado desde Tekla.
- **Los anclajes** se crean con el detalle de placa base (1004 y similares), no como objeto aparte.
- `tekla_abrir_modelo` descarta los cambios sin guardar del modelo actual.

## Pruebas

```powershell
pip install -r requirements-dev.txt
py -m pytest tests -q --cov=src             # unitarias, no necesitan Tekla (58 pruebas, 98 %)
py tests\vivo\prueba_es16.py <Catalogs común> <Catalogs imperial>   # con Tekla abierto
py tests\vivo\prueba_cortes_y_componentes.py <carpeta con catálogos>
py tests\vivo\prueba_cliente_mcp.py        # arranca el servidor por stdio como un cliente MCP
```

Las pruebas vivas crean modelos propios en `%TEMP%\tekla-mcp-pruebas` y dejan abierto el último:
vuelva a abrir su modelo al terminar.

La prueba viva reproduce una unión de alma (W16X26 a W21X44, placa A36 de ¼ in, tres tornillos
A325N de ⅝ in a 3 in, filete de 3/16 in), guarda, reabre y relee. Resultado del 26-11-2026: tres
piezas, un grupo con tres tornillos en Z = 139,85 · 63,65 · −12,55 mm, una soldadura de 4,76 mm.

`prueba_cortes_y_componentes.py` (26-11-2026): el ajuste lleva el extremo de la secundaria a 13 mm
del alma; el despunte baja el peso neto de 118,95 a 118,00 kg; el corte por plano la deja en
y = 2500; la unión 146 genera una placa, un grupo de tornillos y una soldadura; el detalle 1004, la
placa base con sus anclajes y tres soldaduras; todo sobrevive a guardar y reabrir; tras numerar se
crean el plano de pieza y el de conjunto.

## Pendiente

- Leer y fijar por nombre legible los atributos de cada componente (hoy van por nombre interno).
- Planos generales (vistas), cotas y exportación a PDF.
- Placas plegadas y armado.
- Deshacer: un borrado o un corte no se revierten desde el servidor.
