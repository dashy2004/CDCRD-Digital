"""Perfil estratigrafico por receta (Etapa 3.2) - 100% nativo, repetible.

generar(spec, puente) orquesta las herramientas del puente v0.3.x para producir
un perfil estratigrafico completo de cualquier corte: perfiles de estrato,
vista de perfil, estilos por estrato (color), rellenos nativos (hatch), columnas
de sondeo con SPT y nivel freatico, leyenda y export. Cero constantes
hardcodeadas: todo sale del spec y de la base de sondeos (GeotechnicalModeler.db
o los CSV). Datos geotecnicos hipoteticos/preliminares (declararlo en el informe).

Separacion: los helpers de datos/geometria son puros (testeables sin CAD);
generar es lo unico que llama al puente.
"""
import csv
import math
import os
import re
import sqlite3

AVISO = 'Datos geotecnicos hipoteticos/preliminares; no sustituyen un estudio geotecnico.'


def _spt_de_texto(texto):
    """Extrae el N-SPT de una descripcion ('... SPT N~35') -> 35 o None."""
    if not texto:
        return None
    m = re.search(r'SPT\s*N\s*[~=]?\s*(\d+)', texto, re.I)
    return int(m.group(1)) if m else None


def _freatico_de_texto(texto):
    """Extrae la profundidad del nivel freatico ('... freatico ... ~14.0 m')."""
    if not texto:
        return None
    m = re.search(r'fre[a\xe1]tic[oa][^0-9]*([0-9]+(?:\.[0-9]+)?)\s*m', texto, re.I)
    return float(m.group(1)) if m else None


