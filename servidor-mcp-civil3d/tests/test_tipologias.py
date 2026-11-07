import copy, hashlib, json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import tipologias

SEGMENTS = [[0, 35.5, 'R'], [35.5, 47, '-'], [47, 100, 'LR']]


@pytest.mark.parametrize('change', [
    lambda s: s.clear(),
    lambda s: s.__setitem__(0, [0, 35.5]),
    lambda s: s.__setitem__(0, [0, 35.5, 'X']),
    lambda s: s.__setitem__(1, [36, 47, '-']),
    lambda s: s.__setitem__(0, [0, 0, 'R']),
    lambda s: s.__setitem__(0, [True, 35.5, 'R']),
    lambda s: s.__setitem__(0, [float('nan'), 35.5, 'R']),
    lambda s: s.extend([[100 + i, 101 + i, 'L'] for i in range(100)]),
])
def test_invalid_segments_never_reach_cad(change, monkeypatch, tmp_path):
    rows = copy.deepcopy(SEGMENTS); change(rows)
    monkeypatch.setattr(tipologias.bridge, 'llamar', lambda *a: pytest.fail('Invalid request reached CAD'))
    with pytest.raises(ValueError):
        tipologias.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='aplicar', corredor='AA', segmentos=rows)


def test_slope_segments_require_terrain(monkeypatch, tmp_path):
    monkeypatch.setattr(tipologias.bridge, 'llamar', lambda *a: pytest.fail('Invalid request reached CAD'))
    with pytest.raises(ValueError):
        tipologias.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='aplicar', corredor='AA', segmentos=[[0, 50, 'talud'], [50, 100, 'LR']])
    assert tipologias.validar_aplicacion(dict(corredor='AA', segmentos=[[0, 50, 'talud'], [50, 100, 'LR']], superficie_terreno='TIN'))['superficie_terreno'] == 'TIN'


@pytest.mark.parametrize('key,value', [('sonda_m', 0), ('sonda_m', 11), ('union_min_m', -1), ('libre_min_m', float('inf')),
                                       ('corredor', ''), ('superficies_pavimento', 'x'), ('superficies_pavimento', [''])])
def test_invalid_classification_options(key, value):
    with pytest.raises(ValueError):
        tipologias.validar_clasificacion({'corredor': 'AA', key: value})


def test_classification_defaults_and_optional_edge_code():
    out = tipologias.validar_clasificacion(dict(corredor='AA'))
    assert out == dict(corredor='AA', sonda_m=1.0, union_min_m=2.0, libre_min_m=5.0, superficies_pavimento=[], superficies_excluidas=[])
    assert tipologias.validar_clasificacion(dict(corredor='AA', codigo_borde='Edge', superficies_pavimento='["T1"]'))['codigo_borde'] == 'Edge'


def prepare(monkeypatch, tmp_path, mode='ok', accion='aplicar'):
    calls = []
    def read(method):
        return {'doc.info': dict(civil3d=True, dibujo=str(tmp_path / 'copy.dwg'), insunits=6),
                'diag.dialogos': dict(modal_abierto=False), 'diag.cola': dict(activas=[])}[method]
    def dispatch(method, payload):
        calls.append((method, payload))
        command, key, digest, tail = payload['linea'].split('\n')
        assert command == 'CDCRDTIPOLOGIASV1' and not tail
        raw = (tmp_path / f'cdcrd-tipologias-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        request = json.loads(raw)
        assert request['pid'] == 123 and request['accion'] == accion
        if accion == 'aplicar': assert request['segmentos'] == SEGMENTS and request['simular']
        if mode == 'timeout': raise TimeoutError('uncertain dispatch')
        if mode == 'missing': return
        response = dict(id=key, sha256=digest, module='cdcrd-tipologias', pid=123, ok=mode != 'native-error',
                        committed=False, result={'simulacion': True}, error='rolled back')
        if mode == 'wrong-hash': response['sha256'] = 'bad'
        if mode == 'wrong-module': response['module'] = 'other'
        if mode == 'wrong-pid': response['pid'] = 124
        (tmp_path / f'cdcrd-tipologias-{key}.result.json').write_text(json.dumps(response))
    monkeypatch.setattr(tipologias.bridge, 'llamar', read)
    monkeypatch.setattr(tipologias.bridge, 'llamar_con_aprobacion', dispatch)
    return calls


def test_hash_and_simulation_default(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path)
    result = tipologias.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='aplicar', corredor='AA', segmentos=SEGMENTS)
    assert result['ok'] and not result['committed'] and len(calls) == 1


def test_classification_is_a_read_request(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, accion='clasificar')
    result = tipologias.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='clasificar', corredor='AA', sonda_m=.5)
    assert result['ok'] and len(calls) == 1


@pytest.mark.parametrize('mode', ['timeout', 'missing', 'native-error', 'wrong-hash', 'wrong-module', 'wrong-pid'])
def test_uncertain_or_wrong_receipt_never_retries(mode, monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path, mode)
    with pytest.raises(tipologias.TipologiaError) as raised:
        tipologias.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='aplicar', corredor='AA', segmentos=SEGMENTS, timeout=.001)
    assert len(calls) == 1 and raised.value.receipt['id']


def test_busy_queue_and_wrong_document_prevent_dispatch(monkeypatch, tmp_path):
    calls = prepare(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        tipologias.ejecutar('C:\\other.dwg', 123, accion='aplicar', corredor='AA', segmentos=SEGMENTS)
    read = tipologias.bridge.llamar
    monkeypatch.setattr(tipologias.bridge, 'llamar', lambda m: dict(activas=[1]) if m == 'diag.cola' else read(m))
    with pytest.raises(RuntimeError):
        tipologias.ejecutar(str(tmp_path / 'copy.dwg'), 123, accion='aplicar', corredor='AA', segmentos=SEGMENTS)
    assert not calls


def test_unconfirmed_tool_does_not_dispatch(monkeypatch, tmp_path):
    registered = {}
    class Mcp:
        def tool(self):
            def save(fn): registered[fn.__name__] = fn; return fn
            return save
    tipologias.registrar(Mcp(), json.dumps)
    monkeypatch.setattr(tipologias, 'ejecutar', lambda *a, **k: pytest.fail('Not confirmed'))
    assert 'confirmar=True' in registered['aplicar_tipologia_por_tramo'](str(tmp_path / 'copy.dwg'), 123, 'AA', json.dumps(SEGMENTS))
    assert 'confirmar=True' in registered['reconstruir_tipologia_por_tramo'](str(tmp_path / 'copy.dwg'), 123, 'AA')
    assert set(registered) == {'clasificar_bordes_corredor', 'aplicar_tipologia_por_tramo', 'reconstruir_tipologia_por_tramo', 'verificar_tipologia_por_tramo'}
