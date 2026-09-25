"""Contratos de las 31 tools base y las 18 de Claude (incluye una [X]).

Fuentes: OAPI-SAFE-real.md §2/6/7 y wrapper SAFEv1. Las tuplas son py->,
no valores escalares comodin. Estos tests prueban el cliente, NO prueban SAFE.
"""
import ast
from pathlib import Path
from unittest.mock import call, patch

import pytest
from Safe import Safe, SafeError
import oapi


# nombre, argumentos de tool, metodo COM que debe recibirlos, argumentos COM.
# Arrays [in,out] explicitamente vacios se mantienen en los lectores previos
# verificados; los nuevos lectores usan los argumentos opcionales del wrapper.
CASES = [
    ('get_model_info', (), 'GetVersion', ()),
    ('get_units', (), 'GetPresentUnits', ()),
    ('set_units', ('kN, m, C',), 'SetPresentUnits', (6,)),
    ('save_model', ('salida.fdb',), 'File.Save', ('salida.fdb',)),
    ('refresh_view', (), 'View.RefreshView', (0,False)),
    ('describe_oapi', ('AreaObj','Get'), None, ()),
    ('get_points', (), 'PointObj.GetAllPoints', ()),
    ('get_areas', (), 'AreaObj.GetAllAreas', ()),
    ('create_area_by_coordinates', ([1.,4.,7.],[2.,5.,8.],[3.,6.,9.],'S1'), 'AreaObj.AddByCoord', (3,[1.,4.,7.],[2.,5.,8.],[3.,6.,9.],'','S1')),
    ('define_concrete_material', ('C1',21.,30000.,.2,24.), 'PropMaterial.SetMaterial', ('C1',2,-1,'','')),
    ('define_rebar_material', ('R1',420.,630.,200000.), 'PropMaterial.SetMaterial', ('R1',6,-1,'','')),
    ('define_slab_section', ('Z1','C1',400.,'Footing'), 'PropArea.SetSlab', ('Z1',6,2,'C1',400.,-1,'','')),
    ('define_soil_spring', ('SOIL',25.), 'PropAreaSpring.SetAreaSpringProp', ('SOIL',0.,0.,30.,1)),
    ('assign_area_spring', (['A1'],'SOIL'), 'AreaObj.SetSpringAssignment', ('A1','SOIL')),
    ('add_load_pattern', ('Dead','Dead',.5), 'LoadPatterns.Add', ('Dead','Dead',.5,True)),
    ('add_load_combo', ('COMB',{'Dead':1.4,'Live':1.6}), 'RespCombo.Add', ('COMB',0)),
    ('run_analysis', (), 'Analyze.RunAnalysis', ()),
    ('get_analysis_status', (), 'Analyze.GetCaseStatus', (0,[],[])),
    ('run_slab_design', (), 'DesignConcreteSlab.StartSlabDesign', ()),
    ('get_slab_design_summary', (), 'DesignConcreteSlab.GetSummaryResultsFlexureAndShear', tuple([] for _ in range(15))),
    ('get_slab_design_detail', (), 'DesignConcreteSlab.GetFlexureAndShear', tuple([] for _ in range(20))),
    ('get_design_strips', (), 'DesignConcreteSlab.DesignStrip.GetNameList', (0,[])),
    ('get_span_definitions', (), 'DesignConcreteSlab.GetSummaryResultsSpanDefinition', tuple([] for _ in range(10))),
    ('get_punching_check', (), 'DatabaseTables.GetAvailableTables', ()),
    ('get_soil_pressure', (), 'DatabaseTables.GetAvailableTables', ()),
    ('probe_file_types', ('salidas',4,4), 'File.ExportFile', (str(Path('salidas')/'probe_type_4'),4)),
    ('list_tables', (), 'DatabaseTables.GetAvailableTables', ()),
    ('get_table_data', ('Soil Pressure',), 'DatabaseTables.GetTableForDisplayArray', ('Soil Pressure',[],'',0)),
    ('set_table_data', ('Soil Pressure',['Name','Value'],[['P1','20']]), 'DatabaseTables.SetTableForEditingArray', ('Soil Pressure',7,['Name','Value'],1,['P1','20'])),
    ('import_file', ('entrada.f2k',1,0), 'File.ImportFile', ('entrada.f2k',1,0)),
    ('export_file', ('salida.f2k',1), 'File.ExportFile', ('salida.f2k',1)),
    ('open_model', ('copia.fdb',), 'File.OpenFile', ('copia.fdb',)),
    ('close_model', (True,), 'File.NewBlank', ()),
    ('copy_model_file', ('copia.fdb',), 'GetModelFilename', ()),
    ('call_oapi', ('AreaObj','GetProperty',['A1']), 'AreaObj.GetProperty', ('A1',)),
    ('clear_selection', (), 'SelectObj.ClearSelection', ()),
    ('select_objects', ('area',['A1']), 'AreaObj.SetSelected', ('A1',True)),
    ('get_selection', (), 'SelectObj.GetSelected', ()),
    ('delete_object', ('area','A1'), 'AreaObj.Delete', ('A1',0)),
    ('move_objects', ('point',['P1'],10.,20.,30.), 'EditGeneral.Move', (10.,20.,30.)),
    ('get_area_info', ('A1',), 'AreaObj.GetProperty', ('A1',)),
    ('set_area_property', ('A1','S2'), 'AreaObj.SetProperty', ('A1','S2',0)),
    ('set_area_opening', ('A1',True), 'AreaObj.SetOpening', ('A1',True,0)),
    ('set_point_coordinates', ('P1',11.,22.,33.), 'EditGeneral.Move', (10.,20.,30.)),
    ('set_area_points', ('A1',['P3','P2','P1']), 'EditArea.ChangeConnectivity', ('A1',3,['P3','P2','P1'])),
    ('add_point', (11.,12.,13.,'USER'), 'PointObj.AddCartesian', (11.,12.,13.,'','USER')),
    ('assign_point_load', ('P1','Dead',1.,2.,-3.,4.,5.,6.), 'PointObj.SetLoadForce', ('P1','Dead',[1.,2.,-3.,4.,5.,6.],True,'Global',0)),
    ('get_strip_rebar_stations', ('STRIP',1,0), 'DesignConcreteSlab.GetFlexureAndShear', ()),
    ('get_table_fields', ('Soil Pressure',), 'DatabaseTables.GetAllFieldsInTable', ('Soil Pressure',)),
]

