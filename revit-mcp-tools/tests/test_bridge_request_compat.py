import importlib.util
import inspect
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('bridge_request_compat',
    Path(__file__).parents[1]/'maintenance/bridge_request_compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


@pytest.mark.parametrize('value', [b'{"code":"print(1)"}', bytearray(b'{"code":"print(1)"}'),
    '{"code":"print(1)"}', {'code':'print(1)'}])
def test_payload_representations(value):
    assert compat.parse_payload(value) == {'code':'print(1)'}


@pytest.mark.parametrize('value', [[], None, 3, '[]', 'null', b'\xff', b'{'])
def test_rejects_nonobjects_or_invalid_encoding(value):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        compat.parse_payload(value)


def test_unicode_and_no_code_execution():
    assert compat.parse_payload(json.dumps({'code':'raise Exception("never run")'}))['code'].startswith('raise')
    assert compat.parse_payload('{"description":"Sección"}'.encode('utf-8'))['description'] == 'Sección'


def test_patch_is_exact_and_refuses_repeat():
    source = 'import json\n\ndef register_code_execution_routes(api):\n    def handler(request):\n        try:\n'+compat.OLD+'\n            return data\n        except Exception:\n            raise\n'
    patched = compat.patch_source(source, inspect.getsource(compat.parse_payload))
    assert patched.count(compat.NEW) == 1
    with pytest.raises(ValueError):
        compat.patch_source(patched, inspect.getsource(compat.parse_payload))
    with pytest.raises(ValueError):
        compat.patch_source(source.replace('request.data','request.body'), inspect.getsource(compat.parse_payload))
