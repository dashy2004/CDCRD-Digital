"""Feature lines y TIN de plataforma; no crea objetos Grading."""
import json
import math


def parsear_cotas(value):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError('elevaciones requiere 1-1000 numeros')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) for v in rows):
        raise ValueError('elevaciones requiere numeros finitos')
    return list(map(float, rows))


def registrar(mcp, llamar, ok):
    def run(method, params, confirmar):
        if not confirmar:
            return ok({'error': 'operacion de escritura: repita con confirmar=True', **params})
        return llamar(method, {k: v for k, v in params.items() if v != ''}, escribe=True)

    @mcp.tool()
    def crear_feature_line(polilinea: str, nombre: str, elevaciones: str,
                           estilo: str = '', capa: str = '', simular: bool = False,
                           confirmar: bool = False) -> str:
        """FeatureLine Civil sin sitio desde LWPOLYLINE XY recta; conserva fuente.

        elevaciones: JSON [cota_constante] o una cota por vertice, en su orden.
        Requiere unidades Civil e INSUNITS en metros; rechaza cruces y curvas.
        simular ejecuta y revierte en una transaccion.
        """
        try:
            values = parsear_cotas(elevaciones)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({'error': str(exc)})
        return run('civil.feature_line', dict(polilinea=polilinea, nombre=nombre,
                   elevaciones=values, estilo=estilo, capa=capa, simular=simular), confirmar)

    @mcp.tool()
    def crear_superficie_desde_feature_lines(contorno: str, nombre: str,
                                             linea_interior: str = '', estilo: str = '',
                                             capa: str = '', simular: bool = False,
                                             confirmar: bool = False) -> str:
        """TIN desde una FeatureLine exterior y otra interior opcional, por handles.

        Lineas cerradas, rectas, convexas, sin sitio; interior estrictamente
        contenida. Unidades metros. No calcula daylight ni crea Grading nativo.
        Contorno XY copiado: cambios XY requieren crear otra superficie.
        simular ejecuta y revierte; nombres existentes se rechazan.
        """
        return run('civil.superficie_feature_lines', dict(contorno=contorno, nombre=nombre,
                   linea_interior=linea_interior, estilo=estilo, capa=capa,
                   simular=simular), confirmar)
