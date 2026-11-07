import copy, hashlib, json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import cubicacion

THICK = {'Pave1Depth': .075, 'Pave2Depth': .05, 'BaseDepth': .25, 'SubBaseDepth': .35}


@pytest.mark.parametrize('change', [
    lambda t: t.clear(),
    lambda t: t.__setitem__('Pave1Depth', 0),
    lambda t: t.__setitem__('Pave1Depth', 6),
    lambda t: t.__setitem__('Pave1Depth', True),
    lambda t: t.__setitem__('Pave1Depth', float('nan')),
    lambda t: t.__setitem__('Pave1Depth', '0.075'),
    lambda t: t.__setitem__('1bad', .1),
    lambda t: t.__setitem__('Pave1 Depth', .1),
    lambda t: t.update({f'K{i}': .1 for i in range(12)}),
])
def test_invalid_thicknesses_never_reach_cad(change, monkeypatch, tmp_path):
    rows = copy.deepcopy(THICK); change(rows)
    monkeypatch.setattr(cubicacion.bridge, 'llamar', lambda *a: pytest.fail('Invalid request reached CAD'))
    with pytest.raises(ValueError):
        cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='espesores', corredor='AA', espesores=rows)


def test_thickness_options_and_defaults():
    out = cubicacion.validar_accion_espesores(dict(corredor='AA', espesores=json.dumps(THICK)))
    assert out == dict(corredor='AA', espesores=THICK, subensamblajes=[], regiones=[], tolerancia_m=.001)
    with pytest.raises(ValueError): cubicacion.validar_accion_espesores(dict(corredor='AA', espesores=THICK, subensamblajes=['a', 'A']))
    with pytest.raises(ValueError): cubicacion.validar_accion_espesores(dict(corredor='AA', espesores=THICK, tolerancia_m=0))
    with pytest.raises(ValueError): cubicacion.validar_accion_espesores(dict(corredor='', espesores=THICK))


def test_datum_and_volume_options():
    assert cubicacion.validar_accion_datum(dict(corredor='AA')) == dict(corredor='AA', codigo='Datum')
    assert cubicacion.validar_accion_datum(dict(corredor='AA', nombre='D1', codigo='Base'))['nombre'] == 'D1'
    with pytest.raises(ValueError): cubicacion.validar_accion_datum(dict(corredor='AA', codigo='x' * 61))
    with pytest.raises(ValueError): cubicacion.validar_accion_datum(dict(corredor='AA', nombre=0))
    with pytest.raises(ValueError): cubicacion.validar_espesores({'Pave1Depth': .1, 'pave1depth': .2})
    out = cubicacion.validar_accion_cubicacion(dict(corredor='AA', terreno='TIN'))
    assert out == dict(corredor='AA', terreno='TIN', codigos=list(cubicacion.CODIGOS), factor_corte=1, factor_relleno=1)
    assert cubicacion.validar_accion_cubicacion(dict(corredor='AA', terreno='TIN', codigos='["Base"]', datum='D'))['codigos'] == ['Base']
    with pytest.raises(ValueError): cubicacion.validar_accion_cubicacion(dict(corredor='AA', terreno='TIN', datum='tin'))
    with pytest.raises(ValueError): cubicacion.validar_accion_cubicacion(dict(corredor='AA', terreno='TIN', factor_corte=11))
    with pytest.raises(ValueError): cubicacion.validar_accion_cubicacion(dict(corredor='AA'))
    with pytest.raises(ValueError): cubicacion.validar_accion_cubicacion(dict(corredor='AA', terreno='TIN', codigos=['a'] * 21))


