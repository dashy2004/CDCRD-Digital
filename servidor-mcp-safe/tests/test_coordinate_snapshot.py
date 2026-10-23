import pytest


def test_snapshot_wrapper_preserves_model_and_units(api):
    safe, model, state = api
    state['filename'] = r'C:\synthetic\copy.fdb'
    model.PointObj.Count.return_value = 3
    result = safe.get_coordinate_snapshot(state['filename'], 'LOCAL')
    assert result['frame']['length_unit'] == 'mm'
    assert result['points'][2] == {'id': 'P3', 'xyz': [7., 8., 9.]}
    model.SetPresentUnits.assert_not_called()
    model.File.Save.assert_not_called()
    with pytest.raises(ValueError, match='distinto'):
        safe.get_coordinate_snapshot(r'C:\other.fdb', 'LOCAL')
