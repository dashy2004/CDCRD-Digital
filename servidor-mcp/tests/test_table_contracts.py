import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from table_contracts import editing_rows, mass_source_rows

FIELDS = ['Name','IsDefault','IncLateral','IncVertical','LumpMass','SourceSelf',
          'SourceAdded','SourceLoads','LoadPattern','Multiplier']


def test_mass_preserves_other_sources_and_replaces_only_target():
    old = [['Other','Yes','Yes','No','Yes','Yes','Yes','No','',''],
           ['Target','No','Yes','No','Yes','No','No','Yes','OldLoad','1'],
           ['', '', '', '', '', '', '', '', 'OldLive','.5']]
    result = mass_source_rows(FIELDS, old, 'Target', {'Dead':1, 'Live':.25})
    assert len(result) == 3
    assert result[0][0] == 'Other' and result[0][1] == 'No'
    assert result[0][2:] == old[0][2:]
    assert [row[-2] for row in result[1:]] == ['Dead','Live']
    assert all(row[1:8] == ['Yes','Yes','No','Yes','No','No','Yes'] for row in result[1:])


@pytest.mark.parametrize('patterns', [{},{'Dead':-1},{'Dead':float('nan')},{'Dead':True},{'':1},{'Dead':0}])
def test_invalid_mass_patterns_rejected(patterns):
    with pytest.raises(ValueError): mass_source_rows(FIELDS, [], 'Test', patterns)


def test_editing_rows_strict_shape():
    assert editing_rows([1, ['Name','Value'], 1, ['a','b'], 0]) == (['Name','Value'], [['a','b']])
    assert editing_rows([1, ['Name'], 0, None, 0]) == (['Name'], [])


@pytest.mark.parametrize('raw', [None, [1,['A'],1,[],0], [1,['A','A'],1,['x','x'],0],
                               [1,['A'],1,[2],0], [1,['A'],1,['x'],1]])
def test_bad_table_rejected(raw):
    with pytest.raises(ValueError): editing_rows(raw)
