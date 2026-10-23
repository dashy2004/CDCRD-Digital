import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('aligerado',Path(__file__).parents[1]/'src/tools/aligerado_propuesta.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


@pytest.mark.parametrize('height',[.12,.15,.16])
def test_at_or_below_threshold_stays_solid(height):
    assert tool.section_for_existing_thickness(height,'2D') is None


@pytest.mark.parametrize('direction',['1D','2D'])
@pytest.mark.parametrize('height,code',[(.20,'L20A-'),(.25,'L25A-')])
def test_twenty_centimetres_is_lightened(height,code,direction):
    assert tool.section_for_existing_thickness(height,direction)==code+direction


@pytest.mark.parametrize('height',[0,-1,.18,.30,float('inf'),float('nan')])
def test_unknown_section_rejected(height):
    with pytest.raises(ValueError):tool.section_for_existing_thickness(height,'2D')


def test_cavities_keep_border_ribs_and_do_not_overlap():
    rows=tool.cavity_rectangles([10,20,17.5,26.75],'2D',.15,.65,.30)
    assert len(rows)>50
    for i,(x0,y0,x1,y1) in enumerate(rows):
        assert 10.30<=x0<x1<=17.20 and 20.30<=y0<y1<=26.45
        assert x1-x0<=.500001 and y1-y0<=.500001
        for a,b,c,d in rows[i+1:]:
            assert min(x1,c)<=max(x0,a) or min(y1,d)<=max(y0,b)


def test_one_way_cavities_run_along_short_span():
    rows=tool.cavity_rectangles([0,0,8,3],'1D',.15,.65,.30)
    assert all(y0==.30 and y1==2.70 for x0,y0,x1,y1 in rows)
    assert max(x1-x0 for x0,y0,x1,y1 in rows)<=.500001


@pytest.mark.parametrize('bounds,rib,pitch,border',[([0,0,8,3],.15,.1,.3),([0,0,8,3],.15,.65,0),([0,0,8,.5],.15,.65,.3)])
def test_invalid_modulation_rejected(bounds,rib,pitch,border):
    with pytest.raises(ValueError):tool.cavity_rectangles(bounds,'2D',rib,pitch,border)


@pytest.mark.parametrize('reject',[False,True])
def test_owned_geometry_disposed_after_success_or_rejection(monkeypatch,reject):
    disposed=[]
    class Solid:
        def Dispose(self):disposed.append(True)
    def native_run(doc,uidoc,db,config,owned):
        owned.append(Solid())
        if reject:raise ValueError('geometry rejected')
        return {'status':'applied'}
    monkeypatch.setattr(tool,'_run',native_run)
    if reject:
        with pytest.raises(ValueError,match='geometry rejected'):tool.run(None,None,None,{})
    else:
        assert tool.run(None,None,None,{})=={'status':'applied'}
    assert disposed==[True]


def test_low_memory_requires_bounded_complexity_and_explicit_opt_in():
    assert tool.memory_floor_mb({})==1000
    config={'memory_mode':'bounded','bounds_m':[0,0,7,5],'section':'2D','rib_m':.15,'pitch_m':.65,'border_m':.30}
    assert tool.memory_floor_mb(config)==768
    config['bounds_m']=[0,0,10,10]
    assert tool.memory_floor_mb(config)==1000
    with pytest.raises(ValueError):tool.memory_floor_mb({'memory_mode':'unlimited'})