def prepare(monkeypatch, tmp_path, mode='ok', committed=False, rebuild_mode='ok'):
    calls = type('Calls', (list,), {})()
    def read(method):
        return {'doc.info': dict(civil3d=True, dibujo=str(tmp_path / 'copy.dwg'), insunits=6),
                'diag.dialogos': dict(modal_abierto=False), 'diag.cola': dict(activas=[])}[method]
    def dispatch(method, payload):
        calls.append((method, payload))
        command, key, digest, tail = payload['linea'].split('\n')
        assert command == 'CDCRDCUBICACIONV1' and not tail
        raw = (tmp_path / f'cdcrd-cubicacion-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        request = json.loads(raw)
        assert request['pid'] == 123 and request['dibujo'] == str(tmp_path / 'copy.dwg')
        current = mode if request['accion'] != 'reconstruir' else rebuild_mode
        if request['accion'] == 'reconstruir': assert request['simular'] is False and set(request) >= {'corredor', 'vence_utc'}
        if request['accion'] == 'espesores': assert request['espesores'] == THICK
        if current == 'timeout': raise TimeoutError('uncertain dispatch')
        if current == 'missing': return
        response = dict(id=key, sha256=digest, module='cdcrd-cubicacion', pid=123, ok=current != 'native-error',
                        committed=committed or request['accion'] == 'reconstruir',
                        result={'accion': request['accion']}, error='rolled back')
        if current == 'wrong-hash': response['sha256'] = 'bad'
        if current == 'wrong-module': response['module'] = 'other'
        if current == 'wrong-pid': response['pid'] = 124
        if current == 'not-object': response = [response]
        (tmp_path / f'cdcrd-cubicacion-{key}.result.json').write_text(json.dumps(response))
    def recording(method, payload):
        key = payload['linea'].split('\n')[1]
        calls.requests.append(json.loads((tmp_path / f'cdcrd-cubicacion-{key}.request.json').read_text()))
        return dispatch(method, payload)
    calls.requests = []
    monkeypatch.setattr(cubicacion.bridge, 'llamar', read)
    monkeypatch.setattr(cubicacion.bridge, 'llamar_con_aprobacion', recording)
    return calls


def test_simulation_default_sends_one_request(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path)
    result = cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='espesores', corredor='AA', espesores=THICK)
    assert result['ok'] and not result['committed'] and 'reconstruccion' not in result and len(calls) == 1


@pytest.mark.parametrize('accion,extra', [('espesores', dict(espesores=THICK)), ('datum', {})])
def test_committed_write_rebuilds_in_its_own_command(accion, extra, monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, committed=True)
    result = cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion=accion, simular=False, corredor='AA', **extra)
    assert result['committed'] and result['reconstruccion']['result'] == {'accion': 'reconstruir'} and len(calls) == 2


def test_volume_commit_never_triggers_rebuild(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, committed=True)
    result = cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='cubicacion', simular=False, corredor='AA', terreno='TIN')
    assert result['committed'] and 'reconstruccion' not in result and len(calls) == 1


def test_failed_rebuild_reports_both_receipts(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, committed=True, rebuild_mode='native-error')
    with pytest.raises(cubicacion.CubicacionError) as raised:
        cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='espesores', simular=False, corredor='AA', espesores=THICK)
    assert raised.value.receipt['aplicado']['committed'] and not raised.value.receipt['reconstruccion']['ok'] and len(calls) == 2


def test_busy_civil_after_commit_keeps_the_committed_receipt(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, committed=True)
    read = cubicacion.bridge.llamar; seen = []
    def busy(method):
        seen.append(method)
        return dict(activas=['cmd']) if method == 'diag.cola' and seen.count('diag.cola') > 1 else read(method)
    monkeypatch.setattr(cubicacion.bridge, 'llamar', busy); monkeypatch.setattr(cubicacion, 'ESPERA_COLA_S', .2)
    with pytest.raises(cubicacion.CubicacionError, match='ocupado') as raised:
        cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='datum', simular=False, corredor='AA')
    assert raised.value.receipt['aplicado']['committed'] and raised.value.receipt['reconstruccion'] is None and len(calls) == 1


