import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from plataformas import parsear_cotas, registrar


@pytest.mark.parametrize('value', ['[]', '[true]', '[null]', '["100"]', '[NaN]', '[Infinity]', '{}'])
def test_invalid_cotas(value):
    with pytest.raises((ValueError, TypeError)):
        parsear_cotas(value)


def test_tool_confirmation_and_payload():
    tools, calls = {}, []
    class Mcp:
        def tool(self):
            def register(fn):
                tools[fn.__name__] = fn
                return fn
            return register
    def call(method, params, **kwargs):
        calls.append((method, params, kwargs))
        return 'ok'
    registrar(Mcp(), call, json.dumps)
    fn = tools['crear_feature_line']
    assert 'confirmar' in fn('ABC', 'QA', '[100]') and not calls
    assert fn('ABC', 'QA', '[100,101]', confirmar=True) == 'ok'
    assert calls[-1] == ('civil.feature_line', {'polilinea': 'ABC', 'nombre': 'QA',
                         'elevaciones': [100., 101.], 'simular': False}, {'escribe': True})
    fn('ABC', 'QA', '[null]', confirmar=True)
    assert len(calls) == 1
    tools['crear_superficie_desde_feature_lines']('A', 'TIN', 'B', simular=True, confirmar=True)
    assert calls[-1][0] == 'civil.superficie_feature_lines'
    assert calls[-1][1]['simular'] is True and calls[-1][1]['linea_interior'] == 'B'
