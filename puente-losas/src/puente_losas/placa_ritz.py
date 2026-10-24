"""Small orthotropic-plate sensitivity solver (numpy optional dependency).

Rayleigh-Ritz tensor-product polynomial basis with essential edge constraints.
Units m, N, Nm. Uniform load and constant Dx,Dy,H. D12=0 and D66=H/2;
the PDE is identical to Navier's but moment recovery has NO Poisson coupling.
This is NOT a cracked-building, flexible-beam, discrete-rib or CSI model.
Convergence and boundary assumptions must accompany every engineering result.
"""
from __future__ import annotations
from .nervios import _positive, _nonnegative


def solve(a_m:float,b_m:float,dx_nm:float,dy_nm:float,h_nm:float,q_n_m2:float,
          fixed:tuple[str,...]=(),order:int=6) -> dict:
    import numpy as np
    from numpy.polynomial import Polynomial, Legendre
    from numpy.polynomial.legendre import leggauss
    _positive(a=a_m,b=b_m,dx=dx_nm,dy=dy_nm)
    _nonnegative(h=h_nm,q=q_n_m2)
    if any(e not in ('W','E','S','N') for e in fixed) or len(set(fixed))!=len(fixed):
        raise ValueError('Unknown or duplicate fixed edge')
    if isinstance(order,bool) or not isinstance(order,int) or not 2<=order<=9:
        raise ValueError('order must be an integer in [2,9]')
    def basis(left,right):
        edge=Polynomial([0,1])**(2 if left else 1)*Polynomial([1,-1])**(2 if right else 1)
        return [edge*Legendre.basis(i).convert(kind=Polynomial)(Polynomial([-1,2])) for i in range(order)]
    bx=basis('W' in fixed,'E' in fixed);by=basis('S' in fixed,'N' in fixed)
    nodes,weights=leggauss(2*order+5);nodes=(nodes+1)/2;weights=weights/2
    def matrices(bs):
        vals=[np.array([p.deriv(k)(nodes) for p in bs]) for k in range(3)]
        return [(v*weights)@v.T for v in vals], vals[0]@weights
    xx,fx=matrices(bx);yy,fy=matrices(by)
    with np.errstate(over='raise',invalid='raise',divide='raise'):
        try:
            k=(dx_nm/a_m**4*np.kron(xx[2],yy[0])+dy_nm/b_m**4*np.kron(xx[0],yy[2])
               +2*h_nm/(a_m*b_m)**2*np.kron(xx[1],yy[1]))
            f=q_n_m2*np.kron(fx,fy)
            coefficients=np.linalg.solve(k,f)
        except (FloatingPointError,np.linalg.LinAlgError) as exc:
            raise ValueError('Invalid or singular plate system') from exc
    if not np.isfinite(coefficients).all():raise ValueError('Nonfinite solution')
    residual=float(np.max(np.abs(k@coefficients-f))/max(float(np.max(np.abs(f))),1))
    if not np.isfinite(residual) or residual>1e-8:raise ValueError('Plate residual invalid or too high')
    condition=float(np.linalg.cond(k))
    if not np.isfinite(condition):raise ValueError('Nonfinite plate condition number')
    c=coefficients.reshape(order,order)
    coords=np.linspace(0,1,101)
    vx=np.array([p(coords) for p in bx]);vy=np.array([p(coords) for p in by])
    dxx=np.array([p.deriv(2)(coords) for p in bx])/a_m**2
    dyy=np.array([p.deriv(2)(coords) for p in by])/b_m**2
    w=vx.T@c@vy;mx=-dx_nm*dxx.T@c@vy;my=-dy_nm*vx.T@c@dyy
    if not all(np.isfinite(v).all() for v in (w,mx,my)):
        raise ValueError('Nonfinite plate recovery')
    i,j=np.unravel_index(np.argmax(w),w.shape)
    return {'w_center_m':float(w[50,50]),'w_max_m':float(w[i,j]),
            'max_location_fraction':[float(coords[i]),float(coords[j])],
            'mx_positive_nm_m':float(mx.max()),'my_positive_nm_m':float(my.max()),
            'mx_negative_nm_m':float(mx.min()),'my_negative_nm_m':float(my.min()),
            'order':order,'relative_residual':residual,'condition_number':condition,
            'fixed_edges':list(fixed),'sample_grid':101,'beam_movement_included':False}
