"""Vía Pieper-Martens validada contra la salida REAL de Losas.exe v5.21.

Fixture de oro: ``restaurante_2.DL`` + ``restaurante_2.TXT`` (de EstructurasRD,
github.com/dashy2004/EstructurasRD — el mismo con el que se validó el motor C#).

Tolerancia 0.01 ton·m/m, la MISMA del test de oro del C# verificado: los
coeficientes S del PDF de Perdomo están publicados a 2 decimales, lo que
introduce ~0.007 de diferencia en Msx al interpolar (documentado en
MomentosCalculatorTests.cs de EstructurasRD).
"""
import os

import pytest

from puente_losas.contrato import PanoLosa
from puente_losas.dl_io import cargar_dl, cargar_txt, escribir_dl, leer_dl
from puente_losas.pieper_martens import (CODIGO_A_SUBTIPO, balancear, factores,
                                         momentos_losa)
from puente_losas.tipo_pm import clasificar_panos, pares_balanceo

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
DL = os.path.join(FIXTURES, "restaurante_2.DL")
TXT = os.path.join(FIXTURES, "restaurante_2.TXT")
TOL = 0.010


def test_tablas_completas():
    assert len(CODIGO_A_SUBTIPO) == 21
    fx, fy, sx, sy = factores("1", 1.0)      # 4 apoyos simples: sin empotramientos
    assert fx > 0 and fy > 0 and sx is None and sy is None
    fx, fy, sx, sy = factores("4", 1.0)      # 2 adyacentes: ambos S presentes
    assert sx is not None and sy is not None


def test_dl_de_oro_se_lee():
    s = cargar_dl(DL)
    assert s.fc_ton_cm2 == 0.210 and s.fy_ton_cm2 == 4.200
    assert [losa.tipo for losa in s.losas] == [40, 40, 40, 40, 71]
    assert s.pares_x == [(1, 2, "S"), (2, 4, "S")]
    assert s.pares_y == [(1, 3, "S"), (2, 4, "S"), (5, 2, "N"), (5, 1, "N")]


def test_dl_round_trip():
    s = cargar_dl(DL)
    s2 = leer_dl(escribir_dl(s))
    assert s2 == s


def test_txt_de_oro_se_lee():
    momentos, apoyos = cargar_txt(TXT)
    assert len(momentos) == 5 and len(apoyos) == 6
    assert momentos[0].mfx == 1.280 and momentos[0].msy == 2.108
    assert apoyos[0].direccion == "X" and apoyos[0].mu_ij == 1.987


def test_momentos_pm_igualan_a_losas_exe():
    """La cadena tablas→interpolación→momentos reproduce el .TXT de Losas.exe."""
    s = cargar_dl(DL)
    esperados, _ = cargar_txt(TXT)
    por_losa = {m.losa: m for m in esperados}
    for losa in s.losas:
        m = momentos_losa(losa.tipo, losa.carga, losa.lx, losa.ly)
        ref = por_losa[losa.id]
        assert m.mfx == pytest.approx(ref.mfx, abs=TOL), f"Mfx losa {losa.id}"
        assert m.mfy == pytest.approx(ref.mfy, abs=TOL), f"Mfy losa {losa.id}"
        assert m.msx == pytest.approx(ref.msx, abs=TOL), f"Msx losa {losa.id}"
        assert m.msy == pytest.approx(ref.msy, abs=TOL), f"Msy losa {losa.id}"


def test_balanceo_iguala_a_losas_exe():
    s = cargar_dl(DL)
    _, apoyos_ref = cargar_txt(TXT)
    momentos = {str(losa.id): momentos_losa(losa.tipo, losa.carga, losa.lx, losa.ly)
                for losa in s.losas}
    calculados = {}
    for i, j, modo in s.pares_x:
        a = balancear(str(i), str(j), "X", modo, momentos)
        calculados[("X", i, j)] = a.mu_ij
    for i, j, modo in s.pares_y:
        a = balancear(str(i), str(j), "Y", modo, momentos)
        calculados[("Y", i, j)] = a.mu_ij
    for ref in apoyos_ref:
        assert calculados[(ref.direccion, ref.losa_i, ref.losa_j)] == \
            pytest.approx(ref.mu_ij, abs=TOL), f"apoyo {ref.losa_i}-{ref.losa_j} {ref.direccion}"


