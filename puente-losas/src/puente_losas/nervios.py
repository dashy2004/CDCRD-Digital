"""Auditable SI checks for rectangular/T ribs; no automatic design approval.

Units: mm, MPa, N internally; moments kN m, shears kN at the boundary.
Normal-weight, nonprestressed concrete, no axial force, bonded non-epoxy bars.
Flexure uses strain compatibility including compression steel and displaced
concrete. Serviceability is an explicitly idealized simply supported orthotropic
plate; it does not include supporting-beam movement or certify a floor design.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _positive(**values: float) -> None:
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive")


def _nonnegative(**values: float) -> None:
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be finite and nonnegative")


@dataclass(frozen=True)
class RibSection:
    h_mm: float
    bw_mm: float
    bf_mm: float
    tf_mm: float
    fc_mpa: float
    fy_mpa: float
    ec_mpa: float
    es_mpa: float = 200000.0

    def __post_init__(self) -> None:
        _positive(**vars(self))
        if not (self.bw_mm <= self.bf_mm and self.tf_mm <= self.h_mm):
            raise ValueError("Invalid T-section geometry")

    def compression_block(self, depth: float) -> tuple[float, float]:
        """Area and first moment about compressed face, mm² and mm³."""
        if not 0 <= depth <= self.h_mm:
            raise ValueError("Block outside section")
        flange = min(depth, self.tf_mm)
        web = max(0.0, depth - flange)
        return (self.bf_mm * flange + self.bw_mm * web,
                self.bf_mm * flange**2 / 2 + self.bw_mm * web * (flange + web / 2))

    def gross(self) -> dict[str, float]:
        af = self.bf_mm * self.tf_mm
        aw = self.bw_mm * (self.h_mm - self.tf_mm)
        yf, yw = self.tf_mm / 2, (self.h_mm + self.tf_mm) / 2
        centroid = (af * yf + aw * yw) / (af + aw)
        inertia = (self.bf_mm * self.tf_mm**3 / 12 + af * (yf-centroid)**2
                   + self.bw_mm * (self.h_mm-self.tf_mm)**3 / 12 + aw * (yw-centroid)**2)
        return {"area_mm2": af+aw, "centroid_mm": centroid, "ig_mm4": inertia}


def flexure(section: RibSection, steel: list[tuple[float, float]], demand_knm: float) -> dict:
    """steel=(area_mm², distance_mm from compressed face). Positive demand only.

    For negative moment use a RECTANGULAR web section unless a justified inverted
    flange model is supplied separately. Ignoring its tension flange is conservative.
    Checks section strength and tensile strain, not anchorage or bar curtailment.
    """
    _nonnegative(demand=demand_knm)
    if not steel:
        raise ValueError("Invalid demand or empty reinforcement")
    for area, z in steel:
        _positive(area=area, z=z)
        if z >= section.h_mm:
            raise ValueError("Steel outside section")
    beta = max(.65, .85 - max(0.0, section.fc_mpa-28.0) * .05/7.0)
    def forces(c):
        a = min(beta*c, section.h_mm)
        area, first = section.compression_block(a)
        axial, moment = .85*section.fc_mpa*area, .85*section.fc_mpa*first
        for bar_area, z in steel:
            strain = .003*(c-z)/c
            stress = max(-section.fy_mpa, min(section.fy_mpa, section.es_mpa*strain))
            # Remove concrete displaced by bars only within Whitney block.
            net = stress - (.85*section.fc_mpa if z <= a else 0.0)
            axial += bar_area*net
            moment += bar_area*net*z
        return axial, abs(moment)/1e6
    low, high = 1e-7, section.h_mm
    if forces(low)[0] >= 0 or forces(high)[0] <= 0:
        raise ValueError("No zero-axial-force equilibrium")
    for _ in range(90):
        mid = (low+high)/2
        if forces(mid)[0] > 0: high=mid
        else: low=mid
    c = (low+high)/2
    eps_t = .003*(max(z for _,z in steel)-c)/c
    eps_y = section.fy_mpa/section.es_mpa
    phi = .65 + .25*max(0.0,min(1.0,(eps_t-eps_y)/.003))
    nominal = forces(c)[1]
    return {"neutral_axis_mm":c,"epsilon_t":eps_t,"tension_controlled":eps_t>=eps_y+.003,
            "phi":phi,"mn_knm":nominal,"phi_mn_knm":phi*nominal,"mu_knm":demand_knm,
            "strength_pass":phi*nominal>=demand_knm,"equilibrium_residual_n":forces(c)[0]}


def cracked_inertia(section: RibSection, area_mm2: float, d_mm: float) -> dict:
    """Transformed cracked T section; compression steel omitted explicitly."""
    _positive(area=area_mm2,d=d_mm)
    if d_mm >= section.h_mm: raise ValueError("d outside section")
    n = section.es_mpa/section.ec_mpa
    low, high = 0.0,d_mm
    for _ in range(80):
        c=(low+high)/2
        area, first=section.compression_block(c)
        if area*c-first > n*area_mm2*(d_mm-c): high=c
        else: low=c
    c=(low+high)/2
    flange=min(c,section.tf_mm)
    concrete_i=section.bf_mm*((c**3-(c-flange)**3)/3)
    if c>flange: concrete_i+=section.bw_mm*(c-flange)**3/3
    return {"c_mm":c,"icr_mm4":concrete_i+n*area_mm2*(d_mm-c)**2}


def effective_inertia(ig_mm4: float, icr_mm4: float, mcr_knm: float, ma_knm: float) -> float:
    """ACI 318-19 Table 24.2.3.5; nonprestressed members."""
    _positive(ig=ig_mm4,icr=icr_mm4,mcr=mcr_knm)
    _nonnegative(ma=ma_knm)
    if icr_mm4>ig_mm4:
        raise ValueError("Invalid service moment or inertia")
    if ma_knm <= 2*mcr_knm/3: return ig_mm4
    return icr_mm4/(1-(2*mcr_knm/(3*ma_knm))**2*(1-icr_mm4/ig_mm4))


def shear_without_stirrups(fc_mpa:float, bw_mm:float, d_mm:float, as_mm2:float, vu_kn:float) -> dict:
    """ACI 318-19 22.5.5.1(c), lambda=1, Nu=0; no joist 1.1 credit."""
    _positive(fc=fc_mpa,bw=bw_mm,d=d_mm,area=as_mm2)
    _nonnegative(vu=vu_kn)
    rho=as_mm2/(bw_mm*d_mm)
    size=min(1.0,math.sqrt(2/(1+d_mm/250)))
    vc=min(.66*size*rho**(1/3),.42)*min(math.sqrt(fc_mpa),8.3)*bw_mm*d_mm/1000
    return {"rho":rho,"lambda_s":size,"vc_kn":vc,"phi_vc_kn":.75*vc,"vu_kn":vu_kn,
            "strength_pass":.75*vc>=vu_kn,"minimum_shear_reinforcement_checked":False}


def navier_center(a_m:float,b_m:float,dx_nm:float,dy_nm:float,h_nm:float,q_n_m2:float,terms:int=31) -> float:
    """Central deflection m of simply supported orthotropic plate, uniform load.

    PDE Dx*w_xxxx + 2H*w_xxyy + Dy*w_yyyy = q. H=0 is a torsion-free
    smeared grillage sensitivity, not a general bound on a real building.
    Dx,Dy=E*I/pitch; H is supplied, never inferred from weight thickness.
    """
    _positive(a=a_m,b=b_m,dx=dx_nm,dy=dy_nm)
    _nonnegative(h=h_nm,q=q_n_m2)
    if isinstance(terms,bool) or not isinstance(terms,int) or not 1<=terms<=151:
        raise ValueError("terms must be an integer in [1,151]")
    result=0.0
    for m in range(1,2*terms,2):
        for n in range(1,2*terms,2):
            try:
                denominator=math.pi**4*(dx_nm*(m/a_m)**4+2*h_nm*(m/a_m)**2*(n/b_m)**2+dy_nm*(n/b_m)**4)
            except OverflowError as exc:
                raise ValueError("Plate stiffness overflow") from exc
            if not math.isfinite(denominator) or denominator<=0:
                raise ValueError("Plate stiffness outside numerical range")
            result+=16*q_n_m2/(math.pi**2*m*n)*(-1)**((m-1)//2+(n-1)//2)/denominator
    if not math.isfinite(result) or (q_n_m2>0 and result<=0):
        raise ValueError("Deflection outside numerical range")
    return result


def anchored_cells(low:float,high:float,origin:float,block:float,pitch:float) -> list[tuple[float,float]]:
    """EPS intervals intersected with a prevalidated solid-border window.

    Explicit shared origin preserves rib axes across adjacent panels. Clipped
    terminal EPS pieces remain individual; input extents are bounded to avoid OOM.
    """
    _positive(block=block,pitch=pitch)
    if not all(math.isfinite(v) for v in (low,high,origin)) or high<=low or block>=pitch:
        raise ValueError("Invalid cell window")
    first=math.floor((low-origin-block)/pitch)+1
    last=math.ceil((high-origin)/pitch)-1
    if last-first>1000: raise ValueError("Too many cells")
    return [(max(low,origin+i*pitch),min(high,origin+i*pitch+block))
            for i in range(first,last+1) if min(high,origin+i*pitch+block)-max(low,origin+i*pitch)>1e-8]
