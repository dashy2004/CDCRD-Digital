"""Etapa 3.4: isometricos de sondeos, copiar a 3D y tomas de cerca (puente 0.4.0).

Recetas sobre primitivas ya verificadas (entity.create con cilindro/caja,
vista.3d, vista.guardada, vista.exportar, layout.crear). Helpers puros arriba.
"""
import math

from perfil_estratigrafico import cargar_sondeos, AVISO


def estaciones_muestreo(inicio, fin, paso):
    """Estaciones cada `paso` m entre inicio y fin, incluyendo ambos extremos."""
    if paso <= 0:
        raise ValueError('paso debe ser > 0')
    if fin < inicio:
        inicio, fin = fin, inicio
    n = int(math.floor((fin - inicio) / paso + 1e-9))
    ests = [inicio + i * paso for i in range(n + 1)]
    if fin - ests[-1] > 1e-6:
        ests.append(fin)
    return ests


def cilindros_de_sondeo(sid, s, colores, radio=3.0, exag_z=1.0, capa='SOND-3D'):
    """Entidades (cilindros apilados + rotulo) de un sondeo en coordenadas reales.

    exag_z escala las profundidades desde la cota del terreno (la boca del
    sondeo se queda en su sitio; el fondo baja exag_z veces mas).
    """
    ents = []
    for e in s['estratos']:
        z_top = s['elev'] - e['top'] * exag_z
        z_base = s['elev'] - e['base'] * exag_z
        ents.append({'tipo': 'cilindro', 'capa': capa, 'color': colores.get(e['codigo'], 7),
                     'base': [s['x'], s['y'], z_base], 'radio': radio, 'altura': z_top - z_base})
    ents.append({'tipo': 'mtexto', 'capa': capa, 'punto': [s['x'] + radio * 1.2, s['y'], s['elev'] + radio],
                 'altura': radio, 'texto': sid})
    return ents


# ---------------------------------------------------------------------------

def _esc(puente, metodo, parametros):
    return puente.llamar_con_aprobacion(metodo, parametros)


def _handles_por_nombre(puente, coleccion, nombres):
    r = puente.llamar('objects.query', {'coleccion': coleccion, 'props': ['Name'], 'limite': 500})
    quiero = {n.lower() for n in nombres}
    return [o['handle'] for o in r['objetos'] if str(o.get('Name', '')).lower() in quiero]


def isometrico_sondeos(spec, puente, log=print):
    """Columnas 3D de sondeos (cilindros por estrato) + superficies de estrato,
    vista isometrica guardada y export PNG/PDF. Devuelve handles y rutas."""
    pref = spec.get('prefijo', 'ISO')
    res = {'aviso': AVISO, 'creado': {}, 'exportado': {}, 'advertencias': []}
    sondeos = cargar_sondeos(spec)
    ids = spec.get('sondeos') or list(sondeos.keys())
    colores = {e['codigo']: e.get('color_aci', 7) for e in spec.get('estratos', [])}
    radio = spec.get('radio', 3.0)
    exag = spec.get('exageracion_z', 1.0)
    capa = pref + '-SOND3D'
    ents = [{'tipo': 'capa', 'nombre': capa, 'color': 7}]
    for sid in ids:
        if sid not in sondeos:
            res['advertencias'].append({sid: 'no esta en la base'})
            continue
        ents += cilindros_de_sondeo(sid, sondeos[sid], colores, radio, exag, capa)
    r = _esc(puente, 'entity.create', {'entidades': ents})
    handles = [c['handle'] for c in r['creados'] if c['tipo'] != 'capa']
    res['creado']['entidades'] = handles
    if r['errores']:
        res['advertencias'].append({'entidades': r['errores'][:5]})
    log('solidos 3D: %d' % len(handles))

    # superficies de estrato visibles en 3D (triangulos del display Model). El
    # terreno se excluye por defecto: en estilos opacos tapa las columnas.
    sup_nombres = [e['superficie'] for e in spec.get('estratos', []) if e.get('superficie')]
    if spec.get('superficie_terreno') and spec.get('mostrar_terreno', False):
        sup_nombres.append(spec['superficie_terreno'])
    sup_handles = _handles_por_nombre(puente, 'superficies', sup_nombres) if sup_nombres else []
    res['creado']['superficies'] = sup_handles
    if spec.get('mostrar_superficies', True):
        for h in sup_handles:
            try:
                estilo = puente.llamar('objects.read', {'handle': h, 'ruta': 'StyleName'})['valor']
                _esc(puente, 'estilos.display', {'familia': 'SurfaceStyles', 'estilo': estilo,
                                                  'vista': 'Model', 'componente': 'Triangles', 'visible': True})
            except Exception as exc:
                res['advertencias'].append({'superficie_%s' % h: str(exc)})

    # vista isometrica guardada + export
    direccion = spec.get('direccion', 'SE')
    # X-Ray por defecto: deja ver las columnas a traves de las superficies.
    todos = handles + (sup_handles if spec.get('encuadrar_superficies', True) else [])
    _esc(puente, 'vista.3d', {'direccion': direccion, 'handles': todos or handles,
                              'estilo_visual': spec.get('estilo_visual', 'X-Ray')})
    nombre_vista = pref + '-' + str(direccion).replace('[', '').replace(']', '').replace(',', '_')
    _esc(puente, 'vista.guardada', {'nombre': nombre_vista})
    res['creado']['vista'] = nombre_vista
    exp = spec.get('exportar', {})
    if exp.get('png'):
        try:
            params = {'ruta': exp['png'], 'dispositivo': 'PublishToWeb PNG.pc3',
                      'nombre_vista': nombre_vista, 'sombreado': 'AsDisplayed'}
            if exp.get('papel_png'):
                params['papel'] = exp['papel_png']
            res['exportado']['png'] = _esc(puente, 'vista.exportar', params)
        except Exception as exc:
            res['advertencias'].append({'export_png': str(exc)})
    if exp.get('pdf'):
        try:
            res['exportado']['pdf'] = _esc(puente, 'vista.exportar', {
                'ruta': exp['pdf'], 'papel': exp.get('papel', 'A3'), 'nombre_vista': nombre_vista,
                'sombreado': 'AsDisplayed'})
        except Exception as exc:
            res['advertencias'].append({'export_pdf': str(exc)})
    return res


