"""Edicion de tablas con esquemas exactos de la corrida viva §6.1."""
from copy import deepcopy
import math

import pytest
from Safe import SafeError

STRIP='Strip Object Connectivity'
PUNCH='Concrete Slab Design Overwrites - Punching Shear - General'


def test_add_strip_preserva_filas_y_excluye_numsegs_no_importable(api):
    safe,model,state=api
    before=deepcopy(state['tables'][STRIP][1])
    result=safe.add_design_strip('CDX:NEW','P1','P2',125.,250.,layer='B')
    fields=['Name','StartPoint','EndPoint','WStartLeft','WStartRight','WEndLeft','WEndRight','AutoWiden','Layer','GUID']
    flat=['STRIP1','P1','P2','10','20','30','40','No','A','g1',
          'CDX:NEW','P1','P2','125','250','125','250','No','B','']
    model.DatabaseTables.SetTableForEditingArray.assert_called_once_with(STRIP,7,fields,2,flat)
    model.DatabaseTables.ApplyEditedTables.assert_called_once_with(False)
    assert state['tables'][STRIP][1][0]==before[0]
    assert state['tables'][STRIP][1][1][-1]=='generated-guid'
    assert 'releida' in result
    assert model.DatabaseTables.GetTableForDisplayArray.call_count==3


def test_anchos_distintos_inicio_fin_conservan_otras_columnas(api):
    safe,model,state=api
    before=deepcopy(state['tables'][STRIP][1][0])
    safe.set_strip_widths('STRIP1',11.,22.,33.,44.)
    assert state['tables'][STRIP][1][0]==before[:4]+['11','22','33','44']+before[8:]


def test_punch_none_preserva_y_nombre_de_columna_effdepthtype(api):
    safe,model,state=api
    before=deepcopy(state['tables'][PUNCH][1][0])
    safe.set_punching_overwrite('P1',perimeter='Auto',eff_depth='Auto',rebar_type='User supplied test value')
    fields=['UniqueName','CheckPunchingShear','LocationType','Perimeter','EffDepthType','OpeningDef','RebarType']
    expected=before[:-1]+['User supplied test value']
    model.DatabaseTables.SetTableForEditingArray.assert_called_once_with(PUNCH,7,fields,1,expected)
    assert state['tables'][PUNCH][1][0][:6]==before[:6]


def test_punch_nuevo_exige_todos_valores_y_no_inventa_defaults(api):
    safe,model,state=api
    with pytest.raises(SafeError,match='seis valores'):
        safe.set_punching_overwrite('P2',check='Program Determined')
    model.DatabaseTables.SetTableForEditingArray.assert_not_called()
    safe.set_punching_overwrite('P2','Program Determined','Auto','Auto','Auto','Auto','None')
    assert len(state['tables'][PUNCH][1])==2
    assert state['tables'][PUNCH][1][1]==['P2','Program Determined','Auto','Auto','Auto','Auto','None']


def test_punch_none_no_escribir(api):
    safe,model,state=api
    assert 'sin cambios' in safe.set_punching_overwrite('P1')
    model.DatabaseTables.ApplyEditedTables.assert_not_called()


NEW=[('add_design_strip',('NEW','P1','P2',11.,22.)),
     ('set_strip_widths',('STRIP1',11.,22.,33.,44.)),
     ('set_punching_overwrite',('P1','User supplied test value'))]

@pytest.mark.parametrize('name,args',NEW)
@pytest.mark.parametrize('method',[
    'GetAvailableTables','GetTableForDisplayArray','GetAllFieldsInTable',
    'SetTableForEditingArray','ApplyEditedTables'])
def test_ret_no_cero_en_cada_etapa(api,name,args,method):
    safe,model,state=api
    fn=getattr(model.DatabaseTables,method)
    old=fn.side_effect
    fn.side_effect=lambda *a: (*old(*a)[:-1],8)
    with pytest.raises(SafeError): getattr(safe,name)(*args)
    if method!='ApplyEditedTables': model.DatabaseTables.ApplyEditedTables.assert_not_called()


@pytest.mark.parametrize('name,args',NEW)
def test_apply_ret_cero_sin_efecto_falla(api,name,args):
    safe,model,state=api
    state['effects']=False
    with pytest.raises(SafeError,match='no confirmada'): getattr(safe,name)(*args)


@pytest.mark.parametrize('fatal,errors',[(1,0),(0,1)])
def test_apply_ret_cero_con_errores_no_anuncia_exito(api,fatal,errors):
    safe,model,state=api
    model.DatabaseTables.ApplyEditedTables.side_effect=None
    model.DatabaseTables.ApplyEditedTables.return_value=(fatal,errors,0,0,'invalid value',0)
    with pytest.raises(SafeError,match='invalid value'):
        safe.set_strip_widths('STRIP1',11.,22.,33.,44.)


