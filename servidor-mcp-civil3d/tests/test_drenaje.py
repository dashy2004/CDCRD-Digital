import copy, hashlib, json, math, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import drenaje
import drenaje_calculo as calc


# ---------- pure design: inlets ----------
def run(zs, step=10.0, side='der', x0=0.0, offset=3.5):
    """Straight gutter along +X, one point per station, elevations given."""
    return dict(baseline='A', lado=side, indice=0, puntos=[dict(estacion=k * step, desplazamiento=offset, xyz=[x0 + k * step, 0.0, z]) for k, z in enumerate(zs)])


def test_extremes_single_slope_and_flat():
    pts = run([10, 9, 8, 7])['puntos']
    assert calc.extremos_cuneta(pts) == ([0], [3], False)
    pts = run([7, 8, 9, 10])['puntos']
    assert calc.extremos_cuneta(pts) == ([3], [0], False)
    assert calc.extremos_cuneta(run([5, 5, 5])['puntos']) == ([0], [2], True)


def test_extremes_with_plateau_sag_and_interior_crest():
    # z: 10 9 8 8 8 9 10 9 8  -> plateau sag at index 3 (middle), interior crest at 6, sag at 8, crest at 0
    pts = run([10, 9, 8, 8, 8, 9, 10, 9, 8])['puntos']
    assert calc.extremos_cuneta(pts) == ([0, 6], [3, 8], False)


def test_inlets_at_every_sag_and_spacing_respected():
    # 200 m descending to a sag at 100 m then ascending: crest 0, sag at 100 m, crest at 200 m
    zs = [10 - k * .1 for k in range(11)] + [9 + k * .1 for k in range(1, 11)]
    out = calc.proponer_imbornales([run(zs)], intensidad_mm_h=120, espaciamiento_max_m=60, ancho_aporte_m=8, coeficiente_c=.9)
    c = out['cunetas'][0]
    assert len(c['puntos_bajos']) == 1 and c['puntos_bajos'][0]['estacion'] == 100
    rows = c['imbornales']
    sag = [r for r in rows if r['tipo'] == 'punto_bajo']
    assert len(sag) == 1 and sag[0]['estacion'] == pytest.approx(100) and len(sag[0]['aportes']) == 2
    # each 100 m slope split in ceil(100/60)=2 parts of 50 m: inlets at 50, 100, 150
    assert [round(r['estacion'], 6) for r in rows] == [50, 100, 150]
    assert max(b['distancia_m'] - a['distancia_m'] for a, b in zip(rows, rows[1:])) <= 60 + 1e-9
    # tributaries cover the whole run exactly once
    assert sum(r['longitud_aporte_m'] for r in rows) == pytest.approx(c['longitud_m'])
    assert sag[0]['longitud_aporte_m'] == pytest.approx(100)
    # rational method: Q = 0.9 * 120 * (100*8) / 3.6e6
    assert sag[0]['q_m3_s'] == pytest.approx(.9 * 120 * 800 / 3.6e6)
    assert out['resumen']['q_total_m3_s'] == pytest.approx(.9 * 120 * 200 * 8 / 3.6e6)


def test_inlet_xyz_interpolated_on_the_gutter():
    out = calc.proponer_imbornales([run([10, 9.5, 9.0], step=50, x0=100)], intensidad_mm_h=100, espaciamiento_max_m=40)
    rows = out['cunetas'][0]['imbornales']
    # 100 m slope, ceil(100/40)=3 parts: 33.33, 66.67, 100
    assert [round(r['distancia_m'], 3) for r in rows] == [33.333, 66.667, 100]
    assert rows[0]['xyz'][0] == pytest.approx(133.333, abs=1e-3) and rows[0]['xyz'][2] == pytest.approx(10 - .01 * 33.3333, abs=1e-6)
    assert rows[-1]['tipo'] == 'punto_bajo' and rows[-1]['xyz'] == [200, 0, 9]


