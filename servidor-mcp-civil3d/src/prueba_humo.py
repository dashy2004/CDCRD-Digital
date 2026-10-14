"""Prueba de humo del puente de Civil 3D, sin pasar por el cliente MCP.

    py src\\prueba_humo.py

Comprueba, en orden: puente vivo, dibujo activo, API de Civil 3D cargada,
colecciones con conteo y una consulta real. Cada paso imprime lo que fallo,
no un OK global, para que el diagnostico no dependa de leer el log.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import puente_cliente as puente  # noqa: E402


def paso(titulo, fn):
    print(f'\n== {titulo}')
    try:
        resultado = fn()
    except puente.PuenteError as exc:
        print(f'   FALLO [{exc.codigo}] {exc.mensaje}')
        return None
    except Exception as exc:                       # noqa: BLE001
        print(f'   FALLO {type(exc).__name__}: {exc}')
        return None
    print('   ' + json.dumps(resultado, ensure_ascii=False, indent=2, default=str)[:1200])
    return resultado


def main():
    if paso('ping', lambda: puente.llamar('ping')) is None:
        print('\nSin puente: abra Civil 3D 2027 (o escriba CDCRDMCP) y repita.')
        return 1
    info = paso('doc.info', lambda: puente.llamar('doc.info'))
    if info and not info.get('civil3d'):
        print('\nEl dibujo no tiene CivilDocument: las colecciones de Civil 3D no aplican.')
        return 2
    cols = paso('civil.colecciones', lambda: puente.llamar('civil.colecciones'))
    if cols:
        con_datos = [c for c in cols['colecciones'] if (c.get('cantidad') or 0) > 0]
        print(f'\n   colecciones con objetos: {len(con_datos)}')
        for c in con_datos[:10]:
            print(f"      {c['miembro']}: {c['cantidad']}")
        if con_datos:
            miembro = con_datos[0]['miembro']
            paso(f'objects.query sobre {miembro}',
                 lambda: puente.llamar('objects.query', {'coleccion': miembro, 'limite': 3}))
    paso('types.discover (espacio modelo)', lambda: puente.llamar('types.discover'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