def method(model, path):
    for part in path.split('.'): model = getattr(model, part)
    return model


@pytest.mark.parametrize('name,args,path,expected', CASES, ids=[c[0] for c in CASES])
def test_contrato_py_args_y_resultado(api, name, args, path, expected):
    safe, model, state = api
    if name == 'describe_oapi':
        with patch('oapi.describe', return_value='firma real') as describe:
            assert 'firma real' in safe.describe_oapi(*args)
            describe.assert_called_once_with(model.AreaObj,'Get')
        return
    result = getattr(safe, name)(*args)
    method(model,path).assert_any_call(*expected)
    assert result
    if name == 'get_points': assert result[0].xs == [1.] and result[0].id == 'P1'
    if name == 'get_areas': assert result[0].ys == [2.,5.,8.]
    if name == 'get_strip_rebar_stations': assert '12, 13' in result and '15, 16' in result
    if name == 'define_concrete_material':
        model.PropMaterial.SetMPIsotropic.assert_called_once_with('C1',30000.,.2,9.9e-6)
        model.PropMaterial.SetOConcrete_1.assert_called_once_with('C1',21.,False,0.,1,0,.0022,.0052,-.1,0.,0.)
        model.PropMaterial.SetWeightAndMass.assert_called_once_with('C1',1,24.)
    if name == 'define_rebar_material':
        model.PropMaterial.SetMPIsotropic.assert_called_once_with('R1',200000.,.3,11.7e-6)
        model.PropMaterial.SetORebar_1.assert_called_once_with('R1',420.,630.,420.,630.,1,0,.02,.1,.09,-.1)
    if name == 'add_load_combo':
        assert model.RespCombo.SetCaseList.call_args_list == [call('COMB',0,'Dead',1.4),call('COMB',0,'Live',1.6)]
    if name == 'get_design_strips':
        model.DesignConcreteSlab.DesignStrip.GetDesignStrip_1.assert_called_once_with('STRIP1',0,[],[],[],[],[],[],[],[],[])
    if name == 'close_model': model.File.Save.assert_called_once_with()
    if name == 'copy_model_file':
        import shutil
        shutil.copy2.assert_called_once_with('modelo.fdb','copia.fdb')
        model.File.Save.assert_not_called()
        model.File.OpenFile.assert_not_called()


