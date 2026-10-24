"""Seleccion de instancia hermetica: nunca carga COM ni archivos de modelo."""

import importlib.util
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from config import Config
from Safe import Safe, SafeError


@pytest.fixture
def helper(monkeypatch):
    generated = types.ModuleType('comtypes.gen')
    typelib = types.ModuleType('comtypes.gen.SAFEv1')
    typelib.cHelper = object()
    generated.SAFEv1 = typelib
    monkeypatch.setitem(sys.modules, 'comtypes.gen', generated)
    monkeypatch.setitem(sys.modules, 'comtypes.gen.SAFEv1', typelib)
    helper = MagicMock(name='cHelper')
    helper.QueryInterface.return_value = helper
    helper.GetObjectProcess.return_value.GetOAPIVersionNumber.return_value = 2.0
    with patch('Safe.comtypes.client.CreateObject', return_value=helper) as create, \
         patch('Safe.comtypes.client.GetActiveObject', side_effect=AssertionError('ROT prohibido')) as rot:
        yield helper, create, rot, typelib.cHelper


def test_explicit_pid_uses_only_requested_process_and_caches_reference(helper):
    com, create, rot, interface = helper
    safe = Safe(process_id=31748, auto_start=True)
    safe._connect()
    safe._connect()
    create.assert_called_once_with('SAFEv1.Helper')
    com.QueryInterface.assert_called_once_with(interface)
    com.GetObjectProcess.assert_called_once_with('CSI.SAFE.API.ETABSObject', 31748)
    assert safe.SapModel is com.GetObjectProcess.return_value.SapModel
    assert safe.version_string == '2.0'
    rot.assert_not_called()
    com.GetObject.assert_not_called()
    com.CreateObject.assert_not_called()
    com.CreateObjectProgID.assert_not_called()
    com.GetObjectProcess.return_value.ApplicationStart.assert_not_called()


def test_explicit_pid_honors_configured_helper_and_progid(helper):
    com, create, _rot, _interface = helper
    Safe(process_id=7, prog_id='custom.safe', helper_prog_id='custom.helper')._connect()
    create.assert_called_once_with('custom.helper')
    com.GetObjectProcess.assert_called_once_with('custom.safe', 7)


@pytest.mark.parametrize('failure', ['helper', 'interface', 'lookup', 'empty', 'model'])
def test_explicit_pid_failure_never_falls_back_or_auto_starts(helper, failure):
    com, create, rot, _interface = helper
    error = RuntimeError('instancia no disponible')
    if failure == 'helper':
        create.side_effect = error
    elif failure == 'interface':
        com.QueryInterface.side_effect = error
    elif failure == 'lookup':
        com.GetObjectProcess.side_effect = error
    elif failure == 'empty':
        com.GetObjectProcess.return_value = None
    else:
        com.GetObjectProcess.return_value.SapModel.GetModelFilename.side_effect = error
    safe = Safe(process_id=31748, auto_start=True)
    with pytest.raises(SafeError, match='PID SAFE 31748.*no se usara otra instancia'):
        safe._connect()
    assert safe.SapModel is None
    assert safe._safe_object is None
    rot.assert_not_called()
    com.GetObject.assert_not_called()
    com.CreateObject.assert_not_called()
    com.CreateObjectProgID.assert_not_called()
    if com.GetObjectProcess.return_value is not None:
        com.GetObjectProcess.return_value.ApplicationStart.assert_not_called()


def test_invalidated_reference_reconnects_only_to_same_pid(helper):
    com, _create, rot, _interface = helper
    safe = Safe(process_id=31748)
    safe._connect()
    safe.SapModel.GetModelFilename.side_effect = [RuntimeError('desconectado'), 'test.fdb']
    safe._connect()
    assert com.GetObjectProcess.call_count == 2
    assert all(call.args == ('CSI.SAFE.API.ETABSObject', 31748)
               for call in com.GetObjectProcess.call_args_list)
    rot.assert_not_called()


