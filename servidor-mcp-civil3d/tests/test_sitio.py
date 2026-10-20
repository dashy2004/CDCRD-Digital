import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import sitio


@pytest.mark.parametrize('value', ['{}', '[', '[]', '[[0,100]]', '[[0,100],[0,101]]',
    '[[10,100],[0,101]]', '[[0,100],[10,NaN]]', '[[false,100],[10,101]]',
    '[[0,100],[10,"101"]]', '[[0,100],[10,101,102]]'])
def test_rejects_invalid_pvis(value):
    with pytest.raises(ValueError):
        sitio.parsear_pvis(value)


def test_preserves_order_and_values():
    assert sitio.parsear_pvis('[[0,100],[50,101],[100,99]]') == [[0,100],[50,101],[100,99]]


def test_confirmations_and_single_dispatch():
    registered, calls = {}, []
    class Mcp:
        def tool(self):
            def add(fn):
                registered[fn.__name__] = fn
                return fn
            return add
    sitio.registrar(Mcp(), lambda *a, **k: calls.append((a,k)), json.dumps)
    registered['crear_parcela_desde_polilinea']('AAA','lot','new-site')
    registered['crear_alineamiento_desde_polilinea']('BBB','axis')
    registered['crear_perfil_por_pvi']('axis','design','[[0,100],[10,101]]')
    registered['crear_perfil_por_pvi']('axis','design','[[0,100],[0,101]]', confirmar=True)
    assert not calls
    registered['crear_perfil_por_pvi']('axis','design','[[0,100],[10,101]]', simular=True, confirmar=True)
    assert calls == [(('civil.perfil_pvi', {'alineamiento':'axis','nombre':'design',
        'pvis':[[0,100],[10,101]], 'simular':True}), {'escribe':True})]