# No pRetVal en estos getters; describe/copia no invocan metodos con pRetVal.
# probe_file_types es un diagnostico que DEBE devolver todos los errores del
# rango, no abortar ante el primero; no anuncia un export exitoso.
NO_RET = {'get_units','describe_oapi','copy_model_file','probe_file_types'}
ERROR_CASES = [c for c in CASES if c[0] not in NO_RET]

@pytest.mark.parametrize('name,args,path,expected', ERROR_CASES, ids=[c[0] for c in ERROR_CASES])
def test_ret_no_cero_es_safeerror(api, name, args, path, expected):
    safe,model,state=api
    fn=method(model,path)
    old=fn.side_effect
    value=fn.return_value
    def fail(*a,**kw):
        result=old(*a,**kw) if callable(old) else value
        return (*result[:-1],7) if isinstance(result,(tuple,list)) else 7
    fn.side_effect=fail
    with pytest.raises(SafeError): getattr(safe,name)(*args)


WRITES = [c for c in CASES if c[0] in {
    'set_units','move_objects','set_point_coordinates','set_area_property',
    'set_area_opening','set_area_points','add_point','assign_point_load','set_table_data','delete_object'}]

@pytest.mark.parametrize('name,args,path,expected', WRITES, ids=[c[0] for c in WRITES])
def test_ret_cero_sin_efecto_no_anuncia_exito(api,name,args,path,expected):
    safe,model,state=api
    # Desactivar SOLO el efecto del metodo que se prueba; la seleccion sigue
    # funcionando para llegar al Move y comprobar coordenadas sin modificar.
    fn=method(model,path)
    if name in {'move_objects','set_point_coordinates'}:
        fn.side_effect=None; fn.return_value=0
    else: state['effects']=False
    with pytest.raises(SafeError): getattr(safe,name)(*args)


@pytest.mark.parametrize('tool,args,getter,bad', [
    ('set_area_property',('A1','S2'),'AreaObj.GetProperty',('S2',9)),
    ('set_area_opening',('A1',True),'AreaObj.GetOpening',(True,9)),
    ('set_area_points',('A1',['P3','P2','P1']),'AreaObj.GetPoints',(3,['P3','P2','P1'],9)),
    ('add_point',(11.,12.,13.),'PointObj.GetCoordCartesian',(11.,12.,13.,9)),
    ('assign_point_load',('P1','Dead'),'PointObj.GetLoadForce',(0,[],[],[],[],[],[],[],[],[],[],9)),
    ('get_area_info',('A1',),'AreaObj.GetPoints',(3,['P1','P2','P3'],9)),
    ('get_area_info',('A1',),'AreaObj.GetOpening',(False,9)),
    ('get_area_info',('A1',),'PointObj.GetCoordCartesian',(1.,2.,3.,9)),
])
def test_errores_de_relectura(api,tool,args,getter,bad):
    safe,model,_=api
    fn=method(model,getter); fn.side_effect=None; fn.return_value=bad
    with pytest.raises(SafeError): getattr(safe,tool)(*args)


def test_abertura_false_reasigna_seccion_y_confirma(api):
    safe,model,state=api
    state.update(opening=True,prop='None')
    safe.set_area_opening('A1',False,section='S2')
    model.AreaObj.SetOpening.assert_called_once_with('A1',False,0)
    model.AreaObj.SetProperty.assert_called_once_with('A1','S2',0)
    assert state['prop']=='S2' and state['opening'] is False
    model.AreaObj.GetProperty.assert_called_with('A1')


