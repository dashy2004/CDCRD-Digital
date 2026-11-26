"""Prueba viva (requiere Tekla Structures abierto): cortes, componentes, catálogo y planos.

Crea un modelo propio en %TEMP%\\tekla-mcp-pruebas con una viga principal W21X44, una
secundaria W16X26 que llega a su alma y una columna HP12X84; despunta y ajusta la
secundaria, la corta por un plano, inserta una unión y un detalle del catálogo, y
comprueba cada cambio leyendo la caja del sólido y el peso.

Uso: py tests\\vivo\\prueba_cortes_y_componentes.py <carpeta con catálogos> [numero_union] [numero_detalle]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import captura  # noqa: E402
from config import Config  # noqa: E402
from tekla import ErrorTekla, Tekla  # noqa: E402

RAIZ = os.path.expandvars(r'%TEMP%\tekla-mcp-pruebas')
NOMBRE = 'cortes-' + time.strftime('%H%M%S')
ALA_PRINCIPAL, ANCHO_ALA, CANTO_PRINCIPAL, CANTO_SECUNDARIA = 11.43, 165.1, 525.8, 398.5
HOLGURA = 13.0


def pieza(t: Tekla, nombre: str) -> dict:
    return next(p for p in t.tekla_listar_piezas(nombre)['piezas'] if p['nombre'] == nombre)


def main() -> int:
    cfg = Config()
    t = Tekla(cfg.exePuente, cfg.rutasPermitidas)
    out, fallos = {}, []

    def comprobar(nombre: str, condicion: bool) -> None:
        out.setdefault('comprobaciones', {})[nombre] = bool(condicion)
        if not condicion:
            fallos.append(nombre)

    t.tekla_crear_modelo(RAIZ, NOMBRE, aceptar_licencia_educativa=True)
    ruta = os.path.join(RAIZ, NOMBRE)
    t.tekla_copiar_catalogos(sys.argv[1])
    t.tekla_definir_ejes('0 1500 1500', '0 3000', '0 3000', 'A B C', '1 2', 'Base Techo')
    zs = 3000 + CANTO_PRINCIPAL / 2 - CANTO_SECUNDARIA / 2          # tope de acero al ras
    creadas = t.tekla_crear_piezas([
        {'tipo': 'viga', 'nombre': 'Principal', 'perfil': 'W21X44', 'material': 'A992', 'inicio': [0, 0, 3000], 'fin': [3000, 0, 3000]},
        {'tipo': 'viga', 'nombre': 'Secundaria', 'perfil': 'W16X26', 'material': 'A992', 'inicio': [1500, 300, zs], 'fin': [1500, 3000, zs]},
        {'tipo': 'viga', 'nombre': 'Secundaria 2', 'perfil': 'W16X26', 'material': 'A992', 'inicio': [750, 0, zs], 'fin': [750, 3000, zs]},
        {'tipo': 'columna', 'nombre': 'Columna', 'perfil': 'HP12X84', 'material': 'A992', 'inicio': [0, 3000, 0], 'fin': [0, 3000, 3000]},
    ])
    ids = {c['nombre']: c['id'] for c in creadas}
    sec = ids['Secundaria']

    # 1. Ajuste de extremo: el inicio (y=300) se lleva a 13 mm de la cara del alma de la principal.
    y_ajuste = 8.89 / 2 + HOLGURA
    out['ajuste'] = t.tekla_ajustar_extremo(sec, [1500, y_ajuste, zs], [1, 0, 0], [0, 0, 1])
    tras_ajuste = pieza(t, 'Secundaria')
    comprobar('ajuste lleva el extremo al plano', abs(tras_ajuste['caja_min'][1] - y_ajuste) < 0.5)

    # 2. Despunte superior: caja que cubre el ala de la principal más la holgura.
    tope = 3000 + CANTO_PRINCIPAL / 2
    out['despunte'] = t.tekla_despuntar(sec, [1300, -10, tope - ALA_PRINCIPAL - HOLGURA - 20], [1700, ANCHO_ALA / 2 + HOLGURA, tope + 10])
    tras_despunte = pieza(t, 'Secundaria')
    comprobar('despunte quita material', tras_despunte['peso_neto_kg'] < tras_ajuste['peso_neto_kg'] - 0.05)

    # 3. Corte por plano en y=2500: se elimina el lado de la normal (+Y).
    out['corte'] = t.tekla_cortar_plano(sec, [1500, 2500, zs], [0, 0, 1], [1, 0, 0])
    tras_corte = pieza(t, 'Secundaria')
    comprobar('corte por plano acorta la pieza a y=2500', abs(tras_corte['caja_max'][1] - 2500) < 0.5)
    out['secundaria'] = {'peso_neto_tras_ajuste': tras_ajuste['peso_neto_kg'], 'peso_neto_tras_despunte': tras_despunte['peso_neto_kg'],
                         'peso_neto_tras_corte': tras_corte['peso_neto_kg'], 'caja_final': [tras_corte['caja_min'], tras_corte['caja_max']]}

    # 4. Catálogos.
    normas = t.tekla_normas_tornillos()
    out['normas_tornillos'] = [n['norma'] for n in normas]
    comprobar('el catálogo de tornillos trae A325N', any(n['norma'] == 'A325N' for n in normas))
    numero_union = int(sys.argv[2]) if len(sys.argv) > 2 else 146
    numero_detalle = int(sys.argv[3]) if len(sys.argv) > 3 else 1004
    out['catalogo'] = {n: t.tekla_catalogo_componentes(f'({n})')[:5] for n in (numero_union, numero_detalle)}

    # 5. Unión del catálogo entre la principal y la segunda secundaria.
    out['union'] = t.tekla_crear_componente(numero_union, ids['Principal'], [ids['Secundaria 2']])
    comprobar('la unión genera piezas', out['union']['ok'] and len(out['union']['piezas_creadas']) > 0)

    # 6. Detalle de placa base en el pie de la columna.
    out['detalle'] = t.tekla_crear_detalle(numero_detalle, ids['Columna'], [0, 3000, 0])
    comprobar('el detalle genera piezas', out['detalle']['ok'] and len(out['detalle']['piezas_creadas']) > 0)

    # 7. Guardar, reabrir y releer.
    t.tekla_guardar('prueba viva de cortes y componentes')
    t.tekla_abrir_modelo(ruta)
    lista = t.tekla_listar_piezas()
    out['releido'] = {'piezas': len(lista['piezas']), 'tornillos': lista['grupos_de_tornillos'],
                      'soldaduras': lista['soldaduras'], 'componentes': lista['componentes']}
    comprobar('los dos componentes sobreviven al reabrir', len(lista['componentes']) == 2)
    reabierta = pieza(t, 'Secundaria')
    comprobar('los cortes sobreviven al reabrir', abs(reabierta['peso_neto_kg'] - tras_corte['peso_neto_kg']) < 0.01)

    # 8. Planos: sin numerar se rechaza; tras numerar se crean el de pieza y el de conjunto.
    try:
        t.tekla_crear_plano(reabierta['id'], 'pieza')
        out['plano_sin_numerar'] = 'creado'
    except ErrorTekla as e:
        out['plano_sin_numerar'] = str(e)
    comprobar('sin numerar, el plano se rechaza', 'numeración' in out['plano_sin_numerar'])
    out['numerar'] = t.tekla_numerar()
    comprobar('la numeración queda al día', out['numerar']['numeracion_al_dia'])
    reabierta = pieza(t, 'Secundaria')
    out['plano_pieza'] = t.tekla_crear_plano(reabierta['id'], 'pieza')
    out['plano_conjunto'] = t.tekla_crear_plano(pieza(t, 'Principal')['id'], 'conjunto')
    out['planos'] = t.tekla_listar_planos()
    comprobar('se crean los dos planos', out['plano_pieza']['ok'] and out['plano_conjunto']['ok'] and len(out['planos']) == 2)
    t.tekla_guardar('planos de prueba')

    t.tekla_ajustar_vista([-500, -500, -300], [3500, 3500, 3600])
    out['captura'] = captura.capturar(ruta + '.png')
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print('RESULTADO:', 'OK' if not fallos else 'FALLA: ' + '; '.join(fallos))
    return 0 if not fallos else 1


if __name__ == '__main__':
    sys.exit(main())
