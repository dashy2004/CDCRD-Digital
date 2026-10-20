"""Contrato de entrada: parsing, overrides de uso y continuidad por adyacencia."""
import pytest

from puente_losas.contrato import (PanoLosa, aplicar_usos, asignar_bordes,
                                   bordes_continuos, panos_desde_dict)


def _rect(x0, y0, lx, ly):
    return [[x0, y0], [x0 + lx, y0], [x0 + lx, y0 + ly], [x0, y0 + ly]]


def _pano(mark, x0, y0, lx=5.0, ly=6.0, z=3.0, **kw):
    return PanoLosa(mark=mark, nivel="N2", z_tope=z, lx=lx, ly=ly, espesor=0.25,
                    contorno=_rect(x0, y0, lx, ly), **kw)


def test_panos_desde_dict_formato_exportar_proyecto():
    d = {"losas": [{
        "id": "L1", "mark": "L7", "revit_id": 123, "nivel": "2DO NIVEL",
        "contorno": _rect(0, 0, 5, 6), "huecos": [_rect(1, 1, 1, 1)],
        "lx": 5.0, "ly": 6.0, "z_tope": 5.35, "area_m2": 29.0,
        "espesor": {"h_usado": 0.25}, "tipo_revit": "Generic - 0.25",
    }]}
    (p,) = panos_desde_dict(d)
    assert p.mark == "L7"            # manda el Mark de Revit, no el id del export
    assert p.espesor == 0.25
    assert len(p.huecos) == 1
    assert p.uso == "entrepisos"     # default


def test_panos_desde_dict_exige_losas():
    with pytest.raises(ValueError):
        panos_desde_dict({"losas": []})


def test_validaciones_de_pano():
    with pytest.raises(ValueError):
        panos_desde_dict({"losas": [{"id": "L1", "lx": 0, "ly": 5, "z_tope": 0,
                                     "espesor": {"h_usado": 0.2}}]})
    with pytest.raises(ValueError):
        panos_desde_dict({"losas": [{"id": "L1", "lx": 4, "ly": 5, "z_tope": 0,
                                     "espesor": {"h_usado": 0.2}, "uso": "oficina"}]})


def test_aplicar_usos_sobrescribe_y_valida():
    p = _pano("L1", 0, 0)
    (q,) = aplicar_usos([p], {"L1": {"uso": "comun", "mamposteria_tm2": 0.12, "es_vuelo": True}})
    assert q.uso == "comun" and q.mamposteria_tm2 == 0.12 and q.es_vuelo
    with pytest.raises(ValueError):
        aplicar_usos([p], {"L1": {"carga": 1.0}})          # campo desconocido


def test_relacion_de_luces_decide_1d():
    assert not _pano("A", 0, 0, lx=5, ly=6).trabaja_1d     # 1.2 → 2D
    assert _pano("B", 0, 0, lx=2, ly=6).trabaja_1d         # 3.0 → 1D
    assert _pano("C", 0, 0, lx=5, ly=6, direccion="1D").trabaja_1d   # declarado manda


def test_adyacencia_contigua_y_junta():
    # L1 y L2 comparten borde (contiguas); L3 queda al otro lado de una junta de 0.10 m.
    l1 = _pano("L1", 0.0, 0.0)
    l2 = _pano("L2", 5.0, 0.0)
    l3 = _pano("L3", 10.10, 0.0)
    n = bordes_continuos([l1, l2, l3])
    assert n["L1"] == 1
    assert n["L2"] == 1              # la junta con L3 NO cuenta como continuidad
    assert n["L3"] == 0


def test_asignar_bordes_empotrado_solo_interior():
    # 3×3 paños de 5×6: solo el central tiene 4 vecinos.
    panos = [_pano(f"L{j * 3 + i + 1}", i * 5.0, j * 6.0) for j in range(3) for i in range(3)]
    con_borde = {p.mark: p.borde for p in asignar_bordes(panos)}
    assert con_borde["L5"] == "empotrado"
    assert all(b == "simple" for m, b in con_borde.items() if m != "L5")


def test_asignar_bordes_respeta_override():
    p = _pano("L1", 0, 0, borde="empotrado")
    (q,) = asignar_bordes([p])
    assert q.borde == "empotrado"