def test_abertura_reasignacion_sin_efecto_falla(api):
    safe,model,state=api
    state.update(opening=True,prop='None')
    model.AreaObj.SetProperty.side_effect=None
    model.AreaObj.SetProperty.return_value=0
    with pytest.raises(SafeError): safe.set_area_opening('A1',False,section='S2')


@pytest.mark.parametrize('effect',[True,False])
def test_delete_special_point_relee(api,effect):
    safe,model,state=api
    state['effects']=effect
    if effect: assert 'borrado' in safe.delete_object('point','P1')
    else:
        with pytest.raises(SafeError): safe.delete_object('point','P1')
    model.PointObj.DeleteSpecialPoint.assert_called_once_with('P1',0)
    model.PointObj.GetCoordCartesian.assert_called_with('P1')
    model.PointObj.Delete.assert_not_called()


def test_carga_aditiva_compara_suma_y_no_solo_cantidad(api):
    safe,model,state=api
    state['loads']=[10.,20.,30.,40.,50.,60.]
    safe.assign_point_load('P1','Dead',1.,2.,3.,4.,5.,6.,replace=False)
    assert state['loads']==[11.,22.,33.,44.,55.,66.]
    assert model.PointObj.GetLoadForce.call_count==2


def test_delete_no_confunde_error_com_con_ausencia(api):
    safe,model,state=api
    model.PointObj.GetCoordCartesian.side_effect=None
    model.PointObj.GetCoordCartesian.return_value=(0.,0.,0.,9)
    with pytest.raises(SafeError,match='ausencia no confirmada'):
        safe.delete_object('point','P1')


@pytest.mark.parametrize('slab,enum,shell',[('Slab',0,1),('Drop',1,1),('Stiff',2,1),('Ribbed',3,1),('Waffle',4,1),('Mat',5,2),('Footing',6,2)])
def test_enums_slab_confirmados_claude_212(api,slab,enum,shell):
    safe,model,state=api
    model.PropArea.GetSlab.return_value=(enum,shell,'C1',400.,-1,'','g',0)
    safe.define_slab_section('Z1','C1',400.,slab)
    model.PropArea.SetSlab.assert_called_once_with('Z1',enum,shell,'C1',400.,-1,'','')
    model.PropArea.GetSlab.assert_called_once_with('Z1')


def test_enum_ribbed_no_puede_confirmar_footing(api):
    safe,model,state=api
    model.PropArea.GetSlab.return_value=(3,2,'C1',400.,-1,'','g',0)
    with pytest.raises(SafeError): safe.define_slab_section('Z1','C1',400.,'Footing')


@pytest.mark.parametrize('compression,enum,text',[(True,1,'Compression Only'),(False,0,'None')])
def test_suelo_se_confirma_por_tabla_no_por_getter_defectuoso(api,compression,enum,text):
    safe,model,state=api
    state['tables']['Spring Property Definitions - Area Springs'][1][0][1]=text
    safe.define_soil_spring('SOIL',25.,compression_only=compression)
    model.PropAreaSpring.SetAreaSpringProp.assert_called_once_with('SOIL',0.,0.,30.,enum)
    model.PropAreaSpring.GetAreaSpringProp.assert_not_called()


def test_resorte_tension_no_puede_confirmar_compresion(api):
    safe,model,state=api
    state['tables']['Spring Property Definitions - Area Springs'][1][0][1]='Tension Only'
    with pytest.raises(SafeError): safe.define_soil_spring('SOIL',25.)


@pytest.mark.parametrize('index,value',[(1,1),(2,'OTRO'),(3,200.)])
def test_slab_no_solo_compara_enum(api,index,value):
    safe,model,state=api
    result=[6,2,'C1',400.,-1,'','g',0]
    result[index]=value
    model.PropArea.GetSlab.return_value=tuple(result)
    with pytest.raises(SafeError): safe.define_slab_section('Z1','C1',400.,'Footing')


def test_resorte_relee_rigidez_y_nombre_exacto(api):
    safe,model,state=api
    state['tables']['Spring Property Definitions - Area Springs'][1][0][-1]='300'
    with pytest.raises(SafeError): safe.define_soil_spring('SOIL',25.)


