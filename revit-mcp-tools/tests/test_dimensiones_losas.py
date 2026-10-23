import importlib.util
import math
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('dims', Path(__file__).parents[1]/'src/tools/dimensiones_losas.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('angle', [0, .4, math.pi/2, math.pi])
@pytest.mark.parametrize('reverse', [False, True])
def test_measures_rotated_contour_not_axis_box(angle, reverse):
    points = [[10+x*math.cos(angle)-y*math.sin(angle), 20+x*math.sin(angle)+y*math.cos(angle), 5]
              for x,y in [(0,0),(7,0),(7,4),(0,4)]]
    assert module.rectangle_lengths(points[::-1] if reverse else points, math.degrees(angle)) == pytest.approx((7,4))


@pytest.mark.parametrize('points', [
    [[0,0,0],[5,0,0],[4,4,0],[0,4,0]],
    [[0,0,0],[5,0,0],[5,4,1],[0,4,1]],
    [[0,0,0],[0,0,0],[5,4,0],[0,4,0]],
    [[0,0,0],[5,4,0],[5,0,0],[0,4,0]],
    [[0,0,0],[math.inf,0,0],[5,4,0],[0,4,0]],
    [[0,0,0],[5,0,0],[5,4,0]],
])
def test_ambiguous_geometry_rejected(points):
    with pytest.raises(ValueError): module.rectangle_lengths(points)


def test_exact_copy_and_owner_required(tmp_path):
    cfg={'expected_path':str(tmp_path/'copy.rvt'), 'protected_paths':[str(tmp_path/'original.rvt')],
         'expected_pid':9,'floor_ids':[1],'lock_identity':{'owner':'codex','session':'test','task':'dims'}}
    lock=dict(cfg['lock_identity'],state='active')
    module.validate_scope(cfg,cfg['expected_path'],9,lock)
    with pytest.raises(ValueError): module.validate_scope(cfg,cfg['protected_paths'][0],9,lock)
    with pytest.raises(ValueError): module.validate_scope(cfg,cfg['expected_path'],10,lock)
    with pytest.raises(ValueError): module.validate_scope(cfg,cfg['expected_path'],9,dict(lock,session='other'))
    with pytest.raises(ValueError): module.validate_scope(dict(cfg,floor_ids=[1,1]),cfg['expected_path'],9,lock)


def test_rotated_rectangle_requires_declared_axes():
    with pytest.raises(ValueError, match="Ejes"):
        module.rectangle_lengths([[0,0,0],[2,2,0],[1,3,0],[-1,1,0]])
