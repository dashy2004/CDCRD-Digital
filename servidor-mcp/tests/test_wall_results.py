import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import oapi
from wall_results import display_rows, assess_reinforcement, required_cases


def test_display_preserves_null_not_applicable():
    assert display_rows([[], 1, ['Story', 'DCRatio'], 1, ['L1', None], 0]) == [{'Story':'L1', 'DCRatio':None}]


@pytest.mark.parametrize('value', [
    [[],1,['A'],1,[],0], [[],1,['A','A'],1,['1','2'],0],
    [[],1,['A'],1,[3],0], [[],1,['A'],1,['x'],1],
    [[],1,['A'],True,['x'],0], [[],1,['A'],1,['x'],False],
])
def test_display_rejects_bad_contract(value):
    with pytest.raises(ValueError):
        display_rows(value)


def test_required_cases_resolves_nested_combos():
    definitions = {'A':[1,[1],['B'],[1.0],0], 'B':[2,[0,0],['D','L'],[1.2,1.6],0]}
    assert required_cases(['A'], definitions.__getitem__) == ['D','L']


def test_required_cases_rejects_cycles():
    with pytest.raises(ValueError, match='ciclo'):
        required_cases(['A'], lambda _: [1,[1],['A'],[1.0],0])


def test_no_messages_is_not_reinforcement_adequacy():
    row = {'ReinfPcent':'0.49', 'CurrPcent':'0.21', 'WarnMsg':'No Message', 'ErrMsg':'No Message'}
    assert assess_reinforcement(row) == 'current_below_required'


@pytest.mark.parametrize('row', [{}, {'ReinfPcent':None,'CurrPcent':'0.21'}, {'ReinfPcent':'NaN','CurrPcent':'0.21'}])
def test_missing_or_nonfinite_ratio_not_a_pass(row):
    assert assess_reinforcement(row) == 'not_evaluated'


def test_reader_never_invokes_native_summary():
    source = ast.parse((ROOT/'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_shearwall_design')
    node.decorator_list = []
    scope = {'json':json, 'assess_reinforcement':assess_reinforcement}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'Etabs.py','exec'),scope)
    obj = SimpleNamespace(_wall_design_data=lambda: {'table':'test', 'rows':[{'ReinfPcent':'0.49','CurrPcent':'0.21'}]})
    result = json.loads(scope['get_shearwall_design'](obj))
    assert result['rows'][0]['reinforcement_comparison'] == 'current_below_required'


def test_empty_native_rebar_not_reported_as_complete():
    source = ast.parse((ROOT/'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_shearwall_rebar')
    node.decorator_list = []
    scope = {'json':json, 'oapi':oapi, 'EtabsError':RuntimeError}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'Etabs.py','exec'),scope)
    obj = SimpleNamespace(_wall_design_data=lambda: {'rows':[{'EdgeBar':'8'}]},
                          _model=lambda:SimpleNamespace(DesignShearWall=SimpleNamespace(GetRebar=lambda *a: [*([[]]*16),0])))
    result = json.loads(scope['get_shearwall_rebar'](obj))
    assert result['complete_detailing'] is False
    assert result['native_rebar_count'] == 0


@pytest.mark.parametrize('state', [1, 2, 3, None])
def test_incomplete_case_stops_before_reading_wall_summary(state):
    source = ast.parse((ROOT/'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_wall_design_data')
    scope = {'json':json,'oapi':oapi,'display_rows':display_rows,
             'required_cases':required_cases,'EtabsError':RuntimeError}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'Etabs.py','exec'),scope)
    def table(name, *args):
        assert name == 'Shear Wall Design Load Combination Data', 'Unsafe summary read'
        return [[],1,['ComboType','ComboName'],1,['Strength','DWal'],0]
    status = [0,[],[],0] if state is None else [1,['Dead'],[state],0]
    model = SimpleNamespace(DatabaseTables=SimpleNamespace(GetTableForDisplayArray=table),
                            RespCombo=SimpleNamespace(GetCaseList=lambda _: [1,[0],['Dead'],[1.4],0]),
                            Analyze=SimpleNamespace(GetCaseStatus=lambda:status))
    obj = SimpleNamespace(_model=lambda:model, _require_wall_design_results=lambda:'summary')
    with pytest.raises(RuntimeError, match='casos sin resultados'):
        scope['_wall_design_data'](obj)


@pytest.mark.parametrize('definition', [
    [1,[2],['D'],[1.0],0], [1,[True],['D'],[1.0],0],
    [2,[0],['D'],[1.0],0], [1,[0],['D'],[float('nan')],0],
])
def test_required_cases_rejects_malformed_definitions(definition):
    with pytest.raises(ValueError):
        required_cases(['A'], lambda _: definition)
