"""Instance selection and text-import guards must fail closed."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from config import Config


@pytest.mark.parametrize('value,expected', [(0, 0), (123, 123), ('123', 123)])
def test_pid_config(value, expected, monkeypatch):
    monkeypatch.delenv('ETABS_PROCESS_ID', raising=False)
    config = Config.__new__(Config)
    config.data = {'fea': {'process_id': value}}
    assert config.processId == expected


@pytest.mark.parametrize('value', [-1, True, 1.5, '', 'abc', '-5'])
def test_bad_pid_config(value, monkeypatch):
    monkeypatch.delenv('ETABS_PROCESS_ID', raising=False)
    config = Config.__new__(Config)
    config.data = {'fea': {'process_id': value}}
    with pytest.raises(ValueError): _ = config.processId


def test_environment_overrides_config(monkeypatch):
    config = Config.__new__(Config)
    config.data = {'fea': {'process_id': 123}}
    monkeypatch.setenv('ETABS_PROCESS_ID', '456')
    assert config.processId == 456


@pytest.mark.parametrize('method,args', [
    ('open_model', ['synthetic.e2k']), ('open_model', ['synthetic.$et']),
    ('_set_stories_via_texto', [['Test'], [3.0], 0.0])])
def test_unpinned_text_import_never_touches_model(method, args):
    source = ast.parse((ROOT / 'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
    node.decorator_list = []
    scope = {'EtabsError': RuntimeError}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'Etabs.py', 'exec'), scope)
    obj = SimpleNamespace(process_id=0, _model=lambda: pytest.fail('must not connect'))
    with pytest.raises(RuntimeError, match='process_id'):
        scope[method](obj, *args)
