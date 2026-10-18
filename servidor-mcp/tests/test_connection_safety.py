"""Connection-policy tests without starting ETABS or importing COM."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def adapter():
    source = ast.parse((Path(__file__).parents[1] / 'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                and n.name in {'__init__', '_connect', '_launch_instance', '_model', 'reconnect'}]
    for node in cls.body:
        node.decorator_list = []
    attempts = []
    helper = SimpleNamespace(GetObjectProcess=lambda *a: None)
    client = SimpleNamespace(CreateObject=lambda *a: helper,
                             GetActiveObject=lambda *a: attempts.append('ROT'))
    scope = {'comtypes': SimpleNamespace(client=client), 'EtabsError': RuntimeError,
             'PROG_ID': 'test.etabs', 'logger': logging.getLogger('test'),
             'os': SimpleNamespace(path=SimpleNamespace(isfile=lambda p: False))}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'Etabs.py', 'exec'), scope)
    return scope['Etabs'], helper, attempts


def test_missing_pinned_process_never_falls_back(adapter):
    cls, helper, attempts = adapter
    obj = cls(process_id=123)
    with pytest.raises(RuntimeError, match='123'):
        obj._connect()
    assert not attempts


def test_pinned_process_connects_exact_pid(adapter):
    cls, helper, attempts = adapter
    requested = []
    model = SimpleNamespace(GetModelFilename=lambda: 'synthetic.edb')
    api = SimpleNamespace(SapModel=model, GetOAPIVersionNumber=lambda: 2.016)
    def get_process(progid, pid):
        requested.append(pid)
        return api
    helper.GetObjectProcess = get_process
    obj = cls(process_id=123)
    assert obj._model() is model
    assert requested == [123] and not attempts


def test_pinned_process_cannot_auto_launch(adapter):
    cls, helper, attempts = adapter
    obj = cls(process_id=123, auto_start=True)
    with pytest.raises(RuntimeError): obj._launch_instance()
    with pytest.raises(RuntimeError): obj.reconnect(launch_if_missing=True)
    assert not attempts


@pytest.mark.parametrize('pid', [-1, True, '123', 1.5])
def test_invalid_pid_rejected(adapter, pid):
    cls, _, _ = adapter
    with pytest.raises(ValueError): cls(process_id=pid)
