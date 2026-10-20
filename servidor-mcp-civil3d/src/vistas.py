"""Herramientas MCP de exportacion y vistas (puente v0.3.0).

Exportar PDF/PNG/DWF sin dialogos (PlotEngine sincrono), vistas con nombre y
vistas 3D. Helpers puros arriba; registro abajo.
"""
import json

from creacion import parsear_num, parsear_punto, parsear_handles, sin_vacios


def parsear_ventana(crudo):
    """'x1,y1,x2,y2' o '[x1,y1,x2,y2]' -> [x1,y1,x2,y2]."""
    if crudo is None or crudo == '':
        return None
    if isinstance(crudo, (list, tuple)):
        partes = list(crudo)
    else:
        texto = str(crudo).strip()
        partes = json.loads(texto) if texto.startswith('[') else texto.split(',')
    if len(partes) != 4:
        raise ValueError('ventana debe ser [x1,y1,x2,y2]')
    return [float(x) for x in partes]


def parsear_direccion(crudo):
    """'SE'|'SW'|'NE'|'NW'|'PLANTA'|'FRENTE'|'DERECHA' o '[x,y,z]'."""
    if crudo is None or crudo == '':
        return None
    if isinstance(crudo, (list, tuple)) or str(crudo).strip().startswith('['):
        return parsear_punto(crudo, 'direccion')
    return str(crudo).strip()