def test_move_area_relee_ids_nuevos_por_vertices_compartidos(api):
    safe,model,state=api
    def move(dx,dy,dz):
        originals=list(state['area'])
        for pt in originals:
            state['coords']['N'+pt]=tuple(a+d for a,d in zip(state['coords'][pt],(dx,dy,dz)))
        state['area']=['N'+pt for pt in originals]
        return 0
    model.EditGeneral.Move.side_effect=move
    safe.move_objects('area',['A1'],10.,20.,30.)
    assert state['coords']['P1']==(1.,2.,3.)
    assert state['coords']['NP1']==(11.,22.,33.)
    assert model.AreaObj.GetPoints.call_count==2


def test_carga_cero_sin_asignacion_no_es_exito(api):
    safe,model,state=api
    model.PointObj.GetLoadForce.side_effect=None
    model.PointObj.GetLoadForce.return_value=(0,[],[],[],[],[],[],[],[],[],[],0)
    with pytest.raises(SafeError): safe.assign_point_load('P1','Dead')


@pytest.mark.parametrize('name,args,path',[
    ('define_concrete_material',('C1',21.,30000.,.2,24.),'PropMaterial.SetMPIsotropic'),
    ('define_concrete_material',('C1',21.,30000.,.2,24.),'PropMaterial.SetOConcrete_1'),
    ('define_concrete_material',('C1',21.,30000.,.2,24.),'PropMaterial.SetWeightAndMass'),
    ('define_rebar_material',('R1',420.,630.,200000.),'PropMaterial.SetORebar_1'),
    ('add_load_combo',('COMB',{'Dead':1.4}),'RespCombo.SetCaseList'),
    ('get_design_strips',(),'DesignConcreteSlab.DesignStrip.GetDesignStrip_1'),
])
def test_ret_no_cero_en_llamadas_secundarias(api,name,args,path):
    safe,model,state=api
    fn=method(model,path)
    original=fn.return_value
    fn.side_effect=None
    fn.return_value=(*original[:-1],8) if isinstance(original,tuple) else 8
    with pytest.raises(SafeError): getattr(safe,name)(*args)


def test_sonda_reporta_ret_y_falso_exito(api):
    safe,model,state=api
    model.File.ExportFile.side_effect=[8,0]
    result=safe.probe_file_types('salidas',4,5)
    assert 'ret=8' in result and 'sin archivo visible' in result


def test_oapi_no_reintenta_escritura_con_ret_de_error(api):
    safe,model,state=api
    model.AreaObj.SetProperty.side_effect=None
    model.AreaObj.SetProperty.return_value=-99
    with pytest.raises(SafeError,match='SetProperty.*ret=-99'):
        safe.set_area_property('A1','S2')
    model.AreaObj.SetProperty.assert_called_once()


def test_oapi_retorno_desconocido_no_es_exito(api):
    safe,model,state=api
    model.AreaObj.SetProperty.side_effect=None
    model.AreaObj.SetProperty.return_value=None
    with pytest.raises(SafeError,match='ret=None'): safe.set_area_property('A1','S2')


def test_oapi_variante_solo_tras_firma_incompatible(api):
    safe,model,state=api
    model.AreaObj.SetProperty.side_effect=[TypeError('argumentos'),0]
    state['prop']='S2'
    safe.set_area_property('A1','S2')
    assert model.AreaObj.SetProperty.call_args_list==[call('A1','S2',0),call('A1','S2')]


def test_cobertura_de_catalogo_y_no_registrar_metodo_x():
    names={case[0] for case in CASES}
    assert len(names)==49
    source=Path(__file__).parents[1]/'src/server.py'
    tree=ast.parse(source.read_text(encoding='utf-8-sig'))
    registered={node.value.args[0].attr for node in ast.walk(tree)
                if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call)
                and node.value.args and isinstance(node.value.args[0],ast.Attribute)
                and isinstance(node.value.args[0].value,ast.Name)
                and node.value.args[0].value.id=='safe'}
    assert registered == names-{'set_area_points'} | {'add_design_strip','set_strip_widths','set_punching_overwrite'}
    assert len(registered)==51
