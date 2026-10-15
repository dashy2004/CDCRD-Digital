"""Verificacion EN VIVO del puente v0.5.0 tras el reinicio unico.

Corre por TCP contra el puente. Pasos: build correcto, eventos_dialogo,
suite de humo del perfil (regenera el corte A-A' en el dibujo recien
abierto), lamina A3 por layout (fix de SetPlotCentered), gm.diagnosticar,
gm.reparar (simulacion) y gm.perfil_sondeos solo_perfil sobre el corte B-B'
(reproduccion del NRE del GM con evidencia; el dibujo NO se guarda).

Uso:  py pruebas\\humo_v050.py
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import puente_cliente as puente                         # noqa: E402
import humo_perfil                                      # noqa: E402

DIAG = r'C:\Users\emilg\Artificial IQ\_diag'
fallas = []


def check(nombre, cond, detalle=''):
    print('%-52s %s %s' % (nombre, 'OK' if cond else 'FALLA', str(detalle)[:220]))
    if not cond:
        fallas.append(nombre)


def principal():
    print('== 1. build ==')
    r = puente.llamar('ping', {})
    check('version 0.5.0', r.get('version') == '0.5.0', r.get('version'))
    print('build:', r.get('build'))

    print('== 2. eventos_dialogo ==')
    try:
        d = puente.llamar('diag.dialogos', {})
        check('sin modal abierto', d.get('modal_abierto') is False, d)
    except Exception as exc:                            # noqa: BLE001
        check('diag.dialogos responde', False, exc)

    print('== 3. suite de humo del perfil ==')
    check('humo_perfil 13/13', humo_perfil.correr() == 0)

    print('== 4. lamina A3 por layout ==')
    try:
        lay = puente.llamar_con_aprobacion('layout.crear', {
            'nombre': 'LAMINA-A3-DEMO', 'papel': 'A3',
            'viewports': [{'vista': 'PERFIL-DEMO-PLANTA', 'centro': [200, 150],
                           'ancho': 360, 'alto': 240, 'bloquear': True}],
            'textos': [{'punto': [20, 20], 'altura': 4, 'texto':
                        "CDCRD-Digital - Perfil estratigrafico Corte A-A' "
                        '(datos hipoteticos/preliminares)'}]})
        check('layout.crear sin fallidos', not lay.get('fallidos'), lay.get('fallidos'))
        ruta = os.path.join(DIAG, 'lamina_a3_demo.pdf')
        exp = puente.llamar_con_aprobacion('vista.exportar', {
            'ruta': ruta, 'layout': 'LAMINA-A3-DEMO'})
        check('export layout A3 (%s bytes)' % exp.get('bytes'),
              exp.get('bytes', 0) > 10000, exp.get('ruta'))
    except Exception as exc:                            # noqa: BLE001
        check('lamina A3', False, exc)

    print('== 5. gm.diagnosticar ==')
    try:
        g = puente.llamar('gm.diagnosticar', {})
        print(json.dumps(g, indent=1, ensure_ascii=False)[:1500])
        check('gm.diagnosticar responde', 'problemas' in g)
        check('superficie GM - Top Surface presente', g.get('superficie_top') is True)
    except Exception as exc:                            # noqa: BLE001
        check('gm.diagnosticar responde', False, exc)
        g = {}

    print('== 6. gm.reparar (simulacion) ==')
    try:
        rep = puente.llamar_con_aprobacion('gm.reparar', {'aplicar': False})
        check('gm.reparar simula', 'acciones' in rep, rep.get('acciones'))
    except Exception as exc:                            # noqa: BLE001
        check('gm.reparar simula', False, exc)

    print('== 7. gm.perfil_sondeos solo_perfil (Corte B-B\'; el dwg NO se guarda) ==')
    try:
        ps = puente.llamar_con_aprobacion('gm.perfil_sondeos', {
            'alineamiento': "Corte B-B'", 'vista': "Corte B-B'",
            'solo_perfil': True})
        print(json.dumps(ps, indent=1, ensure_ascii=False)[:1500])
        # Exito O captura estructurada del error del GM: ambos son resultado util
        check('gm.perfil_sondeos con evidencia',
              'perfil' in ps or 'perfil_error' in ps)
    except Exception as exc:                            # noqa: BLE001
        check('gm.perfil_sondeos responde', False, exc)

    print()
    if fallas:
        print('VEREDICTO v0.5.0: FALLA (%d): %s' % (len(fallas), '; '.join(fallas)))
        return 1
    print('VEREDICTO v0.5.0: OK')
    return 0


if __name__ == '__main__':
    sys.exit(principal())