@pytest.mark.parametrize('kind,locked,allowed',[(0,False,False),(1,False,False),(2,True,False),(2,False,True),(3,True,True),(99,False,False)])
def test_importtype_y_bloqueo_segun_chm(api,kind,locked,allowed):
    safe,model,state=api
    model.DatabaseTables.GetAvailableTables.side_effect=None
    model.DatabaseTables.GetAvailableTables.return_value=(1,[STRIP],[STRIP],[kind],0)
    model.GetModelIsLocked.return_value=locked
    if allowed: safe.set_strip_widths('STRIP1',11.,22.,33.,44.)
    else:
        with pytest.raises(SafeError): safe.set_strip_widths('STRIP1',11.,22.,33.,44.)
        model.DatabaseTables.SetTableForEditingArray.assert_not_called()
    model.SetModelIsLocked.assert_not_called()


@pytest.mark.parametrize('value',[-1.,math.nan,math.inf])
def test_anchos_invalidos_no_escriben(api,value):
    safe,model,state=api
    with pytest.raises(SafeError): safe.add_design_strip('NEW','P1','P2',value,20.)
    model.DatabaseTables.SetTableForEditingArray.assert_not_called()


def test_no_duplicar_franja_ni_modificar_inexistente(api):
    safe,model,state=api
    with pytest.raises(SafeError): safe.add_design_strip('STRIP1','P1','P2',10.,20.)
    with pytest.raises(SafeError): safe.set_strip_widths('missing',1.,2.,3.,4.)
    model.DatabaseTables.SetTableForEditingArray.assert_not_called()


def test_esquema_desconocido_no_se_escribe(api):
    safe,model,state=api
    state['tables'][PUNCH][0].append('EffDepth')
    state['tables'][PUNCH][1][0].append('400')
    with pytest.raises(SafeError,match='esquema distinto'): safe.set_punching_overwrite('P1',check='Auto')
    model.DatabaseTables.SetTableForEditingArray.assert_not_called()


def test_orden_columnas_distinto_es_valido(api):
    safe,model,state=api
    fields,rows=state['tables'][PUNCH]
    state['tables'][PUNCH]=(list(reversed(fields)),[list(reversed(r)) for r in rows])
    safe.set_punching_overwrite('P1',perimeter='TEST')
    fields,rows=state['tables'][PUNCH]
    assert rows[0][fields.index('Perimeter')]=='TEST'
    assert rows[0][fields.index('CheckPunchingShear')]=='Program Determined'


def test_relectura_reordenada_y_anchos_formateados(api):
    safe,model,state=api
    old=model.DatabaseTables.ApplyEditedTables.side_effect
    def apply(*args):
        result=old(*args)
        fields,rows=state['tables'][STRIP]
        rows.reverse()
        for row in rows:
            for f in ['WStartLeft','WStartRight','WEndLeft','WEndRight']:
                row[fields.index(f)]=f'{float(row[fields.index(f)]):.3f}'
        return result
    model.DatabaseTables.ApplyEditedTables.side_effect=apply
    safe.add_design_strip('NEW','P1','P2',11.,22.)


def test_no_aceptar_cambio_en_fila_ajena(api):
    safe,model,state=api
    old=model.DatabaseTables.ApplyEditedTables.side_effect
    def apply(*args):
        result=old(*args)
        state['tables'][STRIP][1][0][8]='Yes'
        return result
    model.DatabaseTables.ApplyEditedTables.side_effect=apply
    with pytest.raises(SafeError,match='no confirmada'): safe.add_design_strip('NEW','P1','P2',11.,22.)


def test_no_paginar_antes_de_editar(api):
    safe,model,state=api
    fields,rows=state['tables'][PUNCH]
    rows.extend([[f'P{i}','Program Determined','Auto','Auto','Auto','Auto','None'] for i in range(2,152)])
    before=deepcopy(rows)
    safe.set_punching_overwrite('P151',check='TEST')
    after=state['tables'][PUNCH][1]
    assert len(after)==151 and after[:-1]==before[:-1]
    assert after[-1][1]=='TEST'


@pytest.mark.parametrize('fields,rows',[
    (['Name','Value'],[['P1']]), (['Name','Name'],[['P1','P1']]),
    (['Unknown'],[['P1']]), ([],[[]])])
def test_forma_invalida_set_table_data(api,fields,rows):
    safe,model,state=api
    with pytest.raises(SafeError): safe.set_table_data('Soil Pressure',fields,rows)
    model.DatabaseTables.SetTableForEditingArray.assert_not_called()


def test_datos_truncados_no_se_escriben(api):
    safe,model,state=api
    model.DatabaseTables.GetTableForDisplayArray.side_effect=None
    model.DatabaseTables.GetTableForDisplayArray.return_value=([],7,['Name','Value'],2,['P1','10'],0)
    with pytest.raises(SafeError,match='incoherente'): safe.set_table_data('Soil Pressure',['Name','Value'],[['P1','20']])
    model.DatabaseTables.SetTableForEditingArray.assert_not_called()


def test_list_tables_interpreta_0_a_3_y_desconocido(api):
    safe,model,state=api
    model.DatabaseTables.GetAvailableTables.side_effect=None
    model.DatabaseTables.GetAvailableTables.return_value=(5,['a','b','c','d','e'],['a','b','c','d','e'],[0,1,2,3,7],0)
    result=safe.list_tables()
    assert '1: importable, no editable interactivamente' in result
    assert '2: editable interactivamente solo desbloqueado' in result
    assert '3: editable interactivamente bloqueado o desbloqueado' in result
    assert '7: desconocido' in result
