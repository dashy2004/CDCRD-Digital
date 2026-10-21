"""Reglas de carga del flujo de Arlette: sets, mínimos, vuelos y redondeo ↑0.05."""
import pytest

from puente_losas.cargas import (cargas_de_pano, q_para_motor,
                                 redondear_arriba_005)
from puente_losas.contrato import PanoLosa


def _pano(**kw):
    base = dict(mark="L1", nivel="N2", z_tope=3.0, lx=5.0, ly=6.0, espesor=0.20)
    base.update(kw)
    return PanoLosa(**base)


def test_redondeo_arriba_005_ejemplos_de_la_regla():
    # Ejemplos literales de la regla confirmada del 15/10/2026.
    assert redondear_arriba_005(0.121) == 0.15
    assert redondear_arriba_005(0.156) == 0.20
    assert redondear_arriba_005(0.20) == 0.20       # múltiplo exacto se conserva
    assert redondear_arriba_005(0.631) == 0.65
    # Un residuo numérico no sube el múltiplo exacto.
    assert redondear_arriba_005(0.1 + 0.05) == 0.15


def test_set_entrepisos_con_minimo_de_mamposteria():
    c = cargas_de_pano(_pano())
    assert c.acabados_dead == 0.16 and c.patron_viva == "Live" and c.viva == 0.20
    assert c.mamposteria_calculada == 0.10          # mínimo del §13.1
    assert c.mamposteria_asignada == 0.10
    assert c.peso_propio == pytest.approx(0.20 * 2.4028)


def test_mamposteria_dada_se_redondea_al_asignar():
    c = cargas_de_pano(_pano(mamposteria_tm2=0.121))
    assert c.mamposteria_calculada == 0.121
    assert c.mamposteria_asignada == 0.15


def test_vuelo_sin_mamposteria_ni_minimo():
    c = cargas_de_pano(_pano(es_vuelo=True, mamposteria_tm2=0.30))
    assert c.mamposteria_asignada == 0.0            # excepción obligatoria
    assert c.acabados_dead == 0.16 and c.viva == 0.20   # acabados y viva se conservan


def test_sets_techo_y_parqueos():
    t = cargas_de_pano(_pano(uso="techo"))
    assert (t.acabados_dead, t.patron_viva, t.viva) == (0.16, "LiveT", 0.10)
    p = cargas_de_pano(_pano(uso="parqueos"))
    assert (p.acabados_dead, p.patron_viva, p.viva) == (0.16, "LiveP", 0.50)


def test_combinaciones_servicio_y_ultima():
    c = cargas_de_pano(_pano())
    d = c.peso_propio + 0.16 + 0.10
    assert c.q_servicio == pytest.approx(d + 0.20)
    assert c.q_ultima == pytest.approx(1.2 * d + 1.6 * 0.20)


def test_conversion_a_si():
    assert q_para_motor(1.0) == pytest.approx(9806.65)
