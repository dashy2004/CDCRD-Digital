"""Civil site design: straight polylines and tangent-only design profiles, SI."""
import json
import math


def parsear_pvis(value):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or not 2 <= len(rows) <= 1000:
        raise ValueError('pvis requiere 2-1000 pares [estacion,elevacion]')
    previous = -math.inf
    result = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('cada PVI requiere [estacion,elevacion]')
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) for x in row):
            raise ValueError('estacion y elevacion deben ser numeros')
        station, elevation = map(float, row)
        if not all(map(math.isfinite, (station, elevation))) or station - previous <= 1e-8:
            raise ValueError('PVI no finitos, duplicados o sin orden creciente')
        previous = station
        result.append([station, elevation])
    return result


def registrar(mcp, llamar, ok):
    def run(method, params, confirmar):
        if not confirmar:
            return ok({'error': 'operacion de escritura: repita con confirmar=True', **params})
        return llamar(method, {k: v for k, v in params.items() if v != ''}, escribe=True)

    @mcp.tool()
    def crear_parcela_desde_polilinea(polilinea: str, nombre: str, sitio_nuevo: str,
                                      estilo: str = '', capa: str = '', simular: bool = False,
                                      confirmar: bool = False) -> str:
        """Parcela Civil en un sitio NUEVO, con area m2 y fuente conservada.

        Solo LWPOLYLINE cerrada XY de segmentos rectos, sin cruces. Requiere
        INSUNITS y unidades Civil en metros. Rechaza sitios existentes para
        impedir subdividir parcelas ajenas. simular ejecuta y revierte.
        """
        return run('civil.parcela_polilinea', dict(polilinea=polilinea, nombre=nombre,
                   sitio_nuevo=sitio_nuevo, estilo=estilo, capa=capa, simular=simular), confirmar)

    @mcp.tool()
    def crear_alineamiento_desde_polilinea(polilinea: str, nombre: str,
                                          estacion_inicial: float = 0, estilo: str = '',
                                          etiquetas: str = '', capa: str = '',
                                          simular: bool = False, confirmar: bool = False) -> str:
        """Eje Civil sin sitio, de LWPOLYLINE abierta XY recta; conserva la fuente.

        No agrega curvas. Unidades metros. Nombre existente se rechaza.
        simular ejecuta y revierte. El sentido sigue los vertices de la fuente.
        """
        if not math.isfinite(estacion_inicial):
            return ok({'error': 'estacion_inicial debe ser finita'})
        return run('civil.alineamiento_polilinea', dict(polilinea=polilinea, nombre=nombre,
                   estacion_inicial=estacion_inicial, estilo=estilo, etiquetas=etiquetas,
                   capa=capa, simular=simular), confirmar)

    @mcp.tool()
    def crear_perfil_por_pvi(alineamiento: str, nombre: str, pvis: str,
                             estilo: str = '', etiquetas: str = '', capa: str = '',
                             simular: bool = False, confirmar: bool = False) -> str:
        """Rasante Civil por JSON [[estacion,elevacion],...], metros y orden creciente.

        Tangentes sin curvas verticales; rechaza ecuaciones de estacion, nombres
        existentes y PVI fuera del eje. Devuelve PVI releidos y pendientes m/m.
        No ordena ni recorta datos. simular ejecuta y revierte.
        """
        try:
            points = parsear_pvis(pvis)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({'error': str(exc)})
        return run('civil.perfil_pvi', dict(alineamiento=alineamiento, nombre=nombre,
                   pvis=points, estilo=estilo, etiquetas=etiquetas, capa=capa, simular=simular), confirmar)