def registrar(mcp, llamar, ok):
    """Registra las herramientas de vistas/exportacion en el servidor MCP."""

    def pendiente(**datos):
        return ok({'error': 'operacion de escritura: repita con confirmar=True', **datos})

    def area(parametros, ventana, handles):
        if ventana:
            parametros['ventana'] = parsear_ventana(ventana)
        if handles:
            parametros['handles'] = parsear_handles(handles)
        return parametros

    @mcp.tool()
    def listar_papeles(dispositivo: str = '') -> str:
        """Lista los dispositivos de ploteo y, dado uno, sus papeles (canonico+nombre).

        Ejemplos de dispositivo: 'DWG To PDF.pc3', 'PublishToWeb PNG.pc3',
        'DWF6 ePlot.pc3'. El nombre canonico es el que acepta exportar_vista.
        """
        return llamar('vista.papeles', sin_vacios(dict(dispositivo=dispositivo)))

    @mcp.tool()
    def exportar_vista(ruta: str, dispositivo: str = 'DWG To PDF.pc3', papel: str = '',
                       ventana: str = '', handles: str = '', nombre_vista: str = '',
                       layout: str = '', estilo_plot: str = '', sombreado: str = '',
                       margen: str = '', confirmar: bool = False) -> str:
        """Exporta el modelo a PDF/PNG/DWF por PlotEngine, SINCRONO y sin dialogos.

        Area a plotear, en orden de prioridad: layout (una presentacion, a 1:1),
        nombre_vista (vista guardada; unica via correcta para vistas 3D), ventana
        'x1,y1,x2,y2' (coordenadas
        del modelo), handles (extension de esos objetos + margen), o la extension
        completa. papel acepta el nombre canonico, el visible o un pedazo
        ('A3', 'ISO full bleed A3'); vacio = el del dispositivo por defecto.
        sombreado: Wireframe|HiddenLine|Rendered|AsDisplayed (vistas 3D).
        La respuesta vuelve cuando el archivo existe, con su tamano en bytes.
        """
        try:
            parametros = area(sin_vacios(dict(ruta=ruta, dispositivo=dispositivo, papel=papel,
                                              nombre_vista=nombre_vista, layout=layout,
                                              estilo_plot=estilo_plot,
                                              sombreado=sombreado,
                                              margen=parsear_num(margen, 'margen'))),
                              ventana, handles)
        except ValueError as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(**parametros)
        return llamar('vista.exportar', parametros, escribe=True)

    @mcp.tool()
    def vista_3d(direccion: str = 'SE', objetivo: str = '', ancho: str = '', alto: str = '',
                 handles: str = '', estilo_visual: str = '', confirmar: bool = False) -> str:
        """Pone la vista actual del modelo en 3D (isometrica u ortogonal).

        direccion: SE|SW|NE|NW|PLANTA|FRENTE|DERECHA o '[x,y,z]'. objetivo y
        ancho se deducen de handles (o de la extension del dibujo) si se omiten.
        estilo_visual: Conceptual, Realistic, Shaded, Wireframe, Hidden, X-Ray...
        Para exportarla: crear_vista_guardada + exportar_vista(nombre_vista=...).
        """
        try:
            parametros = area(sin_vacios(dict(direccion=parsear_direccion(direccion),
                                              estilo_visual=estilo_visual,
                                              ancho=parsear_num(ancho, 'ancho'),
                                              alto=parsear_num(alto, 'alto'))), '', handles)
            if objetivo:
                parametros['objetivo'] = parsear_punto(objetivo, 'objetivo')
        except ValueError as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(**parametros)
        return llamar('vista.3d', parametros, escribe=True)

    @mcp.tool()
    def crear_vista_guardada(nombre: str, direccion: str = '', objetivo: str = '',
                             ancho: str = '', alto: str = '', ventana: str = '',
                             handles: str = '', estilo_visual: str = '',
                             confirmar: bool = False) -> str:
        """Crea o reemplaza una vista con nombre (Named View).

        Sin parametros de geometria guarda la vista ACTUAL tal cual. Con
        direccion/objetivo/ancho (o ventana/handles) construye la vista igual
        que vista_3d. Es el paso previo para exportar una vista 3D o para
        volver a un encuadre exacto con activar_vista.
        """
        try:
            parametros = area(sin_vacios(dict(nombre=nombre,
                                              direccion=parsear_direccion(direccion),
                                              estilo_visual=estilo_visual,
                                              ancho=parsear_num(ancho, 'ancho'),
                                              alto=parsear_num(alto, 'alto'))), ventana, handles)
            if objetivo:
                parametros['objetivo'] = parsear_punto(objetivo, 'objetivo')
        except ValueError as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(**parametros)
        return llamar('vista.guardada', parametros, escribe=True)

    @mcp.tool()
    def activar_vista(nombre: str) -> str:
        """Restaura una vista guardada como vista actual del modelo."""
        return llamar('vista.activar', {'nombre': nombre})

    @mcp.tool()
    def crear_layout(nombre: str, viewports: str = '[]', textos: str = '[]', papel: str = 'A3',
                     dispositivo: str = 'DWG To PDF.pc3', rotacion: str = '',
                     confirmar: bool = False) -> str:
        """Crea (o reemplaza) una presentacion con papel, viewports y textos de rotulo.

        viewports: lista JSON [{"vista":"<vista guardada>","centro":[x,y] mm,
        "ancho":mm,"alto":mm,"escala":N (1:N, opcional; sin escala encuadra la
        vista),"bloquear":true}]. textos: [{"punto":[x,y],"texto":"...","altura":3.5}]
        en mm de papel. Luego exportar_vista(layout=nombre) la plotea a 1:1.
        """
        try:
            vps = json.loads(viewports or '[]')
            txs = json.loads(textos or '[]')
        except json.JSONDecodeError as exc:
            return ok({'error': f'viewports/textos no son JSON validos: {exc}'})
        parametros = sin_vacios(dict(nombre=nombre, papel=papel, dispositivo=dispositivo,
                                     rotacion=rotacion, viewports=vps, textos=txs))
        if not confirmar:
            return pendiente(**{k: v for k, v in parametros.items() if k != 'viewports'},
                             viewports=len(vps))
        return llamar('layout.crear', parametros, escribe=True)

    @mcp.tool()
    def estado_cola() -> str:
        """Estado de despachos activos y los ultimos 64 terminados/cancelados.

        Responde desde el socket, incluso durante un modal. Tras un timeout,
        busque request_id antes de reintentar. Para cmd.run, terminado solo
        acredita que AutoCAD recibio el comando, no que lo haya terminado.
        """
        return llamar('diag.cola', {})

    @mcp.tool()
    def leer_log_puente(n: int = 100) -> str:
        """Ultimas n lineas del log del puente (%LOCALAPPDATA%/CdcrdCivil3dBridge/puente.log).

        No depende de que Civil 3D este inactivo: sirve para ver que paso cuando
        una herramienta dio timeout o Civil 3D quedo en un dialogo.
        """
        return llamar('diag.log', {'n': n})

    @mcp.tool()
    def ping_comandos(timeout_ms: int = 3000) -> str:
        """Comprueba rapido si Civil 3D esta inactivo (sin dialogo modal ni comando).

        inactivo=false significa que cualquier herramienta de lectura/escritura
        se quedaria esperando: hay un dialogo modal, un comando activo o edicion
        en curso. Usela antes de operaciones largas y tras ejecutar_comando.
        """
        return llamar('diag.ping', {'timeout_ms': timeout_ms})

    @mcp.tool()
    def deshacer(veces: int = 1, confirmar: bool = False) -> str:
        """Encola _.U (deshacer) n veces en Civil 3D. Asincrono: verifique despues."""
        if not confirmar:
            return pendiente(veces=veces)
        return llamar('doc.undo', {'veces': veces}, escribe=True)

    return mcp