def copiar_a_3d(puente, vista, paso=10.0, prefijo='3D', solo=None, log=print):
    """Equivalente a Profile View > Copy to 3D: cada perfil de la vista pasa a una
    polilinea 3D en coordenadas del modelo (XY del eje, Z del perfil)."""
    res = {'creado': [], 'advertencias': []}
    # objects.query devuelve el ObjectId como handle (objects.read lo abriria y expandiria)
    q = puente.llamar('objects.query', {'handles': [vista], 'props': ['AlignmentId']})
    alin = q['objetos'][0].get('AlignmentId') if q['objetos'] else None
    if not alin:
        raise ValueError('la vista %s no tiene AlignmentId legible' % vista)
    ids = puente.llamar('objects.invoke', {'handle': alin, 'metodo': 'GetProfileIds'})['resultado']
    ids = ids.get('handles', []) if isinstance(ids, dict) else []
    if not ids:
        res['advertencias'].append({'perfiles': 'el alineamiento de la vista no tiene perfiles que copiar'})
    ents = [{'tipo': 'capa', 'nombre': prefijo + '-PERFILES', 'color': 7}]
    nombres = []
    for h in ids:
        nombre = puente.llamar('objects.read', {'handle': h, 'ruta': 'Name'})['valor']
        if solo and not any(str(nombre).startswith(s) for s in solo):
            continue
        e0 = puente.llamar('objects.read', {'handle': h, 'ruta': 'StartingStation'})['valor']
        e1 = puente.llamar('objects.read', {'handle': h, 'ruta': 'EndingStation'})['valor']
        puntos = []
        for st in estaciones_muestreo(e0, e1, paso):
            try:
                z = puente.llamar('objects.invoke', {'handle': h, 'metodo': 'ElevationAt', 'args': [st]})['resultado']
                xy = puente.llamar('objects.invoke', {'handle': alin, 'metodo': 'PointLocation',
                                                      'args': [st, 0, None, None]})['resultado']['salidas']
                k = list(xy.keys())
                puntos.append([xy.get('easting', xy[k[0]]), xy.get('northing', xy[k[1]]), z])
            except Exception as exc:
                res['advertencias'].append({'%s@%.1f' % (nombre, st): str(exc)})
        if len(puntos) >= 2:
            ents.append({'tipo': 'polilinea3d', 'capa': prefijo + '-PERFILES', 'puntos': puntos})
            nombres.append(nombre)
    if len(ents) > 1:
        r = _esc(puente, 'entity.create', {'entidades': ents})
        for c, n in zip([c for c in r['creados'] if c['tipo'] != 'capa'], nombres):
            res['creado'].append({'perfil': n, 'handle': c['handle']})
        if r['errores']:
            res['advertencias'].append({'entidades': r['errores'][:5]})
    log('copiar_a_3d: %d polilineas 3D' % len(res['creado']))
    return res