def test_voladizo_71_y_72():
    m71 = momentos_losa(71, 0.720, 13.650, 1.200)
    assert m71.msy == pytest.approx(0.720 * 1.2 ** 2 / 2, rel=1e-9)
    assert m71.mfx == m71.mfy == m71.msx == 0.0
    m72 = momentos_losa(72, 1.0, 1.5, 6.0)
    assert m72.msx == pytest.approx(1.0 * 1.5 ** 2 / 2, rel=1e-9)
    assert m72.msy == 0.0


# ----------------------- clasificador y pares de balanceo -----------------------
def _rect(x0, y0, lx, ly):
    return [[x0, y0], [x0 + lx, y0], [x0 + lx, y0 + ly], [0 + x0, y0 + ly]]


def _pano(mark, x0, y0, lx=5.0, ly=6.0, **kw):
    return PanoLosa(mark=mark, nivel="N1", z_tope=3.0, lx=lx, ly=ly, espesor=0.25,
                    contorno=_rect(x0, y0, lx, ly), **kw)


def _grilla_3x3():
    return [_pano(f"L{j * 3 + i + 1}", i * 5.0, j * 6.0) for j in range(3) for i in range(3)]


def test_clasificador_grilla_3x3():
    c = clasificar_panos(_grilla_3x3())
    assert c["L5"].codigo == 60     # centro: 4 bordes continuos
    assert c["L1"].codigo == 40     # esquina: 2 adyacentes
    assert c["L2"].codigo == 51     # medio inferior: 3 continuos, apoyo horizontal
    assert c["L4"].codigo == 52     # medio izquierdo: 3 continuos, apoyo vertical


def test_clasificador_casos_restantes():
    solo = clasificar_panos([_pano("A", 0, 0)])
    assert solo["A"].codigo == 10
    dos_h = clasificar_panos([_pano("A", 0, 0), _pano("B", 0, 6), _pano("C", 0, -6)])
    assert dos_h["A"].codigo == 31  # vecinos arriba y abajo (N,S)
    assert dos_h["B"].codigo == 21  # un empotrado horizontal
    dos_v = clasificar_panos([_pano("A", 0, 0), _pano("B", 5, 0), _pano("C", -5, 0)])
    assert dos_v["A"].codigo == 32
    assert dos_v["B"].codigo == 22


def test_vuelo_vecino_no_empotra():
    # Convención del fixture RESTAURANTE 2: la losa junto al vuelo NO gana un
    # borde empotrado por él (allí las vecinas del vuelo son tipo 40, no 5x).
    base = _pano("L1", 0, 0)
    vuelo = _pano("V1", -1.8, 0, lx=1.8, ly=6.0, es_vuelo=True)
    c = clasificar_panos([base, vuelo])
    assert c["L1"].codigo == 10      # sin el vuelo, L1 no tiene vecinos reales
    assert c["V1"].codigo == 72


def test_clasificador_vuelo_y_eps():
    vuelo = _pano("V", -1.8, 0, lx=1.8, ly=6.0, es_vuelo=True)
    c = clasificar_panos([vuelo])
    assert c["V"].codigo == 72      # la luz corta es Lx → vuela sobre Lx (Msx)
    alargada = _pano("B", 0, 0, lx=2.0, ly=6.0)
    assert clasificar_panos([alargada])["B"].eps_recortado   # ε = 3.0 > 2.0


def test_pares_balanceo_con_vuelo():
    base = _pano("L1", 0, 0)
    vuelo = _pano("V1", -1.8, 0, lx=1.8, ly=6.0, es_vuelo=True)
    px, py = pares_balanceo([base, vuelo])
    assert py == []
    assert px == [("V1", "L1", "N")]   # el vuelo gobierna: losa I, modo N


def test_pares_balanceo_grilla():
    px, py = pares_balanceo(_grilla_3x3())
    assert len(px) == 6 and len(py) == 6       # 6 bordes verticales y 6 horizontales
    assert all(modo == "S" for _, _, modo in px + py)
