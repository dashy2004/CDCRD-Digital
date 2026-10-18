"""Native area-layer fallback, without claiming a complete or checked bar schedule."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from wall_results import area_rebar_rows, read_wall_area_layers


def native():
    return [2, [None, None], [2, 1], [25., 0.], ['12', '16'], [113.1, 201.1],
            [450., 230.], [0, 0], [False, False], [0., 0.], [0., 0.], [0., 0.], 0]


def test_decodes_native_layers_and_preserves_unspecified_values():
    rows = area_rebar_rows(native())
    assert len(rows) == 2
    assert rows[0]['LayerTypeName'] == 'horizontal_middle_each_face'
    assert rows[1]['LayerTypeName'] == 'vertical_middle_each_face'
    assert rows[1]['ClearCover'] == 0
    assert rows[1]['LayerID'] is None
    assert rows[1]['NumberBars'] == 0  # Not an invented total number of bars.


@pytest.mark.parametrize('index,value', [
    (0, True), (0, -1), (0, 3), (12, 1), (12, False), (2,[8,1]),
    (4,['','16']), (5,[float('nan'),201.1]), (6,[-1,230]),
    (7,[1.5,0]), (8,[0,False]), (3,[25,None]),
])
def test_bad_layer_contract_rejected(index, value):
    result = native()
    result[index] = value
    with pytest.raises(ValueError):
        area_rebar_rows(result)


def test_empty_is_not_manufactured_reinforcement():
    assert area_rebar_rows([0, *([[]]*11), 0]) == []


def test_fallback_maps_only_designed_story_piers_and_reports_missing_coverage():
    a = SimpleNamespace(
        GetNameList=lambda: [3,['slab','wall','other'],0],
        GetPier=lambda n: ['None' if n=='slab' else 'P1',0],
        GetLabelFromName=lambda n: [n,'L1' if n=='wall' else 'L3',0],
        GetRebarDataPier=lambda n: native(),
    )
    call = lambda obj, name, args: getattr(obj,name)(*args)
    result = read_wall_area_layers(SimpleNamespace(AreaObj=a),
                                  [{'Story':'L1','Pier':'P1'}, {'Story':'L2','Pier':'P1'}], call)
    assert len(result['areas']) == 1
    assert result['areas'][0]['AreaObjName'] == 'wall'
    assert result['layer_count'] == 2
    assert result['missing_story_piers'] == [{'Story':'L2','Pier':'P1'}]
    assert result['all_designed_story_piers_have_layers'] is False


def test_native_read_failure_not_swallowed():
    def fail(*args):
        raise RuntimeError('COM read failed')
    with pytest.raises(RuntimeError, match='COM read failed'):
        read_wall_area_layers(SimpleNamespace(AreaObj=object()), [{'Story':'L1','Pier':'P'}], fail)