def test_flat_run_is_reported_and_still_gets_inlets():
    out = calc.proponer_imbornales([run([5, 5, 5, 5], step=30)], intensidad_mm_h=100, espaciamiento_max_m=50)
    c = out['cunetas'][0]
    assert c['plano'] and len(c['imbornales']) == 2 and c['imbornales'][-1]['estacion'] == 90


def test_side_filter_and_ids():
    out = calc.proponer_imbornales([run([10, 9]), run([10, 9], side='izq')], intensidad_mm_h=100, lados='izq')
    assert len(out['cunetas']) == 1 and out['cunetas'][0]['lado'] == 'izq' and out['cunetas'][0]['imbornales'][0]['id'] == 'I2-1'
    with pytest.raises(ValueError): calc.proponer_imbornales([run([10, 9])], intensidad_mm_h=100, lados='izq')


@pytest.mark.parametrize('kwargs', [dict(intensidad_mm_h=0), dict(intensidad_mm_h=100, espaciamiento_max_m=2), dict(intensidad_mm_h=100, ancho_aporte_m=0),
                                    dict(intensidad_mm_h=100, coeficiente_c=1.5), dict(intensidad_mm_h=100, lados='x')])
def test_invalid_proposal_options(kwargs):
    with pytest.raises(ValueError): calc.proponer_imbornales([run([10, 9])], **kwargs)


def test_invalid_runs_rejected():
    with pytest.raises(ValueError): calc.proponer_imbornales([run([10])], intensidad_mm_h=100)
    bad = run([10, 9]); bad['puntos'][0]['xyz'] = [0, 0]
    with pytest.raises(ValueError): calc.proponer_imbornales([bad], intensidad_mm_h=100)
    bad = run([10, 9]); bad['puntos'].reverse()
    with pytest.raises(ValueError): calc.proponer_imbornales([bad], intensidad_mm_h=100)


# ---------- pure design: network ----------
NODES = [dict(id='I1', tipo='imbornal', xyz=[0, 0, 100.0], q_m3_s=.05, hacia='P1'),
         dict(id='I2', tipo='imbornal', xyz=[0, 20, 100.1], q_m3_s=.04, hacia='P1'),
         dict(id='P1', tipo='pozo', xyz=[40, 10, 99.8], hacia='S'),
         dict(id='S', tipo='salida', xyz=[100, 10, 99.5])]


def test_manning_capacity_formula():
    d, s, n = .3, .005, .013
    assert calc.capacidad_manning(d, s, n) == pytest.approx(math.pi * d * d / 4 * (d / 4) ** (2 / 3) * math.sqrt(s) / n)


def test_network_design_rules():
    out = calc.disenar_red(NODES, diametros_mm=[300, 375, 450, 600], pendiente_min=.005, profundidad_min_m=1.0, n_manning=.013, sumidero_m=.1)
    pipes = {p['id']: p for p in out['tuberias']}
    assert set(pipes) == {'T-I1-P1', 'T-I2-P1', 'T-P1-S'}
    for p in pipes.values():
        assert p['pendiente'] >= .005 - 1e-12 and p['cota_fin'] < p['cota_inicio']
        assert p['profundidad_clave_inicio_m'] >= 1 - 1e-9 and p['profundidad_clave_fin_m'] >= 1 - 1e-9
        assert p['capacidad_m3_s'] >= p['q_m3_s'] and p['diametro_mm'] in (300, 375, 450, 600)
    # accumulated flow and non-decreasing diameters downstream
    assert pipes['T-P1-S']['q_m3_s'] == pytest.approx(.09)
    assert pipes['T-P1-S']['diametro_mm'] >= max(pipes['T-I1-P1']['diametro_mm'], pipes['T-I2-P1']['diametro_mm'])
    # outgoing invert at the manhole never above the incoming inverts
    assert pipes['T-P1-S']['cota_inicio'] <= min(pipes['T-I1-P1']['cota_fin'], pipes['T-I2-P1']['cota_fin']) + 1e-12
    # head inlet invert is rim - cover - D
    assert pipes['T-I1-P1']['cota_inicio'] == pytest.approx(100 - 1 - pipes['T-I1-P1']['diametro_m'])
    structures = {s['id']: s for s in out['estructuras']}
    assert structures['S']['cota_fondo'] == pytest.approx(pipes['T-P1-S']['cota_fin'] - .1)
    assert structures['P1']['cota_fondo'] == pytest.approx(min(pipes['T-I1-P1']['cota_fin'], pipes['T-I2-P1']['cota_fin'], pipes['T-P1-S']['cota_inicio']) - .1)
    assert out['resumen']['q_salida_m3_s'] == pytest.approx(.09) and out['estructuras'][-1]['id'] == 'S'


