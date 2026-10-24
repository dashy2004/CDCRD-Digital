import math
import pytest
from puente_losas.nervios import (RibSection, flexure, cracked_inertia,
    effective_inertia, shear_without_stirrups, navier_center, anchored_cells)


def test_rectangular_capacity_matches_hand_equilibrium():
    s=RibSection(500,300,300,500,28,420,25000)
    result=flexure(s,[(900,450)],100)
    a=900*420/(.85*28*300)
    assert result['mn_knm']==pytest.approx(900*420*(450-a/2)/1e6,rel=1e-10)
    assert result['phi']==pytest.approx(.9)
    assert abs(result['equilibrium_residual_n'])<1e-6


def test_compression_steel_increases_capacity_and_equilibrates():
    s=RibSection(250,160,160,250,25,420,25000)
    single=flexure(s,[(600,215)],30)
    double=flexure(s,[(600,215),(400,35)],30)
    assert double['phi_mn_knm']>single['phi_mn_knm']
    assert abs(double['equilibrium_residual_n'])<1e-6


def test_flange_strength_and_rectangular_inertia():
    s=RibSection(300,200,800,70,30,420,27000)
    assert flexure(s,[(500,260)],20)['phi_mn_knm']>flexure(RibSection(300,200,200,300,30,420,27000),[(500,260)],20)['phi_mn_knm']
    rectangle=RibSection(400,250,250,400,25,420,25000)
    assert rectangle.gross()['ig_mm4']==pytest.approx(250*400**3/12)
    n=8; area=600; d=350
    c=(-n*area+math.sqrt((n*area)**2+2*250*n*area*d))/250
    assert cracked_inertia(rectangle,area,d)['icr_mm4']==pytest.approx(250*c**3/3+n*area*(d-c)**2)


def test_effective_inertia_limits_and_continuity():
    assert effective_inertia(100,25,3,2)==100
    assert effective_inertia(100,25,3,2.00000001)==pytest.approx(100,rel=1e-7)
    assert effective_inertia(100,25,3,1e10)==pytest.approx(25)
    with pytest.raises(ValueError):effective_inertia(25,100,3,2)


def test_navier_matches_classical_square_plate_and_scaling():
    # Classical simply supported isotropic square: center w=0.00406235*q*a^4/D.
    w=navier_center(4,4,2e6,2e6,2e6,5000)
    assert w==pytest.approx(.00406235*5000*4**4/2e6,rel=2e-6)
    assert navier_center(4,4,2e6,2e6,2e6,10000)==pytest.approx(2*w)
    assert navier_center(5,4,3e6,2e6,1e6,5000)==pytest.approx(navier_center(4,5,2e6,3e6,1e6,5000))
    assert navier_center(4,4,2e6,2e6,0,5000)>w


def test_navier_long_plate_recovers_simple_beam():
    # In the infinite-aspect-ratio limit and zero coupling, short-direction strip.
    assert navier_center(4,160,2e6,2e6,0,5000,101)==pytest.approx(5*5000*4**4/(384*2e6),rel=.005)


def test_shear_has_no_joist_bonus_and_finite_guard():
    r=shear_without_stirrups(25,150,180,300,10)
    assert r['vc_kn']==pytest.approx(.66*(300/(150*180))**(1/3)*5*150*180/1000)
    for x in [0,-1,float('nan'),float('inf'),True]:
        with pytest.raises(ValueError):shear_without_stirrups(x,150,180,300,10)


def test_high_strength_concrete_shear_limit():
    assert not shear_without_stirrups(100,150,200,500,35)['strength_pass']
    assert shear_without_stirrups(100,150,200,500,35)['phi_vc_kn']==pytest.approx(31.4838230299,rel=1e-7)


def test_compression_bar_below_yield_displaces_concrete():
    s=RibSection(250,160,160,250,25,420,25000)
    r=flexure(s,[(400,35),(747.142857142857,215)],20)
    assert r['neutral_axis_mm']==pytest.approx(70)
    assert r['mn_knm']==pytest.approx(57.546075)


@pytest.mark.parametrize('fn',[
    lambda:navier_center(1,1,1e308,1e308,1e308,100),
    lambda:navier_center(1,1,1,1,True,100),
    lambda:navier_center(1,1,1,1,0,True),
    lambda:shear_without_stirrups(25,150,180,300,True),
])
def test_nonfinite_result_and_boolean_rejected(fn):
    with pytest.raises(ValueError):fn()


def test_anchor_preserves_pitch_and_partial_edge_cell():
    cells=anchored_cells(.3,3.1,.3,.5,.65)
    assert cells==pytest.approx([(.3,.8),(.95,1.45),(1.6,2.1),(2.25,2.75),(2.9,3.1)])
    with pytest.raises(ValueError):anchored_cells(0,10000,0,.5,.65)
    with pytest.raises(ValueError):anchored_cells(0,1,0,.5,.5)


@pytest.mark.parametrize('fn',[
    lambda:RibSection(200,150,100,50,25,420,25000),
    lambda:navier_center(4,4,1,1,-1,10),
    lambda:navier_center(4,4,1,1,0,10,100000),
    lambda:flexure(RibSection(200,150,650,50,25,420,25000),[(200,201)],20),
    lambda:flexure(RibSection(200,150,650,50,25,420,25000),[],20),
])
def test_invalid_scope_rejected(fn):
    with pytest.raises(ValueError):fn()
