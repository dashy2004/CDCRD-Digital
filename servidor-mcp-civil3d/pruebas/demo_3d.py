"""Demo EN VIVO 3.4: isometrico de sondeos, copiar a 3D, toma de cerca y lamina.

Requiere puente >= 0.4.0, SOLAR.dwg abierto y, para la lamina, haber corrido
demo_perfil.py (vista guardada PERFIL-DEMO-PLANTA). No guarda el dibujo.
Salidas en _diag: iso_sondeos.png/.pdf, cerca_S3.png, lamina_iso.pdf.
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(RAIZ, 'src'))
import puente_cliente as puente  # noqa: E402
import tridimensional as t3  # noqa: E402

GEO = r'C:\Civil3D_Geo'
DIAG = r'C:\Users\emilg\Artificial IQ\_diag'
ESTRATOS = [
    {'codigo': 101, 'nombre': 'RELLENO', 'superficie': 'GM - Stratum - RELLENO.1', 'color_aci': 34},
    {'codigo': 205, 'nombre': 'ARCILLA RESIDUAL', 'superficie': 'GM - Stratum - ARCILLA RESIDUAL.1', 'color_aci': 12},
    {'codigo': 310, 'nombre': 'CALIZA METEORIZADA', 'superficie': 'GM - Stratum - CALIZA METEORIZADA.1', 'color_aci': 51},
    {'codigo': 320, 'nombre': 'CALIZA COMPETENTE', 'superficie': 'GM - Stratum - CALIZA COMPETENTE.1', 'color_aci': 8},
]


def main():
    r = puente.llamar('ping')
    print('puente:', r.get('version'))
    db_local = os.path.join(tempfile.gettempdir(), 'gm_demo3d.db')
    try:
        shutil.copy2(os.path.join(GEO, 'GeotechnicalModeler.db'), db_local)
    except OSError:
        db_local = None
    spec = {
        'prefijo': 'ISO-DEMO', 'sondeos': ['S-1', 'S-2', 'S-3', 'S-4', 'S-5'],
        'estratos': ESTRATOS, 'superficie_terreno': 'TERRENO_FABDEM_SITIO',
        'db_sondeos': db_local,
        'csv_ubicaciones': os.path.join(GEO, 'sondeos_ubicaciones.csv'),
        'csv_estratigrafia': os.path.join(GEO, 'sondeos_estratigrafia.csv'),
        'radio': 4.0, 'exageracion_z': 1.0, 'direccion': 'SE',
        'mostrar_superficies': True,
        'exportar': {'png': os.path.join(DIAG, 'iso_sondeos.png'), 'papel_png': 'Sun Hi-Res',
                     'pdf': os.path.join(DIAG, 'iso_sondeos.pdf'), 'papel': 'full bleed A3'},
    }
    res = t3.isometrico_sondeos(spec, puente)
    print('ISO:', json.dumps({k: v for k, v in res.items() if k != 'creado'}, ensure_ascii=True, default=str)[:1500])
    print('ISO creado: entidades=%d superficies=%d vista=%s' % (
        len(res['creado'].get('entidades', [])), len(res['creado'].get('superficies', [])), res['creado'].get('vista')))

    # toma de cerca de S-3 (coordenadas reales del sondeo)
    try:
        cerca = t3.toma_de_cerca(puente, 'ISO-DEMO-CERCA-S3', os.path.join(DIAG, 'cerca_S3.png'),
                                 objetivo=[414640, 2044100, 32], ancho=70, direccion='SE',
                                 estilo_visual='X-Ray', papel='Sun Hi-Res')
        print('CERCA:', json.dumps(cerca, ensure_ascii=True, default=str)[:300])
    except Exception as exc:
        print('CERCA ERROR:', exc)

    # copiar a 3D la vista PERFIL-DEMO-VP (si existe)
    try:
        ra = puente.llamar('objects.query', {'coleccion': 'alineamientos', 'props': ['Name']})
        pv = None
        for a in ra['objetos']:
            rv = puente.llamar('objects.invoke', {'handle': a['handle'], 'metodo': 'GetProfileViewIds'})['resultado']
            for h in (rv.get('handles', []) if isinstance(rv, dict) else []):
                if str(puente.llamar('objects.read', {'handle': h, 'ruta': 'Name'})['valor']).startswith('PERFIL-DEMO'):
                    pv = h
        if pv:
            c3 = t3.copiar_a_3d(puente, pv, paso=10.0, prefijo='ISO-DEMO', solo=['PERFIL-DEMO-'])
            print('COPIAR_A_3D:', json.dumps(c3, ensure_ascii=True, default=str)[:600])
        else:
            print('COPIAR_A_3D: no hay vista PERFIL-DEMO (corra demo_perfil.py antes)')
    except Exception as exc:
        print('COPIAR_A_3D ERROR:', exc)
        traceback.print_exc()

    # lamina A3 con dos viewports
    try:
        vps = [{'vista': 'ISO-DEMO-SE', 'centro': [105, 150], 'ancho': 190, 'alto': 250, 'bloquear': True}]
        if pv:
            vps.append({'vista': 'PERFIL-DEMO-PLANTA', 'centro': [305, 150], 'ancho': 190, 'alto': 250, 'bloquear': True})
        lay = puente.llamar_con_aprobacion('layout.crear', {
            'nombre': 'CDCRD-ISO', 'papel': 'full bleed A3', 'viewports': vps,
            'textos': [{'punto': [20, 285], 'texto': 'TERMINAL INTERREGIONAL SDE - SONDEOS 3D Y PERFIL A-A', 'altura': 5},
                       {'punto': [20, 10], 'texto': 'Datos geotecnicos hipoteticos/preliminares. Generado por API CDCRD-Civil3D.', 'altura': 3}]})
        print('LAYOUT:', json.dumps(lay, ensure_ascii=True, default=str)[:600])
        ex = puente.llamar_con_aprobacion('vista.exportar', {'ruta': os.path.join(DIAG, 'lamina_iso.pdf'),
                                                             'layout': 'CDCRD-ISO'})
        print('LAMINA PDF:', json.dumps(ex, ensure_ascii=True))
    except Exception as exc:
        print('LAYOUT ERROR:', exc)
        traceback.print_exc()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
