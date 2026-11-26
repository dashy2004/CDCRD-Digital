"""Prueba viva (requiere Tekla Structures abierto): unión de alma tipo ES-16, detalle 3.

W16X26 que llega al alma de una W21X44 con placa A36 de 1/4 in, tres tornillos
A325N de 5/8 in a 3 in y filete de 3/16 in. Crea un modelo propio en
%TEMP%\\tekla-mcp-pruebas, lo guarda, lo reabre y relee todo.

Uso: py tests\\vivo\\prueba_es16.py [carpeta_catalogos ...]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import captura  # noqa: E402
from config import Config  # noqa: E402
from tekla import Tekla  # noqa: E402

PULG = 25.4
RAIZ = os.path.expandvars(r'%TEMP%\tekla-mcp-pruebas')
NOMBRE = 'union-es16-' + time.strftime('%H%M%S')


def main() -> int:
    cfg = Config()
    t = Tekla(cfg.exePuente, cfg.rutasPermitidas)
    previo = t.tekla_estado()
    out = {'previo': previo['ruta']}
    out['crear'] = t.tekla_crear_modelo(RAIZ, NOMBRE, aceptar_licencia_educativa=True)
    ruta = os.path.join(RAIZ, NOMBRE)
    for carpeta in sys.argv[1:]:
        out.setdefault('catalogos', []).append(t.tekla_copiar_catalogos(carpeta))
    assert os.path.normcase(t.tekla_estado()['ruta']) == os.path.normcase(ruta)
    out['ejes'] = t.tekla_definir_ejes('0 1500 1500', '0 3000', '0', 'A B C', '1 2', 'Eje')
    zs = 525.8 / 2 - 398.5 / 2          # tope de acero al ras
    cara_alma = 8.89 / 2                 # medio espesor del alma de W21X44
    piezas = t.tekla_crear_piezas([
        {'tipo': 'viga', 'nombre': 'Principal W21X44', 'perfil': 'W21X44', 'material': 'A992', 'inicio': [0, 0, 0], 'fin': [3000, 0, 0]},
        {'tipo': 'viga', 'nombre': 'Secundaria W16X26', 'perfil': 'W16X26', 'material': 'A992',
         'inicio': [1500, cara_alma + 0.5 * PULG, zs], 'fin': [1500, 3000, zs]},
    ])
    out['piezas'] = piezas
    xp = 1500 + 6.35 / 2 + 0.25 * PULG / 2        # placa adosada al alma de la secundaria
    alto, ancho = 8.25 * PULG, 3.25 * PULG
    y0, y1, z0, z1 = cara_alma, cara_alma + ancho, zs - alto / 2, zs + alto / 2
    placa = t.tekla_crear_placa([[xp, y0, z0], [xp, y1, z0], [xp, y1, z1], [xp, y0, z1]], 'PL6.35', 'A36', 'Placa de alma')
    out['placa'] = placa
    yb = y1 - 1.25 * PULG
    out['tornillos'] = t.tekla_crear_tornillos(placa['id'], piezas[1]['id'], [xp, yb, zs + 3 * PULG], [xp, yb, zs - 3 * PULG],
                                                'A325N', 0.625 * PULG, [3 * PULG, 3 * PULG], [0], holgura=1.5875)
    out['soldadura'] = t.tekla_crear_soldadura(piezas[0]['id'], placa['id'], 0.1875 * PULG, 0.1875 * PULG)
    out['guardar'] = t.tekla_guardar('prueba viva ES-16')
    t.tekla_abrir_modelo(ruta)
    lista = t.tekla_listar_piezas()
    out['releido'] = lista
    ids = [p['id'] for p in lista['piezas']]
    t.tekla_ajustar_vista([-200, -500, -600], [3200, 3200, 600])
    t.tekla_ajustar_vista([1000, -300, -350], [2000, 700, 400], ajustar_area=False)
    t.tekla_seleccionar([p['id'] for p in lista['piezas'] if p['nombre'] == 'Placa de alma'])
    out['captura'] = captura.capturar(ruta + '.png')
    out['informe'] = t.tekla_crear_informe(ids, 'P_Part_List', os.path.basename(ruta) + '.xsr')
    print(json.dumps(out, ensure_ascii=False, indent=1))
    ok = (len(lista['piezas']) == 3 and lista['grupos_de_tornillos'] == 1 and lista['soldaduras'] == 1
          and len(out['tornillos']['posiciones']) == 3)
    print('RESULTADO:', 'OK' if ok else 'FALLA')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
