"""Caso de referencia: placa rectangular simplemente apoyada con carga uniforme.

Compara el FEM del motor de EstructurasRD contra la solución analítica de
Navier (serie doble, Timoshenko & Woinowsky-Krieger, *Theory of Plates and
Shells*, §Navier): w y Mx en el centro, calculados aquí con la MISMA ν del
motor — sin coeficientes copiados de tabla. También cubre el adaptador
completo (analizar_pano) y la coherencia simple/empotrado.
"""
import math

import pytest

from puente_losas.contrato import PanoLosa, asignar_bordes
from puente_losas.motor import analizar_pano, divisiones_malla, modulo_elasticidad_pa

A = 5.0
E, NU, T = 2.0e10, 0.2, 0.2
Q = 10000.0


def _navier_centro(a: float, b: float, q: float, e: float, nu: float, t: float,
                   terminos: int = 61) -> tuple[float, float]:
    """(w, Mx) en el centro de una placa SS a×b bajo q uniforme (serie de Navier).

    w   = Σ Amn / (D·((m/a)²+(n/b)²)²·π⁴) · sin(mπ/2)·sin(nπ/2)
    Mx  = Σ Amn · ((mπ/a)² + ν(nπ/b)²) / (π⁴·((m/a)²+(n/b)²)²) · sin(mπ/2)·sin(nπ/2)
    con Amn = 16q/(π²·m·n), m y n impares.
    """
    d = e * t ** 3 / (12.0 * (1.0 - nu * nu))
    w = mx = 0.0
    for m in range(1, terminos + 1, 2):
        for n in range(1, terminos + 1, 2):
            amn = 16.0 * q / (math.pi ** 2 * m * n)
            den = math.pi ** 4 * ((m / a) ** 2 + (n / b) ** 2) ** 2
            seno = math.sin(m * math.pi / 2.0) * math.sin(n * math.pi / 2.0)
            w += amn / (d * den) * seno
            mx += amn * ((m * math.pi / a) ** 2 + nu * (n * math.pi / b) ** 2) / den * seno
    return w, mx


def test_navier_reproduce_el_coeficiente_clasico():
    # Sanidad de la propia referencia: placa cuadrada, w = 0.00406·q·a⁴/D.
    d = E * T ** 3 / (12.0 * (1.0 - NU * NU))
    w, _ = _navier_centro(A, A, Q, E, NU, T)
    assert w * d / (Q * A ** 4) == pytest.approx(0.00406, abs=0.00002)


def test_fem_vs_navier_flecha_y_momento():
    from motor_fea.core.losa_fem import resolver_losa_rectangular
    w_ref, mx_ref = _navier_centro(A, A, Q, E, NU, T)
    r = resolver_losa_rectangular(A, A, 16, 16, E, NU, T, Q, "simple")
    assert r.w_central == pytest.approx(w_ref, rel=0.03)
    # mx_max del motor es el máximo en centros de elemento: tolerancia de malla.
    assert r.mx_max == pytest.approx(mx_ref, rel=0.10)


def test_fem_rectangular_no_cuadrada_vs_navier():
    from motor_fea.core.losa_fem import resolver_losa_rectangular
    a, b = 4.0, 6.0
    w_ref, _ = _navier_centro(a, b, Q, E, NU, T)
    r = resolver_losa_rectangular(a, b, 12, 16, E, NU, T, Q, "simple")
    assert r.w_central == pytest.approx(w_ref, rel=0.04)


def _pano(**kw):
    base = dict(mark="LE1", nivel="N1", z_tope=3.0, lx=5.0, ly=5.0, espesor=0.20)
    base.update(kw)
    return PanoLosa(**base)


def test_adaptador_end_to_end():
    (p,) = asignar_bordes([_pano()])
    r = analizar_pano(p)
    assert r.params["borde"] == "simple"
    assert r.params["t"] >= 0.20
    assert r.w_servicio_m < r.w_ultima_m          # servicio pesa menos que última
    assert r.mx_tonf_m > 0 and r.my_tonf_m > 0
    for franja in (r.franja_x, r.franja_y, r.franja_apoyo):
        assert franja["cumple"] and not franja["seccion_insuficiente"]
        assert franja["as_diseno"] >= franja["as_minimo"] - 1e-6


def test_empotrado_baja_flecha_y_sube_apoyo():
    (simple,) = asignar_bordes([_pano(borde="simple")])
    (empotrado,) = asignar_bordes([_pano(borde="empotrado")])
    rs, re = analizar_pano(simple), analizar_pano(empotrado)
    assert re.w_ultima_m < rs.w_ultima_m
    assert re.m_apoyo_tonf_m > rs.m_apoyo_tonf_m


def test_malla_y_modulo():
    assert divisiones_malla(5.0) == 10
    assert divisiones_malla(2.0) == 8              # piso
    assert divisiones_malla(12.0) == 16            # tope
    # Ec = 15100·√210 kg/cm² → Pa (valor de la biblioteca de Arlette).
    assert modulo_elasticidad_pa() == pytest.approx(15100.0 * math.sqrt(210.0) * 98066.5)


def test_vuelo_va_por_voladizo_analitico_no_por_fem():
    # El FEM del motor apoya los 4 bordes: un vuelo iría falsamente rígido.
    (p,) = asignar_bordes([_pano(mark="V1", lx=1.8, ly=6.0, es_vuelo=True,
                                 espesor=0.20, uso="comun", direccion="1D")])
    r = analizar_pano(p)
    assert r.params["modelo"] == "voladizo_analitico"
    # M_apoyo = q·l²/2 exacto, en tonf·m/m.
    assert r.m_apoyo_tonf_m == pytest.approx(r.cargas.q_ultima * 1.8 ** 2 / 2.0, rel=1e-9)
    assert r.mx_tonf_m == 0.0 and r.my_tonf_m == 0.0
    assert r.franja_apoyo["as_diseno"] >= r.franja_apoyo["as_minimo"]
    assert r.franja_x["gobierna_minimo"]            # vano: solo retracción/temperatura
    # w = q·l⁴/(8D) exacto.
    d_placa = (modulo_elasticidad_pa() * 0.20 ** 3) / (12.0 * (1.0 - 0.2 ** 2))
    q_u = r.cargas.q_ultima * 9806.65
    assert r.w_ultima_m == pytest.approx(q_u * 1.8 ** 4 / (8.0 * d_placa), rel=1e-9)


def test_borde_sin_asignar_es_error():
    with pytest.raises(ValueError):
        analizar_pano(_pano())
