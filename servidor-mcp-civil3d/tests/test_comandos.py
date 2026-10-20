import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import comandos


def tools(responses=None):
    registered, calls = {}, []
    results = iter(responses or [{'ticket': 'qa', 'finalizado': False}])

    class Mcp:
        def tool(self):
            def register(fn):
                registered[fn.__name__] = fn
                return fn
            return register

    def call(*args, **kwargs):
        calls.append((args, kwargs))
        return json.dumps(next(results))

    comandos.registrar(Mcp(), call, json.dumps)
    return registered, calls


def test_no_dispatch_without_confirmation_or_with_invalid_arguments():
    registered, calls = tools()
    fn = registered['ejecutar_comando_seguido']
    fn('LINE')
    for args, wait in [('{}', 0), ('[', 0), ('[]', -1), ('[]', 31)]:
        assert 'error' in json.loads(fn('LINE', args, wait, True))
    assert calls == []


def test_dispatch_once_and_poll_receipt(monkeypatch):
    registered, calls = tools([
        {'ticket': 'qa', 'finalizado': False},
        {'ticket': 'qa', 'finalizado': True, 'estado': 'terminado'},
    ])
    monkeypatch.setattr(comandos.time, 'sleep', lambda _: None)
    result = json.loads(registered['ejecutar_comando_seguido'](
        '_.LINE', '[[0,0,0],[10,0,0],""]', 1, True))
    assert result['estado'] == 'terminado'
    assert calls == [(('cmd.ejecutar', {'comando': '_.LINE',
                    'argumentos': [[0, 0, 0], [10, 0, 0], '']}), {'escribe': True}),
                     (('cmd.estado', {'ticket': 'qa'}), {})]


def test_zero_wait_returns_pending_ticket_without_resend():
    registered, calls = tools()
    result = json.loads(registered['ejecutar_comando_seguido']('_.REGEN', confirmar=True))
    assert not result['finalizado']
    assert len(calls) == 1


def test_status_is_read_only():
    registered, calls = tools()
    registered['consultar_comando']('existing')
    assert calls == [(('cmd.estado', {'ticket': 'existing'}), {})]
