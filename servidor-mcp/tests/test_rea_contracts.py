"""Offline contract tests: no COM server, CAD files or live model access."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import oapi
import oapi_catalog

DRIFT_FIELDS = [('Story', str), ('LoadCase', str), ('StepType', str),
                ('StepNum', float), ('Direction', str), ('Drift', float),
                ('Label', str), ('X', float), ('Y', float), ('Z', float)]


def drift_result(drift=0.003):
    # Story/case resemble directions, and StepNum/coordinates resemble drift.
    return [1, ['X'], ['Y'], ['Step'], [0.125], ['UX'], [drift],
            ['P1'], [0.01], [0.02], [3.0], 0]


@pytest.mark.parametrize('response', [None, True, 'ok', [], [False]])
def test_unknown_status_fails_without_retry(response):
    attempted = []
    owner = SimpleNamespace(first=lambda: response, second=lambda: attempted.append(1))
    with pytest.raises(oapi.OapiError, match='sin codigo'):
        oapi.call(owner, [('first', ()), ('second', ())])
    assert not attempted


def test_nonzero_status_is_error():
    with pytest.raises(oapi.OapiError, match='ret=7'):
        oapi.call_checked(SimpleNamespace(run=lambda: 7), 'run', ())


@pytest.mark.parametrize('drift', [0.0, -0.004, 1.5])
def test_drift_by_contract_not_magnitude(drift):
    rows = oapi.result_rows(object(), 'StoryDrifts', drift_result(drift), DRIFT_FIELDS)
    assert rows[0]['Drift'] == drift
    assert rows[0]['Direction'] == 'UX'
    assert rows[0]['StepNum'] == 0.125


def test_runtime_typelib_order():
    names = ['NumberResults', *[n for n, _ in DRIFT_FIELDS]]
    values = drift_result()
    names[4], names[6] = names[6], names[4]
    values[4], values[6] = values[6], values[4]
    spec = (int, 'StoryDrifts', [object] * 12,
            [(2, n) for n in names] + [(10, 'pRetVal')], [], '')
    owner = type('Results', (), {'_methods_': [spec]})()
    assert oapi.result_rows(owner, 'StoryDrifts', values, DRIFT_FIELDS)[0]['Drift'] == 0.003


@pytest.mark.parametrize('change', ['length', 'nan', 'bool', 'status', 'count', 'shape'])
def test_malformed_result_rejected(change):
    result = drift_result()
    if change == 'length': result[6] = []
    if change == 'nan': result[6] = [float('nan')]
    if change == 'bool': result[6] = [True]
    if change == 'status': result[-1] = 1
    if change == 'count': result[0] = -1
    if change == 'shape': result.pop(7)
    with pytest.raises(oapi.OapiError):
        oapi.result_rows(object(), 'StoryDrifts', result, DRIFT_FIELDS)


def test_empty_results():
    assert oapi.result_rows(object(), 'StoryDrifts', [0] + [None]*10 + [0], DRIFT_FIELDS) == []


def test_mesh_object_nullable_only_when_declared():
    raw = [1, [None], ['~17'], 0]
    fields = [('Obj', str), ('Elm', str)]
    with pytest.raises(oapi.OapiError):
        oapi.result_rows(object(), 'JointDispl', raw, fields)
    assert oapi.result_rows(object(), 'JointDispl', raw, fields,
                            nullable_fields=('Obj',)) == [{'Obj':None, 'Elm':'~17'}]
    raw[2] = [None]
    with pytest.raises(oapi.OapiError):
        oapi.result_rows(object(), 'JointDispl', raw, fields, nullable_fields=('Obj',))


@pytest.fixture
def etabs_unit():
    # Compile the two production method bodies, excluding the Windows imports
    # and STA decorator. This tests adapters, not COM marshalling/integration.
    source = ast.parse((ROOT / 'src' / 'Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in {'get_story_drifts', 'get_joint_displacements'}]
    for method in methods:
        method.decorator_list = []
    units = next(n for n in source.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'PRESET_UNITS' for t in n.targets))
    scope = {'oapi': oapi, 'json': json, 'EtabsError': RuntimeError}
    exec(compile(ast.Module(body=[units, *methods], type_ignores=[]), str(ROOT / 'src' / 'Etabs.py'), 'exec'), scope)
    return scope


def test_story_adapter_uses_contract(etabs_unit):
    model = SimpleNamespace(Results=SimpleNamespace(StoryDrifts=drift_result))
    obj = SimpleNamespace(_model=lambda: model, _select_output_cases=lambda *a: None)
    result = etabs_unit['get_story_drifts'](obj)
    assert 'deriva 0.00300' in result and 'dir UX' in result
    assert 'paso Step 0.125' in result


def test_joint_adapter_units_pagination_and_cases(etabs_unit):
    selected = []
    raw = [2, ['P1','P1'], ['1','1'], ['Dead','Live'], ['Step','Step'], [0,1],
           [0.1,0.2], [0.3,0.4], [0.5,0.6], [0.01,0.02], [0.03,0.04], [0.05,0.06], 0]
    model = SimpleNamespace(Results=SimpleNamespace(JointDispl=lambda n,i: raw), GetPresentUnits=lambda: 6)
    obj = SimpleNamespace(_model=lambda: model, _select_output_cases=lambda m,c: selected.append(c))
    result = json.loads(etabs_unit['get_joint_displacements'](obj, 'P1', cases=['Dead'], max_results=1))
    assert selected == [['Dead']]
    assert result['length_unit'] == 'm' and result['rotation_unit'] == 'rad'
    assert result['next_offset'] == 1 and result['total_results'] == 2
    assert result['results'][0]['U1'] == 0.1 and result['results'][0]['R3'] == 0.05


@pytest.mark.parametrize('kwargs', [{'name':''}, {'name':'P1','item_type':4},
                                   {'name':'P1','max_results':0}, {'name':'P1','offset':-1}])
def test_invalid_inputs_do_not_connect(etabs_unit, kwargs):
    obj = SimpleNamespace(_model=lambda: pytest.fail('must not connect'))
    with pytest.raises(ValueError):
        etabs_unit['get_joint_displacements'](obj, **kwargs)


def test_catalog_verified_static_scope_and_search():
    data = oapi_catalog._catalog()
    assert data['method_count'] == len(data['methods']) == 4861
    assert not data['runtime_verified']
    found = json.loads(oapi_catalog.search_oapi_catalog('cAnalysisResults JointDispl'))
    assert found['total_matches'] >= 1
    assert any(m['name'] == 'JointDispl' for m in found['methods'])
    assert json.loads(oapi_catalog.search_oapi_catalog('StoryForces'))['total_matches'] == 0
    page = json.loads(oapi_catalog.search_oapi_catalog(limit=1))
    assert len(page['methods']) == 1 and page['next_offset'] == 1


@pytest.mark.parametrize('kwargs', [{'limit':0}, {'limit':True}, {'offset':-1}])
def test_catalog_pagination_validation(kwargs):
    with pytest.raises(ValueError): oapi_catalog.search_oapi_catalog(**kwargs)


def test_server_registers_both_new_tools():
    source = (ROOT / 'src' / 'server.py').read_text(encoding='utf-8')
    assert 'mcp.tool()(etabs.get_joint_displacements)' in source
    assert 'mcp.tool()(search_oapi_catalog)' in source


def test_catalog_builder_rejects_mismatched_evidence():
    spec = importlib.util.spec_from_file_location('build_rea_catalog', ROOT / 'tools' / 'build_rea_catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match='different DLLs'):
        module.build_catalog({'normalized_result': {'artifact': {'sha256':'a'}}},
                             {'normalized_result': {'artifact': {'sha256':'b'}}}, '')
