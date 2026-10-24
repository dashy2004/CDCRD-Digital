import pytest
pytest.importorskip('numpy')
from puente_losas.placa_ritz import solve
from puente_losas.nervios import navier_center


@pytest.mark.parametrize('h',[0,1e6,2e6])
def test_ritz_matches_navier_independent_series(h):
    r=solve(5,4,2e6,3e6,h,5000,order=8)
    assert r['w_center_m']==pytest.approx(navier_center(5,4,2e6,3e6,h,5000),rel=.001)
    assert r['relative_residual']<1e-10


def test_fixed_plate_classical_coefficient():
    # Classical isotropic square, all fixed: w_max ~= .0012653*q*a^4/D.
    r=solve(4,4,2e6,2e6,2e6,5000,('W','E','S','N'),8)
    assert r['w_max_m']==pytest.approx(.0012653*5000*4**4/2e6,rel=.0001)


def test_mixed_edges_convergence_symmetry():
    a=solve(6,5,2e6,3e6,0,5000,('E','N'),6)
    b=solve(6,5,2e6,3e6,0,5000,('E','N'),8)
    c=solve(5,6,3e6,2e6,0,5000,('E','N'),8)
    assert a['w_max_m']==pytest.approx(b['w_max_m'],rel=.001)
    assert b['w_max_m']==pytest.approx(c['w_max_m'],rel=1e-7)
    assert b['w_max_m']<solve(6,5,2e6,3e6,0,5000,(),8)['w_max_m']
    assert b['mx_negative_nm_m']<0


def test_invalid_plate_boundary():
    with pytest.raises(ValueError):solve(4,5,1e6,1e6,0,100,('NN',))


def test_large_finite_units_do_not_produce_nan_receipt():
    import math
    r=solve(1,1,1e200,1e200,1e200,1e200,order=6)
    assert math.isfinite(r['relative_residual'])
