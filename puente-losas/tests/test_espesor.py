"""Espesor mínimo normativo, redondeo ↑0.05 y mapeo a la biblioteca de losas."""
import pytest

from puente_losas.contrato import PanoLosa
from puente_losas.espesor import (espesor_de_pano, h_min_dos_direcciones,
                                  h_min_una_direccion, redondear_arriba_005_m,
                                  seccion_biblioteca)


def _pano(**kw):
    base = dict(mark="L1", nivel="N2", z_tope=3.0, lx=5.0, ly=6.0, espesor=0.25,
                borde="simple")
    base.update(kw)
    return PanoLosa(**base)


def test_una_direccion_tabla_7311():
    assert h_min_una_direccion(4.0, False, "simple") == pytest.approx(4.0 / 20)
    assert h_min_una_direccion(4.0, False, "empotrado") == pytest.approx(4.0 / 28)
    assert h_min_una_direccion(1.8, True, "simple") == pytest.approx(1.8 / 10)


def test_dos_direcciones_8312b():
    # h = ln(0.8 + fy/1400)/(36 + 9β), fy=420 → 0.8+0.3=1.1; β=1 → 45.
    assert h_min_dos_direcciones(6.0, 1.0) == pytest.approx(6.0 * 1.1 / 45.0)
    assert h_min_dos_direcciones(1.0, 1.0) == 0.090     # piso absoluto 90 mm


def test_redondeo_dimensiones_anexo_a():
    # Ejemplos literales del Anexo A: 1.56→1.60, 1.51→1.55, 1.55 queda 1.55.
    assert redondear_arriba_005_m(1.56) == 1.60
    assert redondear_arriba_005_m(1.51) == 1.55
    assert redondear_arriba_005_m(1.55) == 1.55


def test_biblioteca_macizas_y_aligeradas():
    assert seccion_biblioteca(0.12, False) == ("L12", False)
    assert seccion_biblioteca(0.15, False) == ("L15", False)
    assert seccion_biblioteca(0.20, False) == ("L20", False)
    assert seccion_biblioteca(0.25, False) == ("L25A-2D", False)
    assert seccion_biblioteca(0.25, True) == ("L25A-1D", False)
    assert seccion_biblioteca(0.30, False) == ("L30A-2D", True)   # definición nueva: consultar


def test_espesor_de_pano_marca_insuficiente():
    # Paño 2D 5×6 con h=0.10 en el modelo: mínimo 8.3.1.2(b) manda más.
    e = espesor_de_pano(_pano(espesor=0.10))
    assert e.espesor_modelo_insuficiente
    assert e.h_usado >= e.h_recomendado > 0.10
    assert "8.3.1.2" in e.criterio


def test_espesor_de_pano_vuelo_usa_l10():
    e = espesor_de_pano(_pano(lx=1.8, ly=6.0, es_vuelo=True, espesor=0.25))
    assert "voladizo" in e.criterio
    assert e.h_min_normativo == pytest.approx(0.18)
