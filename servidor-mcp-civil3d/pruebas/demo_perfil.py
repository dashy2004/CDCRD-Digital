"""Demo EN VIVO: reproduce el perfil estratigrafico de SOLAR.dwg desde cero.

Corre contra el puente (127.0.0.1:8760) con Civil 3D 2027 y SOLAR.dwg abiertos.
Usa el spec del corte A-A' (S-4,S-3,S-2) y las 4 superficies de estrato del GM,
lee los sondeos del GeotechnicalModeler.db (copia local) y exporta a _diag.

NO borra nada por defecto (el perfil queda para revision). Con --limpiar borra
todos los objetos PERFIL-DEMO-* al final. El dibujo NO se guarda.

Uso:  py pruebas\\demo_perfil.py [--limpiar]
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
import perfil_estratigrafico as pe  # noqa: E402

GEO = r'C:\Civil3D_Geo'
DIAG = r'C:\Users\emilg\Artificial IQ\_diag'
PREF = 'PERFIL-DEMO'


def spec_aa():
    # DB sobre carpeta montada da "disk I/O error": trabajar sobre copia local.
    db_orig = os.path.join(GEO, 'GeotechnicalModeler.db')
    db_local = os.path.join(tempfile.gettempdir(), 'gm_demo.db')
    try:
        shutil.copy2(db_orig, db_local)
        db = db_local
    except OSError:
        db = None
    return {
        'prefijo': PREF,
        'alineamiento': "Corte A-A'",
        'superficie_terreno': 'TERRENO_FABDEM_SITIO',
        'sondeos': ['S-4', 'S-3', 'S-2'],
        'origen': [410000, 2044000],
        'db_sondeos': db,
        'csv_ubicaciones': os.path.join(GEO, 'sondeos_ubicaciones.csv'),
        'csv_estratigrafia': os.path.join(GEO, 'sondeos_estratigrafia.csv'),
        'estilo_forma_base': 'GEO - Relleno',
        'estratos': [
            {'codigo': 101, 'nombre': 'RELLENO', 'superficie': 'GM - Stratum - RELLENO.1', 'color_aci': 34},
            {'codigo': 205, 'nombre': 'ARCILLA RESIDUAL', 'superficie': 'GM - Stratum - ARCILLA RESIDUAL.1', 'color_aci': 12},
            {'codigo': 310, 'nombre': 'CALIZA METEORIZADA', 'superficie': 'GM - Stratum - CALIZA METEORIZADA.1', 'color_aci': 51},
            {'codigo': 320, 'nombre': 'CALIZA COMPETENTE', 'superficie': 'GM - Stratum - CALIZA COMPETENTE.1', 'color_aci': 8},
        ],
        'mostrar': {'spt': True, 'nivel_freatico': True, 'leyenda': True, 'columnas': True},
        'exportar': {'pdf': os.path.join(DIAG, 'perfil_demo.pdf'),
                     'png': os.path.join(DIAG, 'perfil_demo.png'), 'papel': 'full bleed A3'},
    }


def limpiar():
    """Borra TODOS los objetos PERFIL-DEMO-* (entidades, vista, perfiles, estilos)."""
    borrados = {'entidades': 0, 'vistas': 0, 'perfiles': 0, 'estilos': 0}
    # 1. entidades por capa
    for capa in [PREF + '-SOND', PREF + '-TXT', PREF + '-LEG']:
        r = puente.llamar('objects.query', {'capa': capa, 'limite': 500})
        hs = [o['handle'] for o in r['objetos']]
        if hs:
            puente.llamar_con_aprobacion('objects.erase', {'handles': hs})
            borrados['entidades'] += len(hs)
    # 2 y 3. vistas de perfil y perfiles: son por alineamiento en 2027
    def _ids(res):
        return res.get('handles', []) if isinstance(res, dict) else []
    ra = puente.llamar('objects.query', {'coleccion': 'alineamientos', 'props': ['Name'], 'limite': 100})
    for a in ra['objetos']:
        for metodo, clave in [('GetProfileViewIds', 'vistas'), ('GetProfileIds', 'perfiles')]:
            rp = puente.llamar('objects.invoke', {'handle': a['handle'], 'metodo': metodo})
            hx = []
            for h in _ids(rp['resultado']):
                try:
                    nom = puente.llamar('objects.read', {'handle': h, 'ruta': 'Name'})['valor']
                except puente.PuenteError:
                    continue
                if str(nom).startswith(PREF):
                    hx.append(h)
            if hx:
                puente.llamar_con_aprobacion('objects.erase', {'handles': hx})
                borrados[clave] += len(hx)
    # 4. estilos de forma: NO se purgan (se reusan por ya_existia; purgar+recrear
    #    el mismo nombre en el acto hace que CopyAsSibling devuelva nulo).
    print('limpieza:', json.dumps(borrados))
    return borrados


def main():
    r = puente.llamar('ping')
    print('puente:', r.get('version'), r.get('build'))
    if r.get('version') != '0.3.1':
        print('AVISO: se esperaba v0.3.1; reinicie Civil 3D si hace falta')
    spec = spec_aa()
    res = pe.generar(spec, puente)
    print('\n=== RESULTADO ===')
    print(json.dumps({k: v for k, v in res.items() if k != 'estaciones'}, ensure_ascii=True, indent=1, default=str)[:2500])
    print('estaciones:', json.dumps(res.get('estaciones', {}), default=str))
    if '--limpiar' in sys.argv:
        limpiar()
    return 0 if not res.get('advertencias') else 0  # advertencias no son fallo duro


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
