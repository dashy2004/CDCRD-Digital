import importlib.util
from pathlib import Path
import types
import sys
import io
import json

import pytest


@pytest.fixture
def server(monkeypatch):
    # Registration is irrelevant to these tests; no MCP session is opened.
    fake = types.ModuleType('mcp.server.fastmcp')
    class FastMCP:
        def __init__(self, *args, **kwargs):
            pass
        def tool(self, *args, **kwargs):
            return lambda fn: fn
    fake.FastMCP = FastMCP
    monkeypatch.setitem(sys.modules, 'mcp.server.fastmcp', fake)
    spec = importlib.util.spec_from_file_location('transport', Path(__file__).parents[1]/'src/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, data=b'{"host":"Autodesk Revit 2027", "session_id":"sample"}'):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return self.data


def test_discovery_uses_only_http_status_never_revit_code(server, monkeypatch):
    calls = []
    def open_url(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data, timeout))
        return Response()
    monkeypatch.setattr(server.urllib.request, 'urlopen', open_url)
    monkeypatch.setattr(server, '_post', lambda *args: pytest.fail('Native call during discovery'))
    assert server._port() == 48884
    assert calls == [('http://127.0.0.1:48884/routes/status', 'GET', None, 3)]


def test_cached_port_first_and_dead_cache_is_not_reported_healthy(server, monkeypatch):
    server._port_cache = 48887
    calls = []
    def open_url(request, timeout):
        calls.append(request.full_url)
        if ':48887/' in request.full_url:
            raise TimeoutError()
        return Response()
    monkeypatch.setattr(server.urllib.request, 'urlopen', open_url)
    assert server._port() == 48884
    assert calls[0] == 'http://127.0.0.1:48887/routes/status'


def test_malformed_response_does_not_count_as_available_native_api(server, monkeypatch):
    monkeypatch.setattr(server.urllib.request, 'urlopen', lambda *a, **k: Response(b'[]'))
    with pytest.raises(RuntimeError, match='/routes/status'):
        server._port()
    assert server._port_cache is None


def test_execution_uses_json_content_type_and_no_automatic_transaction(server, monkeypatch):
    calls = []
    def open_url(request, timeout):
        calls.append(request)
        assert request.get_header('Content-type') == 'application/json; charset=utf-8'
        assert json.loads(request.data) == {'code': 'print(1)', 'description': 'probe', 'use_transaction': False}
        return Response(b'{"status":"success"}')
    monkeypatch.setattr(server.urllib.request, 'urlopen', open_url)
    assert server._post(48884, 'print(1)', 'probe') == {'status': 'success'}
    assert len(calls) == 1


def test_http_failure_is_not_retried_or_returned_with_attempted_code(server, monkeypatch):
    calls = []
    def open_url(request, timeout):
        calls.append(request)
        raise server.urllib.error.HTTPError(request.full_url, 500, 'failure', {},
            io.BytesIO(b'{"error":"handler failed","code_attempted":"private source"}'))
    monkeypatch.setattr(server.urllib.request, 'urlopen', open_url)
    result = server._post(48884, 'print(1)', 'probe')
    assert result == {'error': 'HTTP 500', 'message': 'handler failed', 'retry_safe': False}
    assert len(calls) == 1 and 'private source' not in json.dumps(result)
