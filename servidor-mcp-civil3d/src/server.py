"""Servidor MCP de Civil 3D 2027 para CDCRD-Digital.

Arquitectura (igual criterio que servidor-mcp de ETABS, distinta via):
    cliente MCP  --stdio-->  este servidor (Python)
                 --TCP JSON-RPC 127.0.0.1:8760-->  puente .NET 10 dentro de Civil 3D

El puente lee y escribe los objetos de Civil 3D por reflexion, de modo que la
cobertura no depende de una lista fija de clases: lo que exponga la version
instalada se puede consultar. Toda escritura exige token de un solo uso ligado
a los parametros exactos, que este servidor pide en la misma llamada.
"""

import json
import logging
import os
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),   # stdout esta reservado al protocolo MCP
        logging.FileHandler(os.path.join(SRC_DIR, 'civil3d_mcp.log'), encoding='utf-8'),
    ])
logger = logging.getLogger('civil3d_mcp')
logger.info('Iniciando servidor MCP de Civil 3D')

from mcp.server.fastmcp import FastMCP            # noqa: E402
import puente_cliente as puente                   # noqa: E402
import dibujo                                      # noqa: E402
import sitio
import plataformas
import creacion                                    # noqa: E402
import vistas                                      # noqa: E402
import perfil_estratigrafico                       # noqa: E402
import tridimensional                              # noqa: E402
import gm                                         # noqa: E402
import aplanar                                    # noqa: E402
import puntos                                     # noqa: E402

with open(os.path.join(SRC_DIR, 'config.json'), encoding='utf-8') as fh:
    CONFIG = json.load(fh)

LIMITE = int(CONFIG.get('limite_objetos_por_consulta', 100))

mcp = FastMCP(CONFIG.get('serverName', 'civil3d'))


def _ok(resultado):
    return json.dumps(resultado, ensure_ascii=False, indent=2, default=str)


def _error(exc):
    if isinstance(exc, puente.PuenteError):
        result = {'error': exc.mensaje, 'codigo': exc.codigo}
        if exc.datos is not None:
            result['datos'] = exc.datos
        return _ok(result)
    logger.exception('fallo no esperado')
    return _ok({'error': f'{type(exc).__name__}: {exc}'})


def _llamar(metodo, parametros=None, escribe=False):
    try:
        if escribe:
            return _ok(puente.llamar_con_aprobacion(metodo, parametros or {}))
        return _ok(puente.llamar(metodo, parametros))
    except Exception as exc:                        # noqa: BLE001
        return _error(exc)


