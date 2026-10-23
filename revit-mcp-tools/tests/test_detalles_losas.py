import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('detalles', Path(__file__).parents[1]/'src/tools/detalles_losas.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def config():
    return {'view_prefix': 'CDX PILOTO DETALLES', 'text_type_name': 'TEXTO GR- 2.00 mm',
            'dimension_type_name': 'Dimensiones GR 2.00',
            'geometry': {'height_m': .25, 'topping_m': .05, 'block_m': .50,
                         'rib_m': .15, 'wall_m': .15, 'wall_gap_m': .02}}


def test_section_plan_and_wall_are_consistent_and_not_structural_approval():
    result = m.build_spec(config())
    assert not result['engineering_approved'] and not result['model_linked']
    section, plan, wall = result['views']
    assert len(plan['lines']) == 28  # six independent block rectangles + boundary
    assert section['dimensions'][0]['expected_m'] == pytest.approx(2.1)
    assert section['dimensions'][1]['expected_m'] == .25
    # Wall rectangle top is below the EPS bottom, even when a gap is configured.
    assert max(p[1] for line in wall['lines'][-4:] for p in line) == pytest.approx(-.02)
    for view in result['views']:
        for dim in view['dimensions']:
            assert all(0 <= r < len(view['lines']) for r in dim['refs'])


@pytest.mark.parametrize('key,value', [('height_m',float('nan')), ('topping_m',float('inf')),
    ('block_m',0), ('rib_m',-.1), ('wall_gap_m',-.01), ('wall_m',True)])
def test_invalid_geometry_fails_before_native_work(key, value):
    p = config()
    p['geometry'][key] = value
    with pytest.raises(ValueError):
        m.build_spec(p)


def test_topping_cannot_consume_block_height():
    p = config()
    p['geometry'].update(height_m=.20,topping_m=.19)
    with pytest.raises(ValueError):
        m.build_spec(p)


def test_digest_stable_but_changes_with_geometry_and_text_style():
    p = config()
    first = m.spec_digest(m.build_spec(p))
    assert m.spec_digest(m.build_spec(config())) == first
    p['geometry']['height_m'] = .30
    assert m.spec_digest(m.build_spec(p)) != first
    p = config()
    p['text_type_name'] = 'TEXTO GR'
    assert m.spec_digest(m.build_spec(p)) != first


def test_scope_rejects_original_pid_and_operator():
    lock = {'owner':'test', 'session':'test', 'task':'test', 'state':'active', 'process_id':42}
    copy, original = os.path.abspath('copy.rvt'), os.path.abspath('original.rvt')
    p = {'expected_path':copy, 'protected_paths':[original], 'expected_pid':42,
         'lock_identity': {k:lock[k] for k in ('owner','session','task')}}
    m.validate_scope(p, copy, 42, lock)
    for path, pid, state in [(original,42,lock), (copy,43,lock),
                             (copy,42,dict(lock, owner='other'))]:
        with pytest.raises(ValueError):
            m.validate_scope(p,path,pid,state)
    p.update(expected_path=original, protected_paths=original)
    with pytest.raises(ValueError):
        m.validate_scope(p,original,42,lock)
