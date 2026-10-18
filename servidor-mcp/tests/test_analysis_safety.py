"""The success message must mean selected cases finished, not just ret=0."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
import oapi


@pytest.fixture
def run_analysis():
    source = ast.parse((Path(__file__).parents[1] / 'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run_analysis')
    method.decorator_list = []
    scope = {'oapi': oapi, 'EtabsError': RuntimeError,
             'os': SimpleNamespace(path=SimpleNamespace(isfile=lambda p: p == 'test.edb'))}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'Etabs.py', 'exec'), scope)
    return scope['run_analysis']


def model(filename='test.edb', selected=True, status=4):
    calls = []
    api = SimpleNamespace(
        GetRunCaseFlag=lambda: [2, ['Test', 'NotSelected'], [selected, False], 0],
        RunAnalysis=lambda: calls.append('run') or 0,
        GetCaseStatus=lambda: [2, ['Test', 'NotSelected'], [status, 1], 0])
    obj = SimpleNamespace(_model=lambda: SimpleNamespace(GetModelFilename=lambda: filename, Analyze=api))
    return obj, calls


@pytest.mark.parametrize('filename', ['', None, '(Untitled)'])
def test_unsaved_does_not_run(run_analysis, filename):
    obj, calls = model(filename=filename)
    with pytest.raises(RuntimeError, match='guardado'): run_analysis(obj)
    assert not calls


def test_no_selected_cases_does_not_run(run_analysis):
    obj, calls = model(selected=False)
    with pytest.raises(RuntimeError, match='seleccionad'): run_analysis(obj)
    assert not calls


@pytest.mark.parametrize('status', [1, 2, 3, 5])
def test_zero_return_but_unfinished_is_not_success(run_analysis, status):
    obj, calls = model(status=status)
    with pytest.raises(RuntimeError, match='Test'): run_analysis(obj)
    assert calls == ['run']


def test_unselected_cases_do_not_fail_success(run_analysis):
    obj, calls = model()
    assert '1 caso' in run_analysis(obj)
    assert calls == ['run']