def test_smallest_sufficient_diameter_and_catalog_overflow():
    # 300 mm at 0.5 % carries ~0.068 m3/s: 0.04 m3/s fits, the 0.09 m3/s of NODES does not
    light = copy.deepcopy(NODES); light[0]['q_m3_s'] = light[1]['q_m3_s'] = .02
    small = calc.disenar_red(light, diametros_mm=[300, 600])
    assert all(p['diametro_mm'] == 300 for p in small['tuberias'])
    assert {p['id']: p['diametro_mm'] for p in calc.disenar_red(NODES, diametros_mm=[300, 375, 450])['tuberias']}['T-P1-S'] == 375
    big = copy.deepcopy(NODES); big[0]['q_m3_s'] = 2.0
    with pytest.raises(ValueError, match='excede el catalogo'): calc.disenar_red(big, diametros_mm=[300, 375])
    sized = calc.disenar_red(big, diametros_mm=[300, 375, 450, 600, 900, 1200])
    assert {p['id']: p['diametro_mm'] for p in sized['tuberias']}['T-I1-P1'] > 300


def test_steep_downstream_rim_forces_steeper_slope():
    nodes = [dict(id='A', tipo='imbornal', xyz=[0, 0, 100.0], q_m3_s=.01, hacia='S'), dict(id='S', tipo='salida', xyz=[50, 0, 95.0])]
    p = calc.disenar_red(nodes)['tuberias'][0]
    assert p['pendiente'] > .005 and p['cota_fin'] == pytest.approx(95 - 1 - p['diametro_m'])


@pytest.mark.parametrize('change', [
    lambda n: n.pop(), lambda n: n.__setitem__(3, dict(n[3], tipo='pozo')), lambda n: n.__setitem__(0, dict(n[0], hacia='X')),
    lambda n: n.__setitem__(0, dict(n[0], hacia='I2')) or n.__setitem__(1, dict(n[1], hacia='I1')), lambda n: n.__setitem__(0, dict(n[0], id='I2')),
    lambda n: n.__setitem__(0, dict(n[0], xyz=[0, 0])), lambda n: n.__setitem__(0, dict(n[0], q_m3_s=-1)), lambda n: n.__setitem__(3, dict(n[3], hacia='P1')),
    lambda n: n.__setitem__(0, dict(n[0], tipo='x')), lambda n: n.append(dict(id='Z', tipo='salida', xyz=[0, 0, 0])), lambda n: n.__setitem__(0, dict(n[0], xyz=[40, 10, 99.9])),
])
def test_invalid_node_trees(change):
    nodes = copy.deepcopy(NODES); change(nodes)
    with pytest.raises(ValueError): calc.disenar_red(nodes)


def test_bad_parameters_rejected():
    for kw in (dict(diametros_mm=[]), dict(diametros_mm=[50]), dict(pendiente_min=0), dict(profundidad_min_m=20), dict(n_manning=1), dict(sumidero_m=-1)):
        with pytest.raises(ValueError): calc.disenar_red(NODES, **kw)