@pytest.mark.parametrize('mode,message', [('timeout', 'Despacho incierto'), ('missing', 'Sin recibo'), ('native-error', 'rolled back'),
                                          ('wrong-hash', 'no corresponde'), ('wrong-module', 'no corresponde'), ('wrong-pid', 'no corresponde'),
                                          ('not-object', 'no corresponde')])
def test_uncertain_or_wrong_receipt_never_retries(mode, message, monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, mode)
    # An existing receipt is read even past the short deadline; only 'missing' ends in the timeout branch.
    with pytest.raises(cubicacion.CubicacionError, match=message) as raised:
        cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='espesores', corredor='AA', espesores=THICK, timeout=.05)
    assert len(calls) == 1 and raised.value.receipt['id']


def test_busy_queue_and_wrong_document_prevent_dispatch(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        cubicacion.ejecutar('C:\\other.dwg', 123, accion='datum', corredor='AA')
    read = cubicacion.bridge.llamar
    monkeypatch.setattr(cubicacion.bridge, 'llamar', lambda m: dict(activas=[1]) if m == 'diag.cola' else read(m))
    with pytest.raises(RuntimeError):
        cubicacion.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='datum', corredor='AA')
    assert not calls


def test_unconfirmed_tools_do_not_dispatch(monkeypatch, tmp_path):
    registered = {}
    class Mcp:
        def tool(self):
            def save(fn): registered[fn.__name__] = fn; return fn
            return save
    cubicacion.registrar(Mcp(), json.dumps)
    monkeypatch.setattr(cubicacion, 'ejecutar', lambda *a, **k: pytest.fail('Not confirmed'))
    drawing = str(tmp_path / 'copy.dwg')
    assert 'confirmar=True' in registered['asignar_espesores_pavimento'](drawing, 123, 'AA', json.dumps(THICK))
    assert 'confirmar=True' in registered['crear_datum_corredor'](drawing, 123, 'AA')
    assert 'confirmar=True' in registered['cubicar_corredor'](drawing, 123, 'AA', 'TIN')
    assert set(registered) == {'asignar_espesores_pavimento', 'crear_datum_corredor', 'cubicar_corredor'}


def test_tool_rejects_malformed_json_before_dispatch(monkeypatch, tmp_path):
    registered = {}
    class Mcp:
        def tool(self):
            def save(fn): registered[fn.__name__] = fn; return fn
            return save
    cubicacion.registrar(Mcp(), json.dumps)
    monkeypatch.setattr(cubicacion, 'ejecutar', lambda *a, **k: pytest.fail('Malformed JSON reached dispatch'))
    drawing = str(tmp_path / 'copy.dwg')
    assert 'error' in json.loads(registered['asignar_espesores_pavimento'](drawing, 123, 'AA', '{bad', confirmar=True))
    assert 'error' in json.loads(registered['cubicar_corredor'](drawing, 123, 'AA', 'TIN', codigos='[', confirmar=True))


def test_confirmed_tool_forwards_validated_request(monkeypatch, tmp_path):
    registered = {}
    class Mcp:
        def tool(self):
            def save(fn): registered[fn.__name__] = fn; return fn
            return save
    cubicacion.registrar(Mcp(), json.dumps)
    calls = prepare(monkeypatch, tmp_path)
    out = json.loads(registered['asignar_espesores_pavimento'](str(tmp_path / 'copy.dwg'), 123, 'AA', json.dumps(THICK), confirmar=True))
    assert out['ok'] and not out['committed'] and len(calls) == 1
    out = json.loads(registered['cubicar_corredor'](str(tmp_path / 'copy.dwg'), 123, 'AA', 'TIN', confirmar=True))
    assert out['ok'] and len(calls) == 2
    first, second = calls.requests
    assert first['accion'] == 'espesores' and first['espesores'] == THICK and first['tolerancia_m'] == .001 and first['simular'] is True
    assert second['accion'] == 'cubicacion' and second['terreno'] == 'TIN' and second['codigos'] == list(cubicacion.CODIGOS) and 'datum' not in second
