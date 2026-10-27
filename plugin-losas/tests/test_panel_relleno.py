"""Ejecuta los handlers reales sin cargar Revit ni escribir parametros."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

SCRIPT = Path(__file__).parents[1] / 'revit/PanelLosas.extension/CDCRD Losas.tab/Losas.panel/UsoLosa.pushbutton/script.py'


def load(name, **scope):
    tree = ast.parse(SCRIPT.read_text(encoding='utf-8'))
    nodes = list(tree.body)
    nodes += next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == 'PanelUsoLosa').body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SCRIPT), 'exec'), scope)
    return scope[name]


@pytest.mark.parametrize('start,end,expected', [(1,3,[1,2,3]),(3,1,[1,2,3]),(2,2,[2]),(-1,2,[]),(2,4,[])])
def test_fill_bounds(start,end,expected):
    assert load('_indices_relleno')(start,end,4) == expected


@pytest.mark.parametrize('native,section,result', [
    ('L20A-2D H=0.20', 'auto (reglamento)', True),
    ('L15 H=0.15', 'L25A-1D', True),
    ('L20 H=0.20', 'L20', False),
    ('Losa nervada', '', True),
])
def test_real_type_overrides_auto_selector(native,section,result):
    assert load('_es_aligerada', re=re)({'tipo_nativo':native},section) == result


def fixture_panel():
    rows = [NS(Cells=[NS(Value='other') for _ in range(14)]) for _ in range(4)]
    for i,row in enumerate(rows):
        row.Cells[4].Value = ['A','B','C','D'][i]
    class Rows(list):
        Count = 4
    grid = NS(Rows=Rows(rows),Capture=True,EndEdit=lambda:True)
    panel = NS(grid=grid,por_etiqueta={'A':'a','B':'b'},_relleno=(1,'B'))
    panel._celda=lambda i,c:grid.Rows[i].Cells[c].Value
    return panel


def test_ctrl_d_changes_only_selected_usage_cells():
    panel=fixture_panel()
    panel.grid.SelectedCells=[NS(RowIndex=i,ColumnIndex=c) for i,c in [(0,4),(2,4),(3,8)]]
    load('rellenar_uso')(panel,None,None)
    assert [r.Cells[4].Value for r in panel.grid.Rows] == ['A','B','A','D']
    assert all(r.Cells[8].Value == 'other' for r in panel.grid.Rows)


@pytest.mark.parametrize('column,row,expected', [(4,3,['A','B','B','B']),(4,0,['B','B','C','D']),(5,3,['A','B','C','D']),(4,-1,['A','B','C','D'])])
def test_mouse_release_commits_only_valid_usage_target(column,row,expected):
    panel=fixture_panel()
    panel.grid.HitTest=lambda x,y:NS(ColumnIndex=column,RowIndex=row)
    load('_fin_relleno',MouseButtons=NS(Left=1),_indices_relleno=load('_indices_relleno'))(panel,None,NS(Button=1,X=0,Y=0))
    assert [r.Cells[4].Value for r in panel.grid.Rows] == expected
    assert panel._relleno is None and not panel.grid.Capture


def test_invalid_edit_does_not_fill():
    panel=fixture_panel()
    panel.grid.EndEdit=lambda:False
    panel.grid.SelectedCells=[NS(RowIndex=0,ColumnIndex=4),NS(RowIndex=2,ColumnIndex=4)]
    load('rellenar_uso')(panel,None,None)
    assert panel.grid.Rows[2].Cells[4].Value == 'C'


def test_cancel_capture_does_not_mutate_values():
    panel=fixture_panel();panel.grid.Capture=False
    load('_cancelar_captura')(panel,None,None)
    assert panel._relleno is None
    assert panel.grid.Rows[2].Cells[4].Value == 'C'


def test_ribbed_steel_not_serialized_as_strip():
    panel=fixture_panel()
    panel.grid.Rows[0].Cells[0].Value='S01'
    panel.grid.Rows[1].Cells[0].Value='S02'
    panel._aligeradas_grid=lambda:['S01']
    result=load('_aceros',_formatear_acero=lambda *args:'#3 @ 0.15')(panel)
    assert 'S01' not in result
    assert result['S02']['x']=='#3 @ 0.15'