# ---------- wrapper validation ----------
def test_creation_payload_validation():
    design, structures, pipes = drenaje.disenar(NODES, dict(tuberia=dict(familia='Concrete Pipe'), imbornal=dict(familia='Rect'), pozo=dict(familia='Cyl', tamanio='1200 mm'), salida=dict(familia='Cyl')))
    out = drenaje.validar_creacion(dict(nombre='RED QA', estructuras=structures, tuberias=pipes))
    assert out['capa'] == 'CDCRD-DRENAJE' and out['pendiente_min'] == .005 and len(out['tuberias']) == 3
    assert next(s for s in out['estructuras'] if s['id'] == 'P1')['tamanio'] == '1200 mm'
    for change in (lambda d: d['tuberias'].__setitem__(0, dict(d['tuberias'][0], cota_fin=1e4)), lambda d: d['estructuras'].pop(),
                   lambda d: d['tuberias'].__setitem__(0, dict(d['tuberias'][0], diametro_m=.05)), lambda d: d['estructuras'].__setitem__(0, dict(d['estructuras'][0], cota_fondo=200)),
                   lambda d: d.__setitem__('nombre', ''), lambda d: d['tuberias'].__setitem__(0, dict(d['tuberias'][0], familia=''))):
        data = dict(nombre='RED QA', estructuras=copy.deepcopy(structures), tuberias=copy.deepcopy(pipes)); change(data)
        with pytest.raises(ValueError): drenaje.validar_creacion(data)


@pytest.mark.parametrize('accion,datos', [('cuneta', dict(corredor='')), ('cuneta', dict(corredor='A', codigo='x' * 61)), ('verificar', dict(red=None)),
                                          ('catalogo', dict(lista_partes='a\nb')), ('crear', dict(nombre='R', estructuras=[], tuberias=[])), ('otra', dict())])
def test_invalid_requests_never_reach_cad(accion, datos, monkeypatch, tmp_path):
    monkeypatch.setattr(drenaje.bridge, 'llamar', lambda *a: pytest.fail('Invalid request reached CAD'))
    with pytest.raises(ValueError):
        drenaje.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion=accion, **datos)


# ---------- transport ----------
def prepare(monkeypatch, tmp_path, mode='ok', accion='cuneta', result=None):
    calls = []
    def read(method):
        return {'doc.info': dict(civil3d=True, dibujo=str(tmp_path / 'copy.dwg'), insunits=6),
                'diag.dialogos': dict(modal_abierto=False), 'diag.cola': dict(activas=[])}[method]
    def dispatch(method, payload):
        calls.append((method, payload))
        command, key, digest, tail = payload['linea'].split('\n')
        assert command == 'CDCRDDRENAJEV1' and not tail
        raw = (tmp_path / f'cdcrd-drenaje-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        request = json.loads(raw)
        assert request['pid'] == 123 and request['accion'] == accion
        if accion == 'crear': assert request['simular'] and len(request['tuberias']) == 3
        if mode == 'timeout': raise TimeoutError('uncertain dispatch')
        if mode == 'missing': return
        response = dict(id=key, sha256=digest, module='cdcrd-drenaje', pid=123, ok=mode != 'native-error', committed=False, result=result or {}, error='rolled back')
        if mode == 'wrong-hash': response['sha256'] = 'bad'
        if mode == 'wrong-module': response['module'] = 'other'
        if mode == 'wrong-pid': response['pid'] = 124
        (tmp_path / f'cdcrd-drenaje-{key}.result.json').write_text(json.dumps(response))
    monkeypatch.setattr(drenaje.bridge, 'llamar', read)
    monkeypatch.setattr(drenaje.bridge, 'llamar_con_aprobacion', dispatch)
    return calls


def creation_args():
    design, structures, pipes = drenaje.disenar(NODES, dict(tuberia=dict(familia='Concrete Pipe'), imbornal=dict(familia='Rect'), pozo=dict(familia='Cyl'), salida=dict(familia='Cyl')))
    return dict(nombre='RED QA', estructuras=structures, tuberias=pipes)


def test_hash_and_simulation_default(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, accion='crear')
    result = drenaje.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='crear', **creation_args())
    assert result['ok'] and not result['committed'] and len(calls) == 1


