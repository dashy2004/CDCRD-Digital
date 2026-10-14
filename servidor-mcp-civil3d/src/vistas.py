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
                       estilo_plot: str = '', sombreado: str = '', margen: str = '',
                       confirmar: bool = False) -> str:
        """Exporta el modelo a PDF/PNG/DWF por PlotEngine, SINCRONO y sin dialogos.

        Area a plotear, en orden de prioridad: nombre_vista (vista guardada;
        unica via correcta para vistas 3D), ventana 'x1,y1,x2,y2' (coordenadas
        del modelo), handles (extension de esos objetos + margen), o la extension
        completa. papel acepta el nombre canonico, el visible o un pedazo
        ('A3', 'ISO full bleed A3'); vacio = el del dispositivo por defecto.
        sombreado: Wireframe|HiddenLine|Rendered|AsDisplayed (vistas 3D).
        La respuesta vuelve cuando el archivo existe, con su tamano en bytes.
        """
        try:
            parametros = area(sin_vacios(dict(ruta=ruta, dispositivo=dispositivo, papel=papel,
                                              nombre_vista=nombre_vista, estilo_plot=estilo_plot,
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

    return mcp