def toma_de_cerca(puente, nombre, ruta, handles=None, objetivo=None, ancho=None,
                  direccion='SE', estilo_visual='Conceptual', dispositivo='PublishToWeb PNG.pc3',
                  papel=None, log=print):
    """Zoom 3D a un objeto/zona + vista guardada + export."""
    params = {'direccion': direccion, 'estilo_visual': estilo_visual}
    if handles:
        params['handles'] = handles
    if objetivo:
        params['objetivo'] = objetivo
    if ancho:
        params['ancho'] = ancho
    _esc(puente, 'vista.3d', params)
    _esc(puente, 'vista.guardada', {'nombre': nombre})
    exp = {'ruta': ruta, 'dispositivo': dispositivo, 'nombre_vista': nombre, 'sombreado': 'AsDisplayed'}
    if papel:
        exp['papel'] = papel
    r = _esc(puente, 'vista.exportar', exp)
    log('toma de cerca %s -> %s (%d bytes)' % (nombre, r['ruta'], r['bytes']))
    return {'vista': nombre, 'exportado': r}


def registrar(mcp, llamar, ok):
    import json
    import puente_cliente as _p

    @mcp.tool()
    def isometrico_sondeos_3d(spec: str) -> str:
        """Isometrico 3D de sondeos: columnas por estrato (cilindros solidos) +
        superficies de estrato, vista guardada y export PNG/PDF.

        spec JSON: prefijo, sondeos, estratos [{codigo,nombre,superficie,color_aci}],
        superficie_terreno, db_sondeos|csv_*, radio (m), exageracion_z,
        direccion (SE|SW|NE|NW|[x,y,z]), estilo_visual (X-Ray por defecto: deja
        ver las columnas bajo las superficies), mostrar_superficies,
        mostrar_terreno (false: el terreno opaco tapa todo), encuadrar_superficies,
        exportar {png, pdf, papel, papel_png}. Datos hipoteticos/preliminares.
        """
        try:
            datos = json.loads(spec)
        except json.JSONDecodeError as exc:
            return ok({'error': f'spec no es JSON valido: {exc}'})
        msgs = []
        try:
            r = isometrico_sondeos(datos, _p, log=lambda m: msgs.append(str(m)))
            r['log'] = msgs
            return ok(r)
        except Exception as exc:                        # noqa: BLE001
            return ok({'error': f'{type(exc).__name__}: {exc}', 'log': msgs})

    @mcp.tool()
    def copiar_vista_perfil_a_3d(vista: str, paso: float = 10.0, prefijo: str = '3D',
                                 solo: str = '', confirmar: bool = False) -> str:
        """Copy to 3D nativo: los perfiles de una vista de perfil pasan a polilineas 3D
        en coordenadas del modelo (XY del eje por PointLocation, Z por ElevationAt).

        vista: handle de la vista de perfil. paso: metros entre vertices. solo:
        prefijos de nombre de perfil separados por coma (vacio = todos).
        """
        if not confirmar:
            return ok({'error': 'operacion de escritura: repita con confirmar=True', 'vista': vista})
        try:
            filtro = [s.strip() for s in solo.split(',') if s.strip()] or None
            return ok(copiar_a_3d(_p, vista, paso, prefijo, filtro, log=lambda m: None))
        except Exception as exc:                        # noqa: BLE001
            return ok({'error': f'{type(exc).__name__}: {exc}'})

    @mcp.tool()
    def toma_de_cerca_3d(nombre: str, ruta: str, handles: str = '', objetivo: str = '',
                         ancho: str = '', direccion: str = 'SE', estilo_visual: str = 'Conceptual',
                         dispositivo: str = 'PublishToWeb PNG.pc3', papel: str = '',
                         confirmar: bool = False) -> str:
        """Zoom 3D a un sondeo/estrato/objeto, lo guarda como vista y lo exporta.

        handles: objetos a encuadrar (coma); o objetivo 'x,y,z' + ancho (m).
        """
        if not confirmar:
            return ok({'error': 'operacion de escritura: repita con confirmar=True', 'nombre': nombre})
        from creacion import parsear_handles, parsear_punto, parsear_num
        try:
            hs = parsear_handles(handles) if handles else None
            obj = parsear_punto(objetivo, 'objetivo') if objetivo else None
            an = parsear_num(ancho, 'ancho')
            return ok(toma_de_cerca(_p, nombre, ruta, hs, obj, an, direccion, estilo_visual,
                                    dispositivo, papel or None, log=lambda m: None))
        except Exception as exc:                        # noqa: BLE001
            return ok({'error': f'{type(exc).__name__}: {exc}'})

    return mcp