def test_proposal_uses_native_gutter_then_pure_design(monkeypatch, tmp_path):
    gutter = dict(corredor='AA', nombre='C', codigo='Flowline_Gutter', lineas=1, puntos=3, codigos_disponibles=['Flowline_Gutter'], cunetas=[run([10, 9.5, 9], step=50)])
    calls = prepare(monkeypatch, tmp_path, result=gutter)
    out = drenaje.proponer(str(tmp_path / 'copy.dwg'), 123, 'AA', intensidad_mm_h=120, espaciamiento_max_m=40)
    assert len(calls) == 1 and json.loads((tmp_path / f"cdcrd-drenaje-{calls[0][1]['linea'].split(chr(10))[1]}.request.json").read_bytes())['corredor'] == 'AA'
    assert out['propuesta']['resumen']['imbornales'] == 3 and out['recibo']['id']


@pytest.mark.parametrize('mode', ['timeout', 'missing', 'native-error', 'wrong-hash', 'wrong-module', 'wrong-pid'])
def test_uncertain_or_wrong_receipt_never_retries(mode, monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, mode, accion='crear')
    with pytest.raises(drenaje.DrenajeError) as raised:
        drenaje.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='crear', timeout=.001, **creation_args())
    assert len(calls) == 1 and raised.value.receipt['id']


def test_busy_queue_and_wrong_document_prevent_dispatch(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path)
    with pytest.raises(ValueError): drenaje.ejecutar('C:\\other.dwg', 123, accion='cuneta', corredor='AA')
    read = drenaje.bridge.llamar
    monkeypatch.setattr(drenaje.bridge, 'llamar', lambda m: dict(activas=[1]) if m == 'diag.cola' else read(m))
    with pytest.raises(RuntimeError): drenaje.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='cuneta', corredor='AA')
    assert not calls


def test_unconfirmed_tool_does_not_dispatch(monkeypatch, tmp_path):
    registered = {}
    class Mcp:
        def tool(self):
            def save(fn): registered[fn.__name__] = fn; return fn
            return save
    drenaje.registrar(Mcp(), json.dumps)
    monkeypatch.setattr(drenaje, 'ejecutar', lambda *a, **k: pytest.fail('Not confirmed'))
    out = registered['crear_red_drenaje'](str(tmp_path / 'copy.dwg'), 123, 'RED', json.dumps(NODES), 'Concrete Pipe', 'Rect', 'Cyl')
    assert 'confirmar=True' in out
    assert set(registered) == {'listar_catalogo_drenaje', 'proponer_imbornales_corredor', 'crear_red_drenaje', 'verificar_red_drenaje'}
    # design errors are reported before any native call even when confirmed
    bad = json.loads(registered['crear_red_drenaje'](str(tmp_path / 'copy.dwg'), 123, 'RED', json.dumps(NODES[:1]), 'Concrete Pipe', 'Rect', 'Cyl', confirmar=True))
    assert 'error' in bad


def test_confirmed_tool_sends_design_and_returns_receipt(monkeypatch, tmp_path):
    registered = {}
    class Mcp:
        def tool(self):
            def save(fn): registered[fn.__name__] = fn; return fn
            return save
    drenaje.registrar(Mcp(), json.dumps)
    calls = prepare(monkeypatch, tmp_path, accion='crear')
    out = json.loads(registered['crear_red_drenaje'](str(tmp_path / 'copy.dwg'), 123, 'RED QA', json.dumps(NODES), 'Concrete Pipe', 'Rect', 'Cyl', confirmar=True))
    assert out['recibo']['ok'] and not out['recibo']['committed'] and out['diseno']['resumen']['tuberias'] == 3 and len(calls) == 1
    request = json.loads((tmp_path / f"cdcrd-drenaje-{calls[0][1]['linea'].split(chr(10))[1]}.request.json").read_bytes())
    assert request['nombre'] == 'RED QA' and request['capa'] == 'CDCRD-DRENAJE' and all(p['familia'] == 'Concrete Pipe' for p in request['tuberias'])
    assert {s['id']: s['familia'] for s in request['estructuras']} == {'I1': 'Rect', 'I2': 'Rect', 'P1': 'Cyl', 'S': 'Cyl'}
