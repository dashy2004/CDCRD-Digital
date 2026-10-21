import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import sitio

PVIS = [[0,100],[100,104],[200,100],[300,102]]

@pytest.mark.parametrize('value', ['{}', '[', '[1]', '[{"pvi":true,"longitud":20}]',
    '[{"pvi":0,"longitud":20}]', '[{"pvi":3,"longitud":20}]',
    '[{"pvi":1,"longitud":0}]', '[{"pvi":1,"longitud":NaN}]',
    '[{"pvi":1,"longitud":200}]', '[{"pvi":1,"longitud":false}]',
    '[{"pvi":1,"longitud":20,"extra":1}]',
    '[{"pvi":1,"longitud":20},{"pvi":1,"longitud":30}]',
    '[{"pvi":1,"longitud":100},{"pvi":2,"longitud":100}]',
    '[{"pvi":1,"longitud":120},{"pvi":2,"longitud":120}]'])
def test_rejects_invalid_curve_spec(value):
    with pytest.raises((ValueError,TypeError)):
        sitio.parsear_curvas(value, PVIS)

def test_curves_preserve_pvis_and_sort_only_indices():
    original = [row[:] for row in PVIS]
    assert sitio.parsear_curvas('[{"pvi":2,"longitud":60},{"pvi":1,"longitud":40}]',PVIS) == [
        {'pvi':1,'longitud':40.0},{'pvi':2,'longitud':60.0}]
    assert PVIS == original

def test_no_grade_change_is_rejected():
    with pytest.raises(ValueError, match='pendiente'):
        sitio.parsear_curvas([{'pvi':1,'longitud':20}],[[0,0],[100,1],[200,2]])

def test_curves_confirmation_and_single_dispatch():
    registered,calls={},[]
    class Mcp:
        def tool(self):
            def add(fn):registered[fn.__name__]=fn;return fn
            return add
    sitio.registrar(Mcp(),lambda *a,**k:calls.append((a,k)),json.dumps)
    fn=registered['crear_perfil_por_pvi']
    fn('A','P',json.dumps(PVIS),curvas='[{"pvi":1,"longitud":40}]')
    fn('A','P',json.dumps(PVIS),curvas='[{"pvi":0,"longitud":40}]',confirmar=True)
    assert calls == []
    fn('A','P',json.dumps(PVIS),curvas='[{"pvi":1,"longitud":40}]',confirmar=True,simular=True)
    assert len(calls)==1
    assert calls[0][0][1]['curvas']==[{'pvi':1,'longitud':40.0}]
    assert calls[0][1]=={'escribe':True}
