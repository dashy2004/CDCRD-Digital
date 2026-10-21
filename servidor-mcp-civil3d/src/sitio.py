"""Civil site design: line/arc alignments and parabolic design profiles, SI."""
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


def parsear_curvas(value, pvis):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or len(rows) > len(pvis) - 2:
        raise ValueError('curvas requiere una lista de PVI interiores y longitudes')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'pvi', 'longitud'}:
            raise ValueError('cada curva requiere {pvi: indice base cero, longitud: metros}')
        index, length = row['pvi'], row['longitud']
        if type(index) is not int or index <= 0 or index >= len(pvis)-1 or index in seen:
            raise ValueError('indice PVI interior requerido, sin duplicados')
        if isinstance(length, bool) or not isinstance(length, (int, float)):
            raise ValueError('longitud debe ser numerica')
        length = float(length)
        if not math.isfinite(length) or length <= 1e-6:
            raise ValueError('longitud debe ser finita y mayor que 0.000001 m')
        station = pvis[index][0]
        if (station - length/2 <= pvis[index-1][0] + 1e-6 or
                station + length/2 >= pvis[index+1][0] - 1e-6):
            raise ValueError('curva fuera de sus tangentes')
        gin = (pvis[index][1]-pvis[index-1][1])/(station-pvis[index-1][0])
        gout = (pvis[index+1][1]-pvis[index][1])/(pvis[index+1][0]-station)
        if not math.isfinite(gin) or not math.isfinite(gout) or abs(gout-gin) <= 1e-10:
            raise ValueError('curva sin cambio de pendiente finito suficiente')
        seen.add(index)
        result.append({'pvi':index, 'longitud':length})
    result.sort(key=lambda c: c['pvi'])
    for a, b in zip(result, result[1:]):
        if pvis[b['pvi']][0]-b['longitud']/2 <= pvis[a['pvi']][0]+a['longitud']/2+1e-6:
            raise ValueError('curvas solapadas o en contacto')
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
        """Eje Civil sin sitio desde LWPOLYLINE abierta XY; conserva la fuente.

        Admite rectas (hasta 1000 vertices) y arcos de hasta 180 grados
        (hasta 200 vertices cuando hay arcos),
        sin cruces/contactos. Conserva los arcos existentes; no agrega fillets.
        Unidades metros. Nombre existente se rechaza.
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
                             simular: bool = False, confirmar: bool = False, curvas: str = '[]') -> str:
        """Rasante Civil por JSON [[estacion,elevacion],...], metros y orden creciente.

        Curvas opcionales JSON [{"pvi":1,"longitud":40}]: parabolas simetricas,
        indice PVI base cero y longitud horizontal en m. Rechaza solapes/contactos
        y exige tangentes positivas. Rechaza ecuaciones de estacion, nombres
        existentes y PVI fuera del eje. Devuelve PVI releidos y pendientes m/m.
        No ordena ni recorta datos. simular ejecuta y revierte.
        """
        try:
            points = parsear_pvis(pvis)
            curve_rows = parsear_curvas(curvas, points)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({'error': str(exc)})
        return run('civil.perfil_pvi', dict(alineamiento=alineamiento, nombre=nombre,
                   pvis=points, estilo=estilo, etiquetas=etiquetas, capa=capa, simular=simular,
                   **({"curvas":curve_rows} if curve_rows else {})), confirmar)