def leer_sondeos_db(ruta_db):
    """Lee boreholes + estratos + SPT de un GeotechnicalModeler.db (copia local)."""
    con = sqlite3.connect(ruta_db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    sondeos = {}
    for b in cur.execute('SELECT * FROM Borehole'):
        agua = b['DepthToWater']
        sondeos[b['BoringId']] = {
            'x': float(b['XCoord']), 'y': float(b['YCoord']),
            'elev': float(b['Elevation']), 'prof_total': float(b['TotalDepth'] or 0),
            'prof_agua': float(agua) if agua not in (None, '') else None,
            'estratos': [], 'spt': [],
        }
    for s in cur.execute('SELECT * FROM Stratum ORDER BY BoringId, TopDepth'):
        bid = s['BoringId']
        if bid not in sondeos:
            continue
        rgb = None
        if s['Red'] is not None:
            rgb = [int(s['Red']), int(s['Green']), int(s['Blue'])]
        prof_agua = _freatico_de_texto(s['Description'])
        if prof_agua is not None and sondeos[bid]['prof_agua'] is None:
            sondeos[bid]['prof_agua'] = prof_agua
        sondeos[bid]['estratos'].append({
            'top': float(s['TopDepth']), 'base': float(s['BaseDepth']),
            'codigo': int(s['LegendCode']) if s['LegendCode'] is not None else None,
            'nombre': s['GeologyName1'] or s['LegendName'] or '',
            'rgb': rgb, 'descripcion': s['Description'] or '',
            'spt': _spt_de_texto(s['Description']),
        })
    try:
        for sp in cur.execute('SELECT * FROM Sample ORDER BY BoringId, TopDepth'):
            bid = sp['BoringId']
            if bid in sondeos and sp['BlowCount'] is not None:
                sondeos[bid]['spt'].append({
                    'top': float(sp['TopDepth']), 'base': float(sp['BottomDepth']),
                    'n': sp['BlowCount']})
    except sqlite3.Error:
        pass
    con.close()
    return sondeos


def leer_sondeos_csv(ruta_ubic, ruta_estrat):
    """Lee sondeos de los dos CSV (ubicaciones + estratigrafia)."""
    sondeos = {}
    with open(ruta_ubic, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            sondeos[r['Location ID']] = {
                'x': float(r['Easting']), 'y': float(r['Northing']),
                'elev': float(r['Ground Level']), 'prof_total': float(r['Final Depth']),
                'prof_agua': None, 'estratos': [], 'spt': []}
    with open(ruta_estrat, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            bid = r['Location ID']
            if bid not in sondeos:
                continue
            desc = r.get('Description', '')
            prof_agua = _freatico_de_texto(desc)
            if prof_agua is not None and sondeos[bid]['prof_agua'] is None:
                sondeos[bid]['prof_agua'] = prof_agua
            try:
                codigo = int(r['Legend Code'])
            except (ValueError, KeyError, TypeError):
                codigo = None
            sondeos[bid]['estratos'].append({
                'top': float(r['Depth Top']), 'base': float(r['Depth Base']),
                'codigo': codigo, 'nombre': r.get('Geology Code', ''),
                'rgb': None, 'descripcion': desc, 'spt': _spt_de_texto(desc)})
    return sondeos


def cargar_sondeos(spec):
    """Elige la fuente de datos segun el spec (db > csv) y devuelve el dict."""
    db = spec.get('db_sondeos')
    if db and os.path.exists(db):
        return leer_sondeos_db(db)
    ub, es = spec.get('csv_ubicaciones'), spec.get('csv_estratigrafia')
    if ub and es:
        return leer_sondeos_csv(ub, es)
    raise ValueError('el spec no indica db_sondeos valido ni csv_ubicaciones/csv_estratigrafia')


def rango_elevaciones(sondeos, ids, margen=2.0):
    """Rango [min, max] cubriendo terreno y fondo de los sondeos, redondeado."""
    cotas = []
    for sid in ids:
        s = sondeos.get(sid)
        if not s:
            continue
        cotas.append(s['elev'])
        cotas.append(s['elev'] - s['prof_total'])
    if not cotas:
        raise ValueError('ningun sondeo valido para el rango de elevaciones')
    return (math.floor((min(cotas) - margen) / 2) * 2, math.ceil((max(cotas) + margen) / 2) * 2)


# ---------------------------------------------------------------------------
# Orquestacion (unica parte que toca el puente)
# ---------------------------------------------------------------------------

def _esc(puente, metodo, parametros):
    return puente.llamar_con_aprobacion(metodo, parametros)


def _xy(puente, pv_handle, estacion, elevacion):
    """Coordenadas de papel (modelo) de (estacion, elevacion) en la vista."""
    r = puente.llamar('objects.invoke', {
        'handle': pv_handle, 'metodo': 'FindXYAtStationAndElevation',
        'args': [estacion, elevacion, None, None]})
    sal = r['resultado']['salidas']
    claves = list(sal.keys())
    return [sal.get('x', sal[claves[0]]), sal.get('y', sal[claves[1]])]


def _estacion_sondeo(puente, alin_handle, x, y):
    """Estacion (y offset) del sondeo proyectado al eje via StationOffset."""
    r = puente.llamar('objects.invoke', {
        'handle': alin_handle, 'metodo': 'StationOffset', 'args': [x, y, None, None]})
    sal = r['resultado']['salidas']
    claves = list(sal.keys())
    est = sal.get('station', sal.get(claves[0]))
    off = sal.get('offset', sal.get(claves[1]) if len(claves) > 1 else None)
    return est, off


def _handle_por_nombre(puente, coleccion, nombre):
    r = puente.llamar('objects.query', {'coleccion': coleccion, 'props': ['Name']})
    for o in r['objetos']:
        if o.get('Name') == nombre or o.get('nombre') == nombre:
            return o['handle']
    return None


GRILLA_MENOR = ('GridHorizontalMinor', 'GridVerticalMinor')
GRILLA_MAYOR = ('GridHorizontalMajor', 'GridVerticalMajor')


def _estilo_vista(puente, spec, pref, resultado):
    """ProfileViewStyle propio del perfil: grilla tenue (mayores en gris claro,
    menores apagadas) y exageracion vertical explicita si el spec la trae.

    Devuelve el nombre del estilo a usar en civil.vista_perfil ('' si no se
    pudo crear: la vista sale con el estilo por defecto y queda advertencia).
    """
    base = spec.get('estilo_vista_base', 'Major Grids')
    # el nombre lleva la base: cambiar de base crea un estilo nuevo en vez de
    # purgar y recrear (CopyAsSibling devuelve nulo tras purgar en la sesion)
    import re as _re
    nombre = '%s-VISTA_%s' % (pref, _re.sub(r'\W+', '', base)[:12] or 'BASE')
    rc = _esc(puente, 'estilos.crear', {'familia': 'ProfileViewStyles',
                                        'nombre': nombre, 'base': base})
    h = str(rc.get('handle') or '')
    if h in ('', '0', 'None') and not rc.get('ya_existia'):
        resultado['advertencias'].append(
            {'estilo_vista': 'no se pudo crear %s desde %s' % (nombre, base)})
        return spec.get('estilo_vista', '')
    if spec.get('grilla_tenue', True):
        aci = str(spec.get('grilla_color_aci', 253))
        for comp, params in ([(c, {'visible': 'false'}) for c in GRILLA_MENOR] +
                             [(c, {'color_aci': aci}) for c in GRILLA_MAYOR]):
            try:
                _esc(puente, 'estilos.display', dict(params, familia='ProfileViewStyles',
                                                     estilo=nombre, vista='Plan',
                                                     componente=comp))
            except Exception as exc:
                resultado['advertencias'].append({'grilla_%s' % comp: str(exc)})
    if spec.get('exageracion') is not None and h not in ('', '0', 'None'):
        try:
            r = puente.llamar_con_aprobacion('objects.update', {
                'handle': h, 'ruta': 'GraphStyle',
                'props': {'VerticalExaggeration': float(spec['exageracion'])}})
            if r.get('fallidos'):
                resultado['advertencias'].append({'exageracion': r['fallidos']})
        except Exception as exc:
            resultado['advertencias'].append({'exageracion': str(exc)})
    return nombre


def generar(spec, puente, log=print):
    """Genera el perfil estratigrafico completo descrito en spec.

    Devuelve un dict con los handles creados, estaciones y rutas exportadas.
    """
    pref = spec.get('prefijo', 'PERFIL')
    alin_nombre = spec['alineamiento']
    resultado = {'aviso': AVISO, 'creado': {}, 'exportado': {}, 'advertencias': []}

    sondeos = cargar_sondeos(spec)
    ids = spec.get('sondeos') or list(sondeos.keys())
    log('sondeos: ' + ', '.join(ids))

    el_min = spec.get('elev_min')
    el_max = spec.get('elev_max')
    if el_min is None or el_max is None:
        el_min, el_max = rango_elevaciones(sondeos, ids)
    fondo = spec.get('fondo', el_min)

    alin_h = _handle_por_nombre(puente, 'alineamientos', alin_nombre)
    if not alin_h:
        raise ValueError("no se encontro el alineamiento '%s'" % alin_nombre)

    estilo_terreno = spec.get('estilo_terreno', '')
    terr = _esc(puente, 'civil.perfil_superficie', {
        'alineamiento': alin_nombre, 'superficie': spec['superficie_terreno'],
        'nombre': pref + '-TERRENO', 'estilo': estilo_terreno})
    resultado['creado']['terreno'] = terr['handle']
    log('perfil terreno: %s (%.1f-%.1f)' % (terr['handle'], terr['elev_min'], terr['elev_max']))

    estratos = spec['estratos']
    perfiles_estrato = []
    for e in estratos:
        p = _esc(puente, 'civil.perfil_superficie', {
            'alineamiento': alin_nombre, 'superficie': e['superficie'],
            'nombre': '%s-EST-%s' % (pref, e['nombre']),
            'estilo': e.get('estilo_perfil', estilo_terreno)})
        perfiles_estrato.append(dict(e, handle=p['handle'], perfil=p['nombre']))
        log('perfil estrato %s: %s' % (e['nombre'], p['handle']))
    fondo_p = _esc(puente, 'civil.perfil_constante', {
        'alineamiento': alin_nombre, 'nombre': pref + '-FONDO', 'elevacion': fondo,
        'estilo': estilo_terreno})
    resultado['creado']['fondo'] = fondo_p['handle']

    estilo_vista = spec.get('estilo_vista', '')
    if spec.get('grilla_tenue', True) or spec.get('exageracion') is not None:
        estilo_vista = _estilo_vista(puente, spec, pref, resultado) or estilo_vista
    vista = _esc(puente, 'civil.vista_perfil', {
        'alineamiento': alin_nombre, 'nombre': pref + '-VP', 'origen': spec['origen'],
        'elev_min': el_min, 'elev_max': el_max,
        'estilo': estilo_vista, 'banda': spec.get('banda', '')})
    pv = vista['handle']
    resultado['creado']['vista'] = pv
    if vista.get('fallidos'):
        resultado['advertencias'].append({'vista_perfil': vista['fallidos']})
    log('vista de perfil: %s' % pv)

    for e in perfiles_estrato:
        nombre_forma = '%s-FORMA-%s' % (pref, e['nombre'])
        rc = _esc(puente, 'estilos.crear', {
            'familia': 'ShapeStyles', 'nombre': nombre_forma,
            'base': e.get('estilo_forma_base', spec.get('estilo_forma_base', 'GEO - Relleno'))})
        if str(rc.get('handle')) in ('0', None) and not rc.get('ya_existia'):
            resultado['advertencias'].append(
                {'forma_%s' % e['nombre']: 'CopyAsSibling devolvio nulo (nombre recien purgado?)'})
        e['forma'] = nombre_forma
        if e.get('color_rgb') or e.get('color_aci') is not None:
            params = {'familia': 'ShapeStyles', 'estilo': nombre_forma, 'vista': 'Profile',
                      'componente': e.get('componente_relleno', 'AreaFill')}
            if e.get('color_rgb'):
                params['color_rgb'] = e['color_rgb']
            else:
                params['color_aci'] = e['color_aci']
            try:
                _esc(puente, 'estilos.display', params)
            except Exception as exc:
                resultado['advertencias'].append({'color_%s' % e['nombre']: str(exc)})

    # Cada superficie "GM - Stratum - X" es el TECHO del estrato X: el relleno del
    # estrato i va de su propio techo al techo del siguiente (el ultimo, al fondo).
    tramos = []
    if spec.get('rellenar_hasta_terreno', True) and perfiles_estrato:
        # hueco entre el terreno real (TIN) y el techo interpolado del primer
        # estrato: se pinta con el color del primer estrato
        tramos.append((pref + '-H-TERRENO', terr['nombre'], perfiles_estrato[0]['perfil'],
                       perfiles_estrato[0]['forma'], 'terreno->' + perfiles_estrato[0]['nombre']))
    for i, e in enumerate(perfiles_estrato):
        inferior = perfiles_estrato[i + 1]['perfil'] if i + 1 < len(perfiles_estrato) else (pref + '-FONDO')
        tramos.append(('%s-H-%s' % (pref, e['nombre']), e['perfil'], inferior, e['forma'], e['nombre']))
    for nombre_h, superior, inferior, forma, etiqueta in tramos:
        try:
            _esc(puente, 'civil.hatch_vista_perfil', {
                'vista': pref + '-VP', 'nombre': nombre_h,
                'superior': superior, 'inferior': inferior, 'estilo_forma': forma})
            log('hatch %s: %s -> %s' % (etiqueta, superior, inferior))
        except Exception as exc:
            resultado['advertencias'].append({'hatch_%s' % etiqueta: str(exc)})

    entidades = [{'tipo': 'capa', 'nombre': pref + '-SOND', 'color': 7},
                 {'tipo': 'capa', 'nombre': pref + '-TXT', 'color': 7}]
    mostrar = spec.get('mostrar', {})
    ancho_col = spec.get('ancho_columna', 6.0)
    h_txt = spec.get('altura_texto', 1.8)
    estaciones = {}
    colores = {e['codigo']: (e.get('color_aci') or 7) for e in estratos}
    for sid in ids:
        s = sondeos.get(sid)
        if not s:
            resultado['advertencias'].append({'sondeo_%s' % sid: 'no esta en la base'})
            continue
        est, off = _estacion_sondeo(puente, alin_h, s['x'], s['y'])
        estaciones[sid] = {'estacion': est, 'offset': off}
        if mostrar.get('columnas', True):
            for e in s['estratos']:
                ztop = s['elev'] - e['top']
                zbot = s['elev'] - e['base']
                p1 = _xy(puente, pv, est - ancho_col / 2, ztop)
                p2 = _xy(puente, pv, est + ancho_col / 2, ztop)
                p3 = _xy(puente, pv, est + ancho_col / 2, zbot)
                p4 = _xy(puente, pv, est - ancho_col / 2, zbot)
                entidades.append({'tipo': 'solido', 'capa': pref + '-SOND',
                                  'color': colores.get(e['codigo'], 7),
                                  'p1': p1, 'p2': p2, 'p4': p3, 'p3': p4})
                if mostrar.get('spt', True) and e.get('spt') is not None:
                    pm = _xy(puente, pv, est + ancho_col / 2 + 2, (ztop + zbot) / 2)
                    entidades.append({'tipo': 'texto', 'capa': pref + '-TXT', 'punto': pm,
                                      'altura': h_txt, 'texto': 'N=%s' % e['spt']})
        ptop = _xy(puente, pv, est, s['elev'] + 1.5)
        entidades.append({'tipo': 'texto', 'capa': pref + '-TXT', 'punto': ptop,
                          'altura': h_txt * 1.3, 'texto': sid, 'centrado': True})
        if mostrar.get('nivel_freatico', True) and s.get('prof_agua') is not None:
            zw = s['elev'] - s['prof_agua']
            pa = _xy(puente, pv, est - ancho_col, zw)
            pb = _xy(puente, pv, est + ancho_col, zw)
            entidades.append({'tipo': 'linea', 'capa': pref + '-TXT', 'color': 5, 'p1': pa, 'p2': pb})
            pw = _xy(puente, pv, est + ancho_col + 1, zw)
            entidades.append({'tipo': 'texto', 'capa': pref + '-TXT', 'color': 5, 'punto': pw,
                              'altura': h_txt * 0.8, 'texto': 'N.F.'})
    if len(entidades) > 2:
        r = _esc(puente, 'entity.create', {'entidades': entidades})
        resultado['creado']['entidades'] = len([c for c in r['creados'] if c['tipo'] != 'capa'])
        if r['errores']:
            resultado['advertencias'].append({'entidades': r['errores'][:5]})
    resultado['estaciones'] = estaciones

    if mostrar.get('leyenda', True):
        ent_leg = _leyenda(puente, pv, estratos, el_max, spec, pref)
        if ent_leg:
            r = _esc(puente, 'entity.create', {'entidades': ent_leg})
            if r['errores']:
                resultado['advertencias'].append({'leyenda': r['errores'][:3]})

    exp = spec.get('exportar', {})
    if exp.get('pdf') or exp.get('png'):
        # Los plots por ventana salen casi vacios; una vista guardada en planta
        # enmarcada en la vista de perfil renderiza de forma fiable.
        vista_nombre = pref + '-PLANTA'
        try:
            _esc(puente, 'vista.guardada', {
                'nombre': vista_nombre, 'direccion': 'PLANTA', 'handles': [pv],
                'estilo_visual': spec.get('estilo_visual', '2dWireframe')})
        except Exception as exc:
            resultado['advertencias'].append({'vista_planta': str(exc)})
            vista_nombre = None
    if exp.get('pdf'):
        try:
            params = {'ruta': exp['pdf'], 'papel': exp.get('papel', 'A3')}
            if vista_nombre:
                params['nombre_vista'] = vista_nombre
            else:
                params['handles'] = [pv]
            resultado['exportado']['pdf'] = _esc(puente, 'vista.exportar', params)
        except Exception as exc:
            resultado['advertencias'].append({'export_pdf': str(exc)})
    if exp.get('png'):
        try:
            params = {'ruta': exp['png'], 'dispositivo': 'PublishToWeb PNG.pc3'}
            if exp.get('papel_png'):
                params['papel'] = exp['papel_png']
            if vista_nombre:
                params['nombre_vista'] = vista_nombre
            else:
                params['handles'] = [pv]
            resultado['exportado']['png'] = _esc(puente, 'vista.exportar', params)
        except Exception as exc:
            resultado['advertencias'].append({'export_png': str(exc)})

    return resultado


def _leyenda(puente, pv, estratos, el_max, spec, pref):
    """Rectangulos de color + nombre de cada estrato, dentro de la vista."""
    ent = [{'tipo': 'capa', 'nombre': pref + '-LEG', 'color': 7}]
    try:
        anc = _xy(puente, pv, spec.get('leyenda_estacion', 10),
                  el_max - spec.get('leyenda_offset', 1))
    except Exception:
        return None
    dx = spec.get('leyenda_dx', 4.0)
    dy = spec.get('leyenda_dy', 3.0)
    h = spec.get('altura_texto', 1.8)
    for i, e in enumerate(estratos):
        y = anc[1] - i * dy
        ent.append({'tipo': 'solido', 'capa': pref + '-LEG', 'color': e.get('color_aci', 7),
                    'p1': [anc[0], y], 'p2': [anc[0] + dx, y],
                    'p4': [anc[0] + dx, y - dy * 0.7], 'p3': [anc[0], y - dy * 0.7]})
        ent.append({'tipo': 'texto', 'capa': pref + '-LEG',
                    'punto': [anc[0] + dx + 1, y - dy * 0.5], 'altura': h,
                    'texto': '%s %s' % (e.get('codigo', ''), e['nombre'])})
    return ent
