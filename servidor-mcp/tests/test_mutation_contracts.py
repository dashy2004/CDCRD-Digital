import ast
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import oapi


@pytest.fixture
def methods():
    source = ast.parse((ROOT / 'src/Etabs.py').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Etabs')
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef)
             and n.name in {'delete_object','set_pier_label','set_table_data',
                            '_require_wall_design_results','set_rigid_diaphragm','call_oapi','close_model',
                            'get_concrete_design_joint','add_time_history_case'}]
    for n in nodes: n.decorator_list = []
    scope = {'oapi':oapi, 'EtabsError':RuntimeError, 'Any':object,'logger':logging.getLogger(__name__),
             'PRESET_UNITS':list(range(16))}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'Etabs.py', 'exec'), scope)
    return scope


def test_delete_connected_point_refused(methods):
    owner = SimpleNamespace(GetConnectivity=lambda _: [1,[2],['frame'],[1],0],
                            DeleteSpecialPoint=lambda *a: pytest.fail('connected point deleted'))
    obj = SimpleNamespace(_model=lambda: SimpleNamespace(PointObj=owner), _OBJ_NAMESPACE={'point':'PointObj'})
    with pytest.raises(RuntimeError, match='conectado'): methods['delete_object'](obj,'point','P')


def test_isolated_point_uses_special_delete_and_rereads(methods):
    called=[]
    owner=SimpleNamespace(GetConnectivity=lambda _: [0,[],[],[],0], DeleteSpecialPoint=lambda *a: called.append(a) or 0)
    obj=SimpleNamespace(_model=lambda: SimpleNamespace(PointObj=owner), _OBJ_NAMESPACE={'point':'PointObj'}, _name_list=lambda *a: [])
    assert 'borrado' in methods['delete_object'](obj,'point','P')
    assert called == [('P',0)]


def test_pier_created_before_assignment(methods):
    calls=[]
    model=SimpleNamespace(PierLabel=SimpleNamespace(SetPier=lambda n: calls.append(('create',n)) or 0),
                          AreaObj=SimpleNamespace(SetPier=lambda *a: calls.append(('assign',*a)) or 0))
    obj=SimpleNamespace(_model=lambda:model, _name_list=lambda *a: [])
    methods['set_pier_label'](obj,['A'],'PIER')
    assert calls == [('create','PIER'),('assign','A','PIER',0)]


@pytest.mark.parametrize('fatal,errors', [(1,0),(0,1)])
def test_table_import_errors_are_not_success(methods, fatal, errors):
    database=SimpleNamespace(GetTableForEditingArray=lambda *a: [1,['Name'],1,['A'],0],
                             SetTableForEditingArray=lambda *a: 0,
                             ApplyEditedTables=lambda *a: [fatal,errors,0,0,'bad row',0])
    obj=SimpleNamespace(_model=lambda:SimpleNamespace(DatabaseTables=database))
    with pytest.raises(RuntimeError, match='parciales'):
        methods['set_table_data'](obj,'Test',['Name'],[['A']])


def test_wall_design_guard_prevents_native_call_without_results(methods):
    db=SimpleNamespace(GetAvailableTables=lambda: [1,['Shear Wall Design Preferences - ACI 318-19'],['prefs'],[1],0])
    obj=SimpleNamespace(_model=lambda:SimpleNamespace(DatabaseTables=db))
    with pytest.raises(RuntimeError, match='No hay resultados'):
        methods['_require_wall_design_results'](obj)


def test_wall_design_guard_accepts_existing_summary(methods):
    db=SimpleNamespace(GetAvailableTables=lambda: [1,['Shear Wall Pier Design Summary - ACI 318-19'],['summary'],[0],0])
    obj=SimpleNamespace(_model=lambda:SimpleNamespace(DatabaseTables=db))
    methods['_require_wall_design_results'](obj)


def test_diaphragm_mismatch_does_not_assign(methods):
    definition=SimpleNamespace(GetNameList=lambda: [1,['D1'],0],GetDiaphragm=lambda _: [False,0])
    obj=SimpleNamespace(_model=lambda:SimpleNamespace(Diaphragm=definition),
                        _read_points=lambda: pytest.fail('must reject before assignments'))
    with pytest.raises(RuntimeError,match='otra rigidez'):
        methods['set_rigid_diaphragm'](obj,'D1',3,True)


@pytest.mark.parametrize('value',[6,False,'test.edb'])
def test_generic_value_getter_is_not_status(methods,value):
    obj=SimpleNamespace(_model=lambda:SimpleNamespace(GetValue=lambda:value))
    result=json.loads(methods['call_oapi'](obj,'','GetValue',returns_status=False))
    assert result['ret'] is None and result['value'] == value


def test_close_saves_and_initializes_before_newblank(methods):
    calls=[]
    model=SimpleNamespace(GetModelFilename=lambda:'test.edb',GetPresentUnits=lambda:6,
                          InitializeNewModel=lambda units: calls.append(('init',units)) or 0,
                          File=SimpleNamespace(Save=lambda:calls.append('save') or 0,
                                               NewBlank=lambda:calls.append('blank') or 0))
    obj=SimpleNamespace(_model=lambda:model)
    methods['close_model'](obj,True)
    assert calls == ['save',('init',6),'blank']


def test_roof_name_cannot_exempt_joint_failure(methods):
    design=SimpleNamespace(GetSummaryResultsJoint=lambda *a:
        [1,['ROOF-C1'],['C'],[1.01],['C'],[.5],['C'],[.5],['C'],[.5],[''],[''],0])
    obj=SimpleNamespace(_model=lambda:SimpleNamespace(DesignConcrete=design))
    result=methods['get_concrete_design_joint'](obj,'ROOF-C1',0,'ROOF')
    assert 'JS>1' in result and 'sin exencion' in result
    assert 'omitible' not in result


def test_unvalidated_nonlinear_history_requires_explicit_optin_before_com(methods):
    obj=SimpleNamespace(_model=lambda:pytest.fail('must reject before connecting'))
    with pytest.raises(RuntimeError,match='antes de modificar'):
        methods['add_time_history_case'](obj,'TH','pulse',nonlinear=True)
