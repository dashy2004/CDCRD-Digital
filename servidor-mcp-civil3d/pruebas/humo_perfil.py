"""Suite de humo EN VIVO del perfil estratigrafico, de punta a punta.

Corre contra el puente (127.0.0.1:8760) con Civil 3D 2027 y SOLAR.dwg
abiertos: limpia la corrida anterior, genera el perfil del corte A-A' con la
receta, y VERIFICA el resultado: 0 advertencias, estaciones exactas de los
sondeos, PDF y PNG exportados, y presencia de los 4 colores de estrato en el
PNG (verificar_png, Python puro). Sale con codigo 0 solo si todo pasa.

Uso:  py pruebas\\humo_perfil.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo_perfil                                      # noqa: E402
import perfil_estratigrafico as pe                      # noqa: E402
import puente_cliente as puente                         # noqa: E402
import verificar_png                                    # noqa: E402

# RGB con que el dispositivo PNG pinta los ACI del spec del A-A'
COLORES_ESPERADOS = {
    'RELLENO (ACI 34)': ((184, 92, 0), 0.002),
    'ARCILLA RESIDUAL (ACI 12)': ((221, 0, 0), 0.01),
    'CALIZA METEORIZADA (ACI 51)': ((255, 255, 127), 0.01),
    'CALIZA COMPETENTE (ACI 8)': ((128, 128, 128), 0.03),
}
ESTACIONES_ESPERADAS = {'S-4': 0.0, 'S-3': 243.5159, 'S-2': 502.9383}


def correr():
    fallas = []

    def check(nombre, cond, detalle=''):
        print('%-52s %s %s' % (nombre, 'OK' if cond else 'FALLA', detalle))
        if not cond:
            fallas.append(nombre)

    print('== limpieza previa ==')
    demo_perfil.limpiar()

    print('== generacion ==')
    spec = demo_perfil.spec_aa()
    r = pe.generar(spec, puente, log=lambda m: None)

    check('sin advertencias', r.get('advertencias') == [], str(r.get('advertencias'))[:200])
    creado = r.get('creado', {})
    for clave in ('terreno', 'fondo', 'vista'):
        check('creado: ' + clave, bool(creado.get(clave)))
    for sid, esperado in ESTACIONES_ESPERADAS.items():
        est = r.get('estaciones', {}).get(sid, {}).get('estacion')
        check('estacion %s = %.4f' % (sid, esperado),
              est is not None and abs(est - esperado) < 0.01,
              'obtenida: %s' % est)
    for clave in ('pdf', 'png'):
        exp = r.get('exportado', {}).get(clave, {})
        ruta = exp.get('ruta')
        existe = bool(ruta) and os.path.isfile(ruta) and os.path.getsize(ruta) > 0
        check('exportado %s (%s bytes)' % (clave, exp.get('bytes')), existe, ruta or '(sin ruta)')

    png = r.get('exportado', {}).get('png', {}).get('ruta')
    if png and os.path.isfile(png):
        hist = verificar_png.histograma(png)
        for nombre, (rgb, minimo) in COLORES_ESPERADOS.items():
            frac = verificar_png.fraccion_de_color(hist, rgb)
            check('color %s' % nombre, frac >= minimo, 'fraccion %.4f (min %.4f)' % (frac, minimo))
    else:
        check('png para histograma', False)

    print()
    if fallas:
        print('VEREDICTO: FALLA (%d): %s' % (len(fallas), '; '.join(fallas)))
        return 1
    print('VEREDICTO: OK — perfil estratigrafico de punta a punta')
    return 0


if __name__ == '__main__':
    sys.exit(correr())