@mcp.resource('config://civil3d')
def configuracion() -> str:
    """Configuracion activa del servidor MCP de Civil 3D."""
    return json.dumps(CONFIG, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Estado y descubrimiento
# --------------------------------------------------------------------------

@mcp.tool()
def estado_puente() -> str:
    """Comprueba si el puente dentro de Civil 3D responde y con que permisos.

    Primera llamada obligatoria de cualquier sesion: dice puerto, version,
    si la escritura esta habilitada y donde esta el log del puente.
    """
    return _llamar('ping')


@mcp.tool()
def info_dibujo() -> str:
    """Datos del dibujo activo: ruta, unidades, version y si hay CivilDocument.

    Si 'civil3d' viene en false, el dibujo esta abierto en AutoCAD puro o la
    API de Civil 3D no cargo: ninguna coleccion de Civil 3D estara disponible.
    """
    return _llamar('doc.info')


@mcp.tool()
def listar_colecciones() -> str:
    """Lista las colecciones de Civil 3D que existen en ESTA version, con su conteo.

    Devuelve los miembros del CivilDocument (GetAlignmentIds, GetSurfaceIds,
    GetCorridorIds, GetPipeNetworkIds, GetViewFrameGroupIds, ...) y los alias en
    espanol aceptados por las demas herramientas. Uselo antes de asumir que una
    coleccion existe: la lista sale del binario instalado, no de documentacion.
    """
    return _llamar('civil.colecciones')


@mcp.tool()
def descubrir_tipos(coleccion: str = '', limite_tipos: int = 60) -> str:
    """Cuenta los objetos del dibujo agrupados por tipo .NET y clase RX.

    coleccion: vacio = espacio modelo completo; o un alias/miembro de
    listar_colecciones para contar solo esa familia de objetos.
    """
    parametros = {}
    if coleccion:
        parametros['coleccion'] = coleccion
    respuesta = _llamar('types.discover', parametros)
    try:
        datos = json.loads(respuesta)
        if isinstance(datos, dict) and 'tipos' in datos:
            datos['tipos'] = datos['tipos'][:max(1, limite_tipos)]
            return _ok(datos)
    except json.JSONDecodeError:
        pass
    return respuesta


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------

@mcp.tool()
def consultar_objetos(coleccion: str = '', tipo: str = '', capa: str = '',
                      props: str = '', handles: str = '',
                      limite: int = 0, salto: int = 0) -> str:
    """Consulta objetos y sus propiedades.

    coleccion: alias o miembro del CivilDocument (alineamientos, superficies,
      corredores, redes_gravedad, redes_presion, puntos, grupos_view_frame...).
      Vacio = espacio modelo.
    tipo: subcadena del nombre de tipo .NET para filtrar (p. ej. 'Alignment').
    capa: nombre exacto de capa (solo aplica a entidades de dibujo).
    props: lista separada por comas de propiedades a leer; '*' trae todas las
      propiedades simples. Sin esto se devuelve handle, tipo, capa, nombre y
      descripcion.
    handles: lista separada por comas de handles concretos, ignora coleccion.
    """
    parametros = {'limite': limite or LIMITE, 'salto': salto}
    if coleccion:
        parametros['coleccion'] = coleccion
    if tipo:
        parametros['tipo'] = tipo
    if capa:
        parametros['capa'] = capa
    if props:
        parametros['props'] = [p.strip() for p in props.split(',') if p.strip()]
    if handles:
        parametros['handles'] = [h.strip() for h in handles.split(',') if h.strip()]
    return _llamar('objects.query', parametros)


@mcp.tool()
def agregar_objetos(prop: str, op: str = 'suma', coleccion: str = '', tipo: str = '') -> str:
    """Estadistica sobre una propiedad numerica: conteo, suma, min, max o promedio.

    Ejemplos: longitud total de alineamientos (coleccion='alineamientos',
    prop='Length', op='suma'); area de superficies; conteo de puntos COGO.
    """
    parametros = {'prop': prop, 'op': op}
    if coleccion:
        parametros['coleccion'] = coleccion
    if tipo:
        parametros['tipo'] = tipo
    return _llamar('objects.aggregate', parametros)


@mcp.tool()
def inspeccionar_objeto(handle: str, ruta: str = '', valores: bool = False,
                        patron: str = '', solo_escribibles: bool = False,
                        incluir: str = '') -> str:
    """Lista propiedades y metodos reales de un objeto, con firma y si son de lectura.

    Es el paso previo a invocar_metodo o actualizar_objeto: la firma sale del
    ensamblado instalado, no de suposiciones sobre la API.

    ruta: para inspeccionar un objeto anidado que no tiene handle propio, p. ej.
      'Analysis' en una superficie, o 'GetGeneralProperties()'. Cada tramo es una
      propiedad o un metodo sin argumentos, con indices opcionales:
      'Analysis.ElevationRanges[0]'.
    valores: ademas de la firma, trae el valor actual de cada propiedad legible.
    patron: regex sobre el nombre del miembro (p. ej. 'Station|Elev') para no
      recibir las decenas de KB de un ProfileView completo.
    solo_escribibles: solo propiedades con escritura (y sin metodos).
    incluir: 'props', 'metodos' o vacio/'ambos'.
    """
    parametros = {'handle': handle}
    if ruta:
        parametros['ruta'] = ruta
    if valores:
        parametros['valores'] = True
    if patron:
        parametros['patron'] = patron
    if solo_escribibles:
        parametros['solo_escribibles'] = True
    if incluir:
        parametros['incluir'] = incluir
    return _llamar('objects.props', parametros)


@mcp.tool()
def leer_ruta(ruta: str, handle: str = '', profundidad: int = 1) -> str:
    """Lee el valor que hay al final de una ruta de propiedades anidadas.

    Es la via para lo que no es un DBObject con handle: el analisis de una
    superficie, las propiedades generales, los rangos de elevacion. Sin handle
    la raiz es el CivilDocument.

    ruta: 'Analysis', 'Analysis.ElevationRanges[2].MaximumElevation',
      'GetGeneralProperties()', y ademas metodos con argumentos y claves por
      nombre: 'GetDisplayStyleProfile(Line).Color',
      'Styles.ProfileStyles["GEO - TERRENO"].Name'.
    profundidad: 0 deja los objetos compuestos como {tipo, texto}; 1 a 3 los
      expande propiedad por propiedad. Suba solo si hace falta: expande rapido.
    """
    parametros = {'ruta': ruta, 'profundidad': profundidad}
    if handle:
        parametros['handle'] = handle
    return _llamar('objects.read', parametros)


@mcp.tool()
def invocar_metodo(metodo: str, handle: str = '', args: str = '', ruta: str = '',
                   profundidad: int = 0, confirmar: bool = False) -> str:
    """Invoca un metodo del objeto (o del CivilDocument si no se da handle).

    Los metodos de lectura (Get*, Find*, Sample*, Station*, Compute*, Is*, Has*)
    corren directo. Cualquier otro metodo modifica el modelo y exige
    confirmar=True, que es lo que dispara el token de aprobacion.

    args: valores separados por ';'. Un punto ([x;y;z] como '1,2,3') se escribe
    entre corchetes: args='[100.5,200.0,0]'.
    ruta: invoca el metodo sobre un objeto anidado en vez de sobre el objeto del
      handle, p. ej. ruta='Analysis' y metodo='CreateElevationData' en una
      superficie. Vea inspeccionar_objeto(handle, ruta=...) para la firma.
    profundidad: expande el objeto devuelto (0 a 3).
    """
    parametros = {'metodo': metodo}
    if handle:
        parametros['handle'] = handle
    if ruta:
        parametros['ruta'] = ruta
    if profundidad:
        parametros['profundidad'] = profundidad
    if args:
        valores = []
        for crudo in args.split(';'):
            crudo = crudo.strip()
            if not crudo:
                continue
            if crudo.startswith('[') and crudo.endswith(']'):
                valores.append([float(x) for x in crudo[1:-1].split(',') if x.strip()])
                continue
            try:
                valores.append(float(crudo) if ('.' in crudo or 'e' in crudo.lower()) else int(crudo))
            except ValueError:
                if crudo.lower() in ('true', 'false'):
                    valores.append(crudo.lower() == 'true')
                else:
                    valores.append(crudo)
        parametros['args'] = valores
    # Misma lista que ReadOnlyMethodPatterns en puente/Handlers.cs
    lectura = any(metodo.startswith(p) for p in ('Get', 'Find', 'Sample', 'Station', 'PointLocation', 'Compute',
                                                 'Is', 'Has', 'Count', 'ElevationAt', 'PointAt', 'DistanceTo',
                                                 'Contains', 'Offset'))
    if lectura:
        return _llamar('objects.invoke', parametros)
    if not confirmar:
        return _ok({'error': 'metodo de escritura: repita con confirmar=True',
                    'metodo': metodo, 'handle': handle or 'CivilDocument'})
    return _llamar('objects.invoke', parametros, escribe=True)


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------

@mcp.tool()
def actualizar_objeto(handle: str, cambios: str, ruta: str = '', confirmar: bool = False) -> str:
    """Cambia propiedades de un objeto. Exige confirmar=True.

    cambios: JSON con pares propiedad/valor, p. ej.
      {"Name": "ALIN-1", "Description": "eje revisado"}
    ruta: aplica los cambios sobre un objeto anidado en vez de sobre el objeto
      del handle. Si ese objeto es un tipo por valor (struct) la escritura se
      rechaza, porque no afectaria al dibujo: ahi va el metodo Set... del padre.
    La respuesta trae el valor antes y despues de cada propiedad aplicada y el
    motivo de cada una que fallo.
    """
    try:
        props = json.loads(cambios)
    except json.JSONDecodeError as exc:
        return _ok({'error': f'cambios no es JSON valido: {exc}'})
    if not isinstance(props, dict) or not props:
        return _ok({'error': 'cambios debe ser un objeto JSON con al menos una propiedad'})
    if not confirmar:
        return _ok({'error': 'operacion de escritura: repita con confirmar=True',
                    'handle': handle, 'ruta': ruta, 'cambios': props})
    parametros = {'handle': handle, 'props': props}
    if ruta:
        parametros['ruta'] = ruta
    return _llamar('objects.update', parametros, escribe=True)


@mcp.tool()
def ejecutar_comando(linea: str, confirmar: bool = False) -> str:
    """Encola una linea de comandos de Civil 3D. Apagado por defecto.

    Requiere CDCRD_C3D_PERMITIR_COMANDOS=1 en el entorno de Civil 3D y
    confirmar=True. Es ASINCRONO: el comando corre despues de esta respuesta,
    asi que el efecto se verifica con una consulta posterior. No sirve para
    comandos que abren dialogos modales: dejan el puente sin respuesta hasta
    que alguien los cierra.
    """
    if not confirmar:
        return _ok({'error': 'operacion de escritura: repita con confirmar=True', 'linea': linea})
    return _llamar('cmd.run', {'linea': linea}, escribe=True)


# --------------------------------------------------------------------------
# Dibujo robusto por .lsp temporal (sin limite de ~256 car. ni problema de 'n~')
# --------------------------------------------------------------------------

def _cargar_lisp(codigo: str):
    """Escribe el codigo en un .lsp temporal local y lo carga con (load ...).

    Supone CDCRD_C3D_PERMITIR_COMANDOS=1 en Civil 3D, igual que ejecutar_comando.
    El efecto es ASINCRONO: se verifica con una consulta posterior.
    """
    ruta = dibujo.escribir_lisp_temporal(codigo)
    resultado = puente.llamar_con_aprobacion('cmd.run', {'linea': dibujo.ruta_load(ruta)})
    return {'cargado': ruta, 'resultado': resultado}


@mcp.tool()
def ejecutar_lisp(codigo: str, confirmar: bool = False) -> str:
    """Ejecuta codigo AutoLISP de cualquier longitud por un .lsp temporal.

    En vez de enviar el codigo por la linea de comandos (que corta alrededor de
    256 caracteres y rompe los acentos y la 'n~'), el servidor lo escribe en un
    .lsp temporal local en ANSI y lo carga con (load ...). Requiere
    CDCRD_C3D_PERMITIR_COMANDOS=1 en Civil 3D y confirmar=True. Es ASINCRONO:
    verifique el efecto con una consulta posterior. No sirve para codigo que
    abra dialogos modales (dejan el puente colgado hasta cerrarlos).
    """
    if not codigo or not codigo.strip():
        return _ok({'error': 'codigo LISP vacio'})
    if not confirmar:
        return _ok({'error': 'operacion de escritura: repita con confirmar=True',
                    'caracteres': len(codigo)})
    try:
        return _ok(_cargar_lisp(codigo))
    except OSError as exc:
        return _ok({'error': f'no se pudo escribir el .lsp temporal: {exc}'})
    except Exception as exc:                        # noqa: BLE001
        return _error(exc)


@mcp.tool()
def crear_entidades(entidades: str, confirmar: bool = False) -> str:
    """Crea entidades de dibujo desde una descripcion JSON (sin escribir LISP a mano).

    entidades: lista JSON de objetos; cada uno con 'tipo' y sus campos:
      - capa:      {"tipo":"capa","nombre":"UBIC-LOTE","color":1}
      - linea:     {"tipo":"linea","capa":"0","p1":[x,y],"p2":[x,y]}
      - polilinea: {"tipo":"polilinea","capa":"0","puntos":[[x,y],...],"cerrada":true,"ancho":0.5}
      - texto:     {"tipo":"texto","capa":"0","punto":[x,y],"altura":2.5,"texto":"N","centrado":true}
      - circulo:   {"tipo":"circulo","capa":"0","centro":[x,y],"radio":10}
      - solido:    {"tipo":"solido","capa":"0","p1":[x,y],"p2":[x,y],"p3":[x,y],"p4":[x,y]}
      - punto:     {"tipo":"punto","capa":"0","punto":[x,y,z]}
    Incluya las capas que use antes que las entidades en la misma lista. Exige
    confirmar=True; sin el devuelve el conteo y un adelanto del LISP. El efecto
    es ASINCRONO: verifique con una consulta posterior.
    """
    try:
        datos = json.loads(entidades)
    except json.JSONDecodeError as exc:
        return _ok({'error': f'entidades no es JSON valido: {exc}'})
    try:
        codigo = dibujo.lisp_para_entidades(datos)
    except (ValueError, TypeError) as exc:
        return _ok({'error': f'entidad invalida: {exc}'})
    if not confirmar:
        n = len(datos) if isinstance(datos, list) else 1
        return _ok({'error': 'operacion de escritura: repita con confirmar=True',
                    'entidades': n, 'lisp_previo': codigo[:600]})
    try:
        return _ok(_cargar_lisp(codigo))
    except OSError as exc:
        return _ok({'error': f'no se pudo escribir el .lsp temporal: {exc}'})
    except Exception as exc:                        # noqa: BLE001
        return _error(exc)


# --------------------------------------------------------------------------
# Capas y guardado
# --------------------------------------------------------------------------

@mcp.tool()
def capas(nombre: str = '') -> str:
    """Lista las capas con su estado: apagada, congelada, bloqueada, color.

    Una capa apagada o congelada esconde el objeto completo por mas que su
    estilo este bien configurado. Revise esto antes de depurar un estilo.

    nombre: subcadena para filtrar (p. ej. 'C-TOPO'). Vacio = todas.
    """
    parametros = {}
    if nombre:
        parametros['nombre'] = nombre
    return _llamar('layers.query', parametros)


@mcp.tool()
def fijar_capas(nombres: str, apagada: str = '', congelada: str = '',
                bloqueada: str = '', confirmar: bool = False) -> str:
    """Enciende, apaga, congela, descongela, bloquea o desbloquea capas.

    nombres: nombres exactos separados por coma.
    apagada / congelada / bloqueada: 'true' o 'false'; vacio deja el estado como
      esta. Para volver visible una capa: apagada='false', congelada='false'.
    """
    lista = [n.strip() for n in nombres.split(',') if n.strip()]
    if not lista:
        return _ok({'error': 'indique al menos un nombre de capa'})
    parametros = {'nombres': lista}
    for clave, crudo in (('apagada', apagada), ('congelada', congelada), ('bloqueada', bloqueada)):
        if crudo != '':
            if crudo.strip().lower() not in ('true', 'false'):
                return _ok({'error': f"{clave} debe ser 'true' o 'false'", 'recibido': crudo})
            parametros[clave] = crudo.strip().lower() == 'true'
    if len(parametros) == 1:
        return _ok({'error': 'indique al menos apagada, congelada o bloqueada'})
    if not confirmar:
        return _ok({'error': 'operacion de escritura: repita con confirmar=True',
                    'cambios': parametros})
    return _llamar('layers.set', parametros, escribe=True)


@mcp.tool()
def guardar_dibujo(ruta: str = '', confirmar: bool = False) -> str:
    """Guarda el dibujo activo. Sin ruta guarda sobre el archivo actual.

    Va por Database.SaveAs. Si la version instalada lo rechaza para el dibujo
    activo, la alternativa es ejecutar_comando('QSAVE') con los comandos
    habilitados.
    """
    if not confirmar:
        return _ok({'error': 'operacion de escritura: repita con confirmar=True',
                    'ruta': ruta or '<archivo actual>'})
    parametros = {}
    if ruta:
        parametros['ruta'] = ruta
    return _llamar('doc.save', parametros, escribe=True)


# --------------------------------------------------------------------------
# Vista
# --------------------------------------------------------------------------

@mcp.tool()
def seleccionar(handles: str = '', coleccion: str = '') -> str:
    """Deja seleccionados en Civil 3D los objetos indicados (seleccion implicita)."""
    parametros = {}
    if handles:
        parametros['handles'] = [h.strip() for h in handles.split(',') if h.strip()]
    if coleccion:
        parametros['coleccion'] = coleccion
    return _llamar('selection.set', parametros)


@mcp.tool()
def zoom(handles: str = '', coleccion: str = '', extension: bool = False, margen: float = 0.10) -> str:
    """Encuadra la vista en los objetos indicados, o en toda la extension del dibujo."""
    parametros = {'margen': margen}
    if extension:
        parametros['extension'] = True
    if handles:
        parametros['handles'] = [h.strip() for h in handles.split(',') if h.strip()]
    if coleccion:
        parametros['coleccion'] = coleccion
    return _llamar('view.zoom', parametros)


# --------------------------------------------------------------------------
# Atajos por area de trabajo (azucar sobre consultar_objetos)
# --------------------------------------------------------------------------

_ATAJOS = {
    'alineamientos': ('alineamientos', 'Name,Length,StartingStation,EndingStation,StyleName,ReferencePointStation'),
    'superficies': ('superficies', 'Name,SurfaceType,StyleName'),
    'corredores': ('corredores', 'Name,Description,StyleName'),
    'redes_gravedad': ('redes_gravedad', 'Name,Description'),
    'redes_presion': ('redes_presion', 'Name,Description'),
    'puntos': ('puntos', 'PointNumber,Easting,Northing,Elevation,RawDescription,FullDescription'),
    'grupos_view_frame': ('grupos_view_frame', 'Name,Description'),
    'vistas_perfil': ('vistas_perfil', 'Name,StyleName'),
}


@mcp.tool()
def listar(area: str, limite: int = 0) -> str:
    """Listado rapido por area: alineamientos, superficies, corredores,
    redes_gravedad, redes_presion, puntos, grupos_view_frame, vistas_perfil.

    Es consultar_objetos con un juego de propiedades razonable por area. Si una
    propiedad no existe en esta version vuelve en null, sin romper la consulta.
    """
    if area not in _ATAJOS:
        return _ok({'error': 'area desconocida', 'areas': sorted(_ATAJOS)})
    coleccion, props = _ATAJOS[area]
    return consultar_objetos(coleccion=coleccion, props=props, limite=limite or LIMITE)


creacion.registrar(mcp, _llamar, _ok)
sitio.registrar(mcp, _llamar, _ok)
plataformas.registrar(mcp, _llamar, _ok)
vistas.registrar(mcp, _llamar, _ok)
tridimensional.registrar(mcp, _llamar, _ok)
gm.registrar(mcp, _llamar, _ok)
import comandos
comandos.registrar(mcp, _llamar, _ok)
aplanar.registrar(mcp, _llamar, _ok)
puntos.registrar(mcp, _llamar, _ok)


@mcp.tool()
def generar_perfil_estratigrafico(spec: str) -> str:
    """Genera un perfil estratigrafico completo de un corte, 100% nativo y repetible.

    spec: JSON con alineamiento, superficie_terreno, lista de estratos
    (cada uno: codigo, nombre, superficie, color_aci|color_rgb), sondeos,
    origen [x,y], y opcionalmente db_sondeos o csv_ubicaciones/csv_estratigrafia,
    elev_min/elev_max (se calculan si faltan), fondo, prefijo, mostrar
    {spt, nivel_freatico, leyenda, columnas} y exportar {pdf, png, papel}.
    Crea perfiles de estrato, vista de perfil, estilos de forma por estrato
    (color), rellenos nativos (hatch), columnas de sondeo con SPT y nivel
    freatico y leyenda; exporta sin dialogos. Todo con el prefijo indicado,
    idempotente. Datos geotecnicos hipoteticos/preliminares.
    """
    try:
        datos = json.loads(spec)
    except json.JSONDecodeError as exc:
        return _ok({'error': f'spec no es JSON valido: {exc}'})
    import puente_cliente as _p
    mensajes = []
    try:
        res = perfil_estratigrafico.generar(datos, _p, log=lambda m: mensajes.append(str(m)))
        res['log'] = mensajes
        return _ok(res)
    except Exception as exc:                        # noqa: BLE001
        logger.exception('generar_perfil_estratigrafico fallo')
        return _ok({'error': f'{type(exc).__name__}: {exc}', 'log': mensajes})


# Calculo hidraulico local; no llama al puente ni accede a CAD.
from pydantic import StrictFloat, StrictStr
from hidraulica import calculate


@mcp.tool()
def calcular_seccion_si(units: StrictStr, q_m3_s: StrictFloat, b_m: StrictFloat, z_h_v: StrictFloat,
                       n_s_m13: StrictFloat, slope_m_m: StrictFloat, bed_m: StrictFloat,
                       available_head_m: StrictFloat | None, losses_m: StrictFloat) -> dict:
    """Normal/critical trapezoidal flow in SI, local energy gate; never certifies a route.

    n_s_m13 is Manning n in s/m^(1/3); z_h_v is horizontal/vertical bank slope.
    available_head_m must be measured TOTAL head on the same datum as bed_m,
    or null when unknown. losses_m is an explicit assumed/verified input.
    Requires all inputs; units must be SI. No CAD or HCanales access.
    """
    return calculate(dict(units=units, q_m3_s=q_m3_s, b_m=b_m, z_h_v=z_h_v,
                          n_s_m13=n_s_m13, slope_m_m=slope_m_m, bed_m=bed_m,
                          available_head_m=available_head_m, losses_m=losses_m))


if __name__ == '__main__':
    logger.info('Herramientas registradas; esperando al cliente MCP por stdio')
    try:
        mcp.run()
    except KeyboardInterrupt:
        # Ctrl+C en una prueba manual: salida limpia, sin traza de anyio
        logger.info('Interrumpido por el operador; servidor detenido')
