import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('apoyos',Path(__file__).parents[1]/'src/tools/apoyos_losa.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_duplicate_supports_do_not_double_count():
    r=module.interval_union([[0,3],[1,4],[5,6]],0,6)
    assert r['covered_m']==5 and r['gaps_m']==[[4,5]]
    assert r['coverage']==pytest.approx(5/6)


def test_clip_full_empty_and_adjacent():
    assert module.interval_union([[-1,3],[3,20]],0,10)['coverage']==1
    assert module.interval_union([],0,5)['gaps_m']==[[0,5]]
    assert module.interval_union([[9,10]],0,5)['coverage']==0


@pytest.mark.parametrize('intervals,lo,hi',[([[2,1]],0,3),([[0,float('nan')]],0,3),([],2,1),([],0,float('inf'))])
def test_invalid_data_rejected(intervals,lo,hi):
    with pytest.raises(ValueError):
        module.interval_union(intervals,lo,hi)


def test_apply_refused_before_model_access():
    with pytest.raises(ValueError,match='Read-only'):
        module.run(None,None,None,{'action':'apply'})


GRID={'height_m':.20,'topping_m':.05,'block_m':.5,'rib_m':.15,'border_m':.30}


def test_full_cells_centered_with_exact_ribs_and_border():
    plan=module.candidate_grid([0,0,7.2,5.9],GRID)
    assert plan['counts_xy']==[10,8]
    assert plan['actual_border_xy_m']==pytest.approx([.425,.425])
    assert plan['eps_height_m']==pytest.approx(.15)
    cells=plan['rectangles_m']
    assert len(cells)==80
    assert all(c[2]-c[0]==pytest.approx(.5) and c[3]-c[1]==pytest.approx(.5) for c in cells)
    ys=sorted(set(c[1] for c in cells))
    assert all(b-a-.5==pytest.approx(.15) for a,b in zip(ys,ys[1:]))
    assert plan['applied'] is False and plan['structural_design_verified'] is False


@pytest.mark.parametrize('change',[{'height_m':.15},{'topping_m':.2},{'block_m':float('nan')},{'rib_m':True},{'border_m':.1}])
def test_candidate_rejects_invalid_inputs(change):
    with pytest.raises(ValueError):
        module.candidate_grid([0,0,7.2,5.9],dict(GRID,**change))


@pytest.mark.parametrize('bounds',[[0,0,.5,.5],[0,0,15,15],[1,1,0,0]])
def test_candidate_rejects_too_small_large_or_reversed(bounds):
    with pytest.raises(ValueError):
        module.candidate_grid(bounds,GRID)
