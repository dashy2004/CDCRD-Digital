import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from table_contracts import time_history_row

FIELDS = ['Name','LoadType','LoadName','Function','TransAccSF','TimeFactor','ArrivalTime',
          'Angle','NumSteps','StepSize','ModalCase','MotionType','InitialCond','GeoNonlin',
          'ProBy','MassCoeff','StiffCoeff','IntType','Gamma','Beta']

@pytest.mark.parametrize('nonlinear', [False, True])
def test_history_schema_and_time_factor(nonlinear):
    row, expected = time_history_row(FIELDS,'TH','pulse','U1',9.80665,.02,5,nonlinear)
    values = dict(zip(FIELDS,row))
    assert values['TimeFactor'] == '1'
    assert values['NumSteps'] == '5'
    assert values['LoadType'] == 'Accel'
    assert float(values['TransAccSF']) == 9.80665
    assert values['IntType'] == ('Newmark' if nonlinear else '')
    assert all(values[k] == v for k,v in expected.items())

@pytest.mark.parametrize('step,count,scale', [(0,5,1),(-1,5,1),(.02,0,1),(.02,True,1),
                                           (.02,2.5,1),(float('nan'),5,1),(.02,5,float('inf'))])
def test_history_rejects_invalid_input(step,count,scale):
    with pytest.raises(ValueError): time_history_row(FIELDS,'TH','pulse','U1',scale,step,count)

def test_history_refuses_unknown_schema():
    with pytest.raises(ValueError, match='Esquema'): time_history_row(['Name'],'TH','pulse','U1',1,.02,5)
