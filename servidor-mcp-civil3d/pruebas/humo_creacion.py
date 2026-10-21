"""Prueba de humo EN VIVO del puente v0.3.0 (creacion nativa + export + vistas).

Corre en el Windows del operador contra el puente TCP (127.0.0.1:8760) con
Civil 3D 2027 y SOLAR.dwg abiertos. Crea objetos con prefijo CDCRD-TEST en una
zona vacia, verifica cada herramienta, exporta PDF/PNG de prueba a _diag y
LIMPIA todo al final. No guarda el dibujo.

Uso:  py pruebas\\humo_creacion.py
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import puente_cliente as puente  # noqa: E402

ALINEAMIENTO = "Corte A-A'"
SUPERFICIE = 'TERRENO_FABDEM_SITIO'
ORIGEN = [409000.0, 2045500.0]   # zona vacia, 1.5 km al norte de la vista real
PREFIJO = 'CDCRD-TEST'
DIAG = r'C:\Users\emilg\Artificial IQ\_diag'

pasos = []
creados = {'perfiles': [], 'vistas': [], 'entidades': [], 'vistas_guardadas': [], 'hatch': False}


def paso(nombre, fn):
    try:
        valor = fn()
        pasos.append({'paso': nombre, 'ok': True})
        print('[OK]   ' + nombre + ': ' + json.dumps(valor, ensure_ascii=True, default=str)[:280])
        return valor
    except Exception as exc:
        pasos.append({'paso': nombre, 'ok': False, 'error': str(exc)})
        print('[FALLO] ' + nombre + ': ' + str(exc))
        return None


def main():
    r = paso('ping v0.3.0', lambda: puente.llamar('ping'))
    assert r and r.get('version') == '0.3.0', 'el puente no es v0.3.0: reinicie Civil 3D'

    # --- estilos: lectura de nombres (fix NombreDe) ---
    estilo_geo = ''
    lst = paso('estilos.listar ProfileStyles', lambda: puente.llamar(
        'estilos.listar', {'familia': 'ProfileStyles'}))
    if lst:
        nombres = [e['nombre'] for e in lst['estilos'] if e['nombre']]
        assert nombres, 'ProfileStyles sin nombres legibles'
        geo = [n for n in nombres if n.upper().startswith('GEO')]
        estilo_geo = geo[0] if geo else nombres[0]
        print('       perfiles: ' + ', '.join(nombres[:10]))

    gm = paso('estilos.listar GM (diagnostico)', lambda: puente.llamar(
        'estilos.listar', {'patron': '^GM - '}))
    if gm:
        filas = sorted({e['familia'] + ' :: ' + e['nombre'] for e in gm['estilos']})
        print('       estilos GM presentes (%d):' % len(filas))
        for f in filas:
            print('         ' + f)

    forma = paso('estilos.crear clon ShapeStyle', lambda: puente.llamar_con_aprobacion(
        'estilos.crear', {'familia': 'ShapeStyles', 'nombre': PREFIJO + '-FORMA', 'base': 'GEO - Relleno'}))

    if forma:
        def display():
            try:
                return puente.llamar_con_aprobacion('estilos.display', {
                    'familia': 'ShapeStyles', 'estilo': PREFIJO + '-FORMA',
                    'vista': 'Profile', 'componente': 'AreaFill', 'color_aci': 94})
            except puente.PuenteError as exc:
                if 'valores:' not in exc.mensaje:
                    raise
                valores = [v.strip() for v in exc.mensaje.split('valores:')[1].split(',')]
                comp = next((v for v in valores if 'Fill' in v), valores[0])
                r2 = puente.llamar_con_aprobacion('estilos.display', {
                    'familia': 'ShapeStyles', 'estilo': PREFIJO + '-FORMA',
                    'vista': 'Profile', 'componente': comp, 'color_aci': 94})
                r2['componente_usado'] = comp
                return r2
        paso('estilos.display color del clon', display)

    # --- perfiles y vista ---
    fondo = paso('civil.perfil_constante @18', lambda: puente.llamar_con_aprobacion(
        'civil.perfil_constante', {'alineamiento': ALINEAMIENTO, 'nombre': PREFIJO + '-FONDO',
                                   'elevacion': 18, 'estilo': estilo_geo}))
    if fondo:
        creados['perfiles'].append(fondo['handle'])
        assert abs(fondo['elev_min'] - 18) < 0.01 and abs(fondo['elev_max'] - 18) < 0.01

    terr = paso('civil.perfil_superficie terreno', lambda: puente.llamar_con_aprobacion(
        'civil.perfil_superficie', {'alineamiento': ALINEAMIENTO, 'superficie': SUPERFICIE,
                                    'nombre': PREFIJO + '-TERR', 'estilo': estilo_geo}))
    if terr:
        creados['perfiles'].append(terr['handle'])
        assert terr['elev_max'] > terr['elev_min'] > 0

    vista = paso('civil.vista_perfil rangos+origen', lambda: puente.llamar_con_aprobacion(
        'civil.vista_perfil', {'alineamiento': ALINEAMIENTO, 'nombre': PREFIJO + '-VP',
                               'origen': ORIGEN, 'est_inicio': 0, 'est_fin': 500,
                               'elev_min': 18, 'elev_max': 44}))
    if vista:
        creados['vistas'].append(vista['handle'])
        loc = vista['location']
        assert abs(loc[0] - ORIGEN[0]) < 0.01 and abs(loc[1] - ORIGEN[1]) < 0.01
        assert not vista['fallidos'], vista['fallidos']

    if vista and terr and fondo and forma:
        hatch = paso('civil.hatch_vista_perfil nativo', lambda: puente.llamar_con_aprobacion(
            'civil.hatch_vista_perfil', {'vista': PREFIJO + '-VP', 'nombre': PREFIJO + '-HATCH',
                                         'superior': PREFIJO + '-TERR', 'inferior': PREFIJO + '-FONDO',
                                         'estilo_forma': PREFIJO + '-FORMA'}))
        if hatch:
            nombres_h = [h.get('Name') for h in hatch['hatches']['items']]
            assert PREFIJO + '-HATCH' in nombres_h
            creados['hatch'] = True

    # --- entidades + orden ---
    ents = paso('entity.create nativo', lambda: puente.llamar_con_aprobacion(
        'entity.create', {'entidades': [
            {'tipo': 'capa', 'nombre': PREFIJO, 'color': 1},
            {'tipo': 'polilinea', 'capa': PREFIJO, 'puntos': [[ORIGEN[0], ORIGEN[1] - 50],
             [ORIGEN[0] + 20, ORIGEN[1] - 50], [ORIGEN[0] + 20, ORIGEN[1] - 30]], 'cerrada': True},
            {'tipo': 'texto', 'capa': PREFIJO, 'punto': [ORIGEN[0], ORIGEN[1] - 60],
             'altura': 2.5, 'texto': 'PRUEBA CDCRD ' + chr(209) + 'andu', 'centrado': True},
            {'tipo': 'hatch', 'capa': PREFIJO, 'patron': 'SOLID', 'color': 94,
             'contorno': [[ORIGEN[0], ORIGEN[1] - 50], [ORIGEN[0] + 20, ORIGEN[1] - 50],
                          [ORIGEN[0] + 20, ORIGEN[1] - 30]]},
        ]}))
    if ents:
        assert not ents['errores'], ents['errores']
        creados['entidades'] = [c['handle'] for c in ents['creados'] if c['tipo'] != 'capa']
        paso('entity.draworder abajo', lambda: puente.llamar_con_aprobacion(
            'entity.draworder', {'handles': [ents['creados'][-1]['handle']], 'accion': 'abajo'}))

    # --- lecturas nuevas ---
    if vista:
        r = paso('objects.props con patron', lambda: puente.llamar(
            'objects.props', {'handle': vista['handle'], 'patron': 'Station|Elev',
                              'solo_escribibles': True}))
        if r:
            assert 0 < len(r['propiedades']) < 30 and len(r['metodos']) == 0
    if estilo_geo:
        r = paso('objects.read clave por nombre', lambda: puente.llamar(
            'objects.read', {'ruta': 'Styles.ProfileStyles["%s"].Name' % estilo_geo}))
        if r:
            assert r['valor'] == estilo_geo
    if terr:
        paso('objects.read metodo con argumento', lambda: puente.llamar(
            'objects.read', {'handle': terr['handle'], 'ruta': 'ElevationAt(250)'}))

    # --- export y vistas (v0.3.0) ---
    pap = paso('vista.papeles DWG To PDF', lambda: puente.llamar(
        'vista.papeles', {'dispositivo': 'DWG To PDF.pc3'}))
    if pap:
        a3 = [m['canonico'] for m in pap['papeles'] if 'A3' in m['canonico'].upper()]
        print('       papeles A3: ' + ', '.join(a3[:4]))

    if vista:
        ventana = [ORIGEN[0] - 10, ORIGEN[1] - 10, ORIGEN[0] + 60, ORIGEN[1] + 35]
        pdf = paso('vista.exportar PDF A3', lambda: puente.llamar_con_aprobacion(
            'vista.exportar', {'ruta': DIAG + r'\humo_test.pdf', 'papel': 'full bleed A3',
                               'ventana': ventana}))
        if pdf:
            assert pdf['bytes'] > 1000, 'PDF demasiado pequeno'

    va = paso('vista.guardada ANTES (vista actual)', lambda: puente.llamar_con_aprobacion(
        'vista.guardada', {'nombre': PREFIJO + '-ANTES'}))
    if va:
        creados['vistas_guardadas'].append(va['handle'])

    if ents:
        v3 = paso('vista.3d SE conceptual', lambda: puente.llamar_con_aprobacion(
            'vista.3d', {'direccion': 'SE', 'handles': creados['entidades'][:1],
                         'estilo_visual': 'Conceptual'}))
        if v3:
            vi = paso('vista.guardada ISO', lambda: puente.llamar_con_aprobacion(
                'vista.guardada', {'nombre': PREFIJO + '-ISO'}))
            if vi:
                creados['vistas_guardadas'].append(vi['handle'])
            png = paso('vista.exportar PNG de vista guardada', lambda: puente.llamar_con_aprobacion(
                'vista.exportar', {'ruta': DIAG + r'\humo_test.png',
                                   'dispositivo': 'PublishToWeb PNG.pc3',
                                   'nombre_vista': PREFIJO + '-ISO', 'sombreado': 'AsDisplayed'}))
            if png:
                assert png['bytes'] > 1000, 'PNG demasiado pequeno'
    paso('vista.activar ANTES', lambda: puente.llamar(
        'vista.activar', {'nombre': PREFIJO + '-ANTES'}))

    # --- limpieza (el dibujo NO se guarda) ---
    if creados['hatch']:
        paso('limpieza: quitar hatch', lambda: puente.llamar_con_aprobacion(
            'civil.hatch_vista_perfil', {'vista': PREFIJO + '-VP', 'nombre': PREFIJO + '-HATCH',
                                         'quitar': True}))
    if creados['vistas']:
        paso('limpieza: borrar vista de perfil', lambda: puente.llamar_con_aprobacion(
            'objects.erase', {'handles': creados['vistas']}))
    if creados['perfiles']:
        paso('limpieza: borrar perfiles', lambda: puente.llamar_con_aprobacion(
            'objects.erase', {'handles': creados['perfiles']}))
    if creados['entidades']:
        paso('limpieza: borrar entidades', lambda: puente.llamar_con_aprobacion(
            'objects.erase', {'handles': creados['entidades']}))
    if creados['vistas_guardadas']:
        paso('limpieza: borrar vistas guardadas', lambda: puente.llamar_con_aprobacion(
            'objects.erase', {'handles': creados['vistas_guardadas']}))
    if forma:
        paso('limpieza: purgar estilos de prueba', lambda: puente.llamar_con_aprobacion(
            'estilos.purgar', {'familia': 'ShapeStyles', 'patron': '^' + PREFIJO}))

    ok = sum(1 for p in pasos if p['ok'])
    fallos = [p['paso'] for p in pasos if not p['ok']]
    print('\nRESUMEN: %d/%d pasos OK' % (ok, len(pasos)))
    if fallos:
        print('FALLOS: ' + '; '.join(fallos))
    print(json.dumps({'ok': ok, 'total': len(pasos), 'fallos': fallos}, ensure_ascii=True))
    return 0 if not fallos else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        print(json.dumps({'ok': sum(1 for p in pasos if p['ok']), 'total': len(pasos),
                          'abortado': True}, ensure_ascii=True))
        sys.exit(2)