def test_no_pid_preserves_legacy_active_instance_connection():
    obj = MagicMock()
    with patch('Safe.comtypes.client.GetActiveObject', return_value=obj) as rot, \
         patch('Safe.comtypes.client.CreateObject') as create:
        safe = Safe()
        safe._connect()
    assert safe.process_id == 0
    assert safe.SapModel is obj.SapModel
    rot.assert_called_once_with('CSI.SAFE.API.SapObject')
    create.assert_not_called()


@pytest.mark.parametrize('invalid', [-1, True, False, 1.5, '31748', None])
def test_constructor_rejects_invalid_pid_without_connecting(invalid):
    with pytest.raises(ValueError, match='process_id'):
        Safe(process_id=invalid)


def test_config_missing_pid_defaults_to_zero(monkeypatch):
    monkeypatch.delenv('SAFE_PROCESS_ID', raising=False)
    with patch('builtins.open', mock_open(read_data='{"safe": {}}')):
        config = Config()
    assert config.processId == 0


@pytest.mark.parametrize('raw, expected', [(0, 0), (31748, 31748), ('31748', 31748)])
def test_config_pid_is_accepted(monkeypatch, raw, expected):
    monkeypatch.delenv('SAFE_PROCESS_ID', raising=False)
    config = Config.__new__(Config)
    config.data = {'safe': {'process_id': raw}}
    assert config.processId == expected


def test_environment_pid_overrides_config(monkeypatch):
    monkeypatch.setenv('SAFE_PROCESS_ID', '31748')
    config = Config.__new__(Config)
    config.data = {'safe': {'process_id': 42}}
    assert config.processId == 31748


@pytest.mark.parametrize('raw', [-1, True, 1.5, None, '', '-1', '1.5', 'PID'])
def test_config_rejects_invalid_pid(monkeypatch, raw):
    monkeypatch.delenv('SAFE_PROCESS_ID', raising=False)
    config = Config.__new__(Config)
    config.data = {'safe': {'process_id': raw}}
    with pytest.raises(ValueError, match='SAFE_PROCESS_ID'):
        _ = config.processId


def test_bad_environment_does_not_fall_back_to_valid_config(monkeypatch):
    monkeypatch.setenv('SAFE_PROCESS_ID', 'invalid')
    config = Config.__new__(Config)
    config.data = {'safe': {'process_id': 42}}
    with pytest.raises(ValueError, match='SAFE_PROCESS_ID'):
        _ = config.processId


def test_server_passes_configured_pid_to_lazy_safe_constructor(monkeypatch):
    fake_config = types.ModuleType('config')
    fake_config.Config = MagicMock(return_value=types.SimpleNamespace(
        autoStart=False, exePath='', progId='', helperProgId='', processId=31748,
        serverName='test', serverVersion='test'))
    fake_safe = types.ModuleType('Safe')
    fake_safe.Safe = MagicMock()
    fake_mcp = types.ModuleType('mcp.server.fastmcp')
    fake_mcp.FastMCP = MagicMock()
    fake_mcp.FastMCP.return_value.tool.return_value = lambda fn: fn
    fake_mcp.FastMCP.return_value.resource.return_value = lambda fn: fn
    monkeypatch.setitem(sys.modules, 'config', fake_config)
    monkeypatch.setitem(sys.modules, 'Safe', fake_safe)
    monkeypatch.setitem(sys.modules, 'mcp.server.fastmcp', fake_mcp)
    path = Path(__file__).parents[1] / 'src' / 'server.py'
    spec = importlib.util.spec_from_file_location('_safe_server_pid_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch('logging.FileHandler', return_value=logging.NullHandler()), \
         patch('logging.basicConfig'):
        spec.loader.exec_module(module)
    fake_safe.Safe.assert_called_once_with(
        auto_start=False, exe_path='', prog_id='', helper_prog_id='', process_id=31748)
