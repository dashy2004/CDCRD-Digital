"""Criterio R-024 tabla 5.1 sobre fixtures SINTETICAS (repo publico: sin datos reales).

Malla 3x3 a 2.25 m con diametro 0.45 -> S/B = 5.00 exacto, factor 0.90.
Pareja a 1.20 m -> S/B = 2.67, fuera de tabla (factor None).
"""
import math

import pytest

import pilotes as pl


def frame(fid, x, y, seccion="P45", z_top=0.0, z_bot=-12.0, x2=None, y2=None):
    return {"id": fid, "seccion": seccion, "p1": f"T{fid}", "p2": f"B{fid}",
            "x1": x, "y1": y, "z1": z_top,
            "x2": x if x2 is None else x2, "y2": y if y2 is None else y2, "z2": z_bot}


SECCIONES = {"P45": {"diametro": 0.45, "material": "C280"}}


def malla_3x3(paso=2.25):
    return [frame(f"F{i}{j}", i * paso, j * paso) for i in range(3) for j in range(3)]


# ---------------------------------------------------------------- tabla 5.1

@pytest.mark.parametrize("sb,esperado", [
    (6.0, 1.0), (7.5, 1.0), (5.0, 0.9), (5.99, 0.9), (4.0, 0.8), (4.5, 0.8), (3.0, 0.7), (3.9, 0.7)])
def test_step_down_es_escalon_inferior(sb, esperado):
    assert pl.factor_tabla_5_1(sb) == (esperado, False)


@pytest.mark.parametrize("sb", [2.99, 2.67, 0.0, -1.0, math.nan, None])
def test_bajo_3_queda_fuera_de_tabla_sin_extrapolar(sb):
    assert pl.factor_tabla_5_1(sb) == (None, True)
    assert pl.factor_tabla_5_1(sb, "linear") == (None, True)


@pytest.mark.parametrize("sb,esperado", [(4.5, 0.85), (3.5, 0.75), (5.0, 0.9), (6.0, 1.0), (3.0, 0.7)])
def test_linear_interpola_y_se_declara(sb, esperado):
    assert pl.factor_tabla_5_1(sb, "linear") == (esperado, False)


def test_interpolacion_desconocida_rechazada():
    with pytest.raises(pl.PilotesError):
        pl.factor_tabla_5_1(5.0, "spline")


def test_sb_5_exacto_por_division_flotante_no_cae_a_0_8():
    assert pl.factor_tabla_5_1(2.25 / 0.45) == (0.9, False)


# ----------------------------------------------------------- malla 3x3 S/B 5

def test_malla_3x3_sb_5_factor_0_90():
    pil, avisos = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    out = pl.evaluar_separacion(pil)
    assert len(out["pilotes"]) == 9 and avisos == []
    assert all(p.s_b == 5.0 and p.factor == 0.9 and not p.fuera_de_tabla for p in out["pilotes"])
    assert all(p.vecinos[0]["distancia"] == 2.25 for p in out["pilotes"])
    r = out["resumen"]
    assert r["separacion"]["min"] == r["separacion"]["max"] == 2.25
    assert r["s_b"]["mediana"] == 5.0 and r["histograma_s_b"] == {"<3": 0, "3-4": 0, "4-5": 0, "5-6": 9, ">=6": 0}
    assert r["fuera_de_tabla"] == {"n": 0, "ids": []} and r["factor_minimo"] == 0.9
    assert out["interpolacion"] == "step_down" and out["tabla_5_1"] == {"6": 1.0, "5": 0.9, "4": 0.8, "3": 0.7}


def test_k_vecinos_ordenados_por_distancia():
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    out = pl.evaluar_separacion(pil, neighbors=3)
    centro = next(p for p in out["pilotes"] if p.id == "F11")
    assert [v["distancia"] for v in centro.vecinos] == [2.25, 2.25, 2.25]
    esquina = next(p for p in out["pilotes"] if p.id == "F00")
    assert [v["distancia"] for v in esquina.vecinos] == [2.25, 2.25, round(2.25 * math.sqrt(2), 6)]
    assert esquina.vecinos[2]["s_b"] == round(2.25 * math.sqrt(2) / 0.45, 6)


def test_grilla_equivale_a_fuerza_bruta_en_nube_dispersa():
    import random
    rnd = random.Random(7)
    frames = [frame(f"R{i}", rnd.uniform(0, 80), rnd.uniform(0, 40)) for i in range(150)]
    frames.append(frame("LEJOS", 500.0, 500.0))  # fuera de todo anillo cercano
    pil, _ = pl.pilotes_desde_frames(frames, SECCIONES)
    pl.asignar_vecinos(pil, 2, "step_down")
    for p in pil:
        bruta = sorted((math.hypot(p.x - q.x, p.y - q.y), q.id) for q in pil if q is not p)[:2]
        assert [v["distancia"] for v in p.vecinos] == [round(d, 6) for d, _ in bruta]


# ----------------------------------------------------- pareja fuera de tabla

def test_pareja_a_1_20_sb_2_67_fuera_de_tabla():
    pil, _ = pl.pilotes_desde_frames([frame("A", 0, 0), frame("B", 1.2, 0)], SECCIONES)
    out = pl.evaluar_separacion(pil, scope="by_footing", cabezales=[cabezal("C", -1, -1, 3, 1)],
                                q_ult=191.25, fs=2.25)
    assert all(p.s_b == 2.666667 and p.factor is None and p.fuera_de_tabla for p in out["pilotes"])
    assert out["resumen"]["fuera_de_tabla"] == {"n": 2, "ids": ["A", "B"]}
    assert out["resumen"]["factor_minimo"] is None and out["resumen"]["histograma_s_b"]["<3"] == 2
    cap = out["capacidad"][0]
    assert cap["a_suma_ultimas_reducidas"] is None and "S/B < 3" in cap["notas"][0]
    assert "cumple" not in str(cap["capacidad_grupo"]).lower().replace("no determinada", "")


# ------------------------------------------------------------- capacidad

CAB_MALLA = [{"id": "C9", "xs": [-0.6, 5.1, 5.1, -0.6], "ys": [-0.6, -0.6, 5.1, 5.1]}]


def test_capacidad_reduce_la_ultima_y_divide_por_fs():
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    cap = pl.evaluar_separacion(pil, scope="by_footing", cabezales=CAB_MALLA, q_ult=191.25, fs=2.25)["capacidad"][0]
    assert cap["a_suma_ultimas_reducidas"] == round(191.25 * 0.9 * 9, 4)
    assert cap["q_adm_grupo_por_a"] == round(191.25 * 0.9 * 9 / 2.25, 4)
    assert "PENDIENTE" in cap["b_pila_equivalente"] and "NO DETERMINADA" in cap["capacidad_grupo"]


def test_q_adm_ya_calculada_declara_la_condicion_del_fs():
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    cap = pl.evaluar_separacion(pil, scope="by_footing", cabezales=CAB_MALLA, q_adm=85.0)["capacidad"][0]
    assert cap["q_adm_grupo_por_a"] == round(85.0 * 0.9 * 9, 4)
    assert cap["a_suma_ultimas_reducidas"] is None and "FS no cambia" in cap["notas"][0]


def test_sin_fs_no_se_anuncia_admisible():
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    cap = pl.evaluar_separacion(pil, scope="by_footing", cabezales=CAB_MALLA, q_ult=100.0)["capacidad"][0]
    assert cap["q_adm_grupo_por_a"] is None and "Sin FS" in cap["notas"][0]


def test_capacidad_no_se_calcula_en_barrido_global_ni_con_vias_mezcladas():
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    out = pl.evaluar_separacion(pil, q_ult=100.0, fs=2.0)
    assert out["capacidad"] == [] and any("no es un grupo" in a for a in out["avisos"])
    with pytest.raises(pl.PilotesError, match="no ambos"):
        pl.evaluar_separacion(pil, q_ult=100.0, q_adm=40.0)
    with pytest.raises(pl.PilotesError, match="fs solo"):
        pl.evaluar_separacion(pil, fs=2.0, q_adm=40.0)


def test_pilote_solo_en_su_cabezal_no_es_fuera_de_tabla():
    frames = malla_3x3() + [frame("SOLO", 30.0, 30.0)]
    pil, _ = pl.pilotes_desde_frames(frames, SECCIONES)
    caps = CAB_MALLA + [{"id": "C1", "xs": [29, 31, 31, 29], "ys": [29, 29, 31, 31]}]
    out = pl.evaluar_separacion(pil, scope="by_footing", cabezales=caps, q_ult=100.0, fs=2.0)
    solo = next(p for p in out["pilotes"] if p.id == "SOLO")
    assert solo.sin_vecino and solo.s_b is None and solo.factor == 1.0 and not solo.fuera_de_tabla
    assert out["resumen"]["fuera_de_tabla"]["n"] == 0 and out["resumen"]["sin_vecino"]["ids"] == ["SOLO"]
    assert out["resumen"]["factor_minimo"] == 0.9  # el factor 1.0 del solitario no entra en el promedio
    c1 = next(c for c in out["capacidad"] if c["cabezal"] == "C1")
    assert c1["a_suma_ultimas_reducidas"] == 100.0 and c1["q_adm_grupo_por_a"] == 50.0
    pil1, _ = pl.pilotes_desde_frames([frame("UNICO", 0, 0)], SECCIONES)
    unico = pl.evaluar_separacion(pil1)["pilotes"][0]
    assert unico.sin_vecino and unico.vecinos == [] and unico.factor == 1.0


def test_sb_del_pilote_es_la_pareja_mas_desfavorable_no_la_mas_cercana():
    secciones = {"P60": {"diametro": 0.6, "material": "C280"}, "P120": {"diametro": 1.2, "material": "C280"}}
    frames = [frame("A", 0, 0, "P60"), frame("B", 2.0, 0, "P60"), frame("C", 2.2, 2.0, "P120")]
    pil, _ = pl.pilotes_desde_frames(frames, secciones)
    out = pl.evaluar_separacion(pil)
    a = next(p for p in out["pilotes"] if p.id == "A")
    assert a.vecinos[0]["id"] == "B" and a.vecinos[0]["s_b"] == round(2.0 / 0.6, 6)
    assert a.pareja_s_b == "C" and a.s_b == round(math.hypot(2.2, 2.0) / 1.2, 6) and a.fuera_de_tabla


def test_punto_aislado_lejos_no_barre_anillos_vacios():
    import time
    frames = malla_3x3() + [frame("LEJOS", 100000.0, 100000.0)]
    pil, _ = pl.pilotes_desde_frames(frames, SECCIONES)
    t0 = time.perf_counter()
    pl.asignar_vecinos(pil, 1, "step_down")
    assert time.perf_counter() - t0 < 0.5
    lejos = next(p for p in pil if p.id == "LEJOS")
    assert lejos.vecinos[0]["id"] == "F22" and lejos.factor == 1.0 and not lejos.sin_vecino


# ----------------------------------------------------------- por cabezal

def cabezal(cid, x0, y0, x1, y1):
    return {"id": cid, "xs": [x0, x1, x1, x0], "ys": [y0, y0, y1, y1]}


def test_by_footing_agrupa_por_punto_en_poligono():
    frames = malla_3x3() + [frame("G1", 20.0, 0.0), frame("G2", 20.0, 1.8), frame("SOLO", 40.0, 40.0)]
    pil, _ = pl.pilotes_desde_frames(frames, SECCIONES)
    caps = [cabezal("C9", -0.6, -0.6, 5.1, 5.1), cabezal("C2", 19.0, -1.0, 21.0, 3.0)]
    out = pl.evaluar_separacion(pil, scope="by_footing", cabezales=caps)
    por = {g["cabezal"]: g for g in out["grupos"]}
    assert por["C9"]["n_pilotes"] == 9 and por["C9"]["factor_minimo"] == 0.9 and por["C9"]["suma_factores"] == 8.1
    assert por["C2"]["n_pilotes"] == 2 and por["C2"]["s_b_min"] == 4.0 and por["C2"]["factor_minimo"] == 0.8
    g2 = next(p for p in out["pilotes"] if p.id == "G2")
    assert g2.vecinos[0]["id"] == "G1"  # vecino dentro del cabezal, no el F22 de la malla
    solo = next(p for p in out["pilotes"] if p.id == "SOLO")
    assert solo.grupo is None and solo.vecinos[0]["id"] in {"G1", "G2"}
    assert any("fuera de todo cabezal" in a for a in out["avisos"])
    assert len(out["capacidad"]) == 2


def test_by_footing_sin_cabezales_es_error():
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), SECCIONES)
    with pytest.raises(pl.PilotesError):
        pl.evaluar_separacion(pil, scope="by_footing")


def test_punto_en_poligono_borde_y_concavo():
    xs, ys = [0, 4, 4, 2, 2, 0], [0, 0, 4, 4, 2, 2]
    assert pl.punto_en_poligono(1, 1, xs, ys) and pl.punto_en_poligono(3, 3, xs, ys)
    assert not pl.punto_en_poligono(1, 3, xs, ys)
    assert pl.punto_en_poligono(0, 1, xs, ys)  # sobre el borde cuenta


# ------------------------------------------------- avisos y filtro de secciones

def test_pilote_duplicado_se_reporta_y_se_excluye():
    pil, _ = pl.pilotes_desde_frames(malla_3x3() + [frame("DUP", 2.25, 2.25)], SECCIONES)
    out = pl.evaluar_separacion(pil)
    assert len(out["pilotes"]) == 9 and all(p.s_b == 5.0 for p in out["pilotes"])
    assert any("DUP duplica la coordenada de F11" in a for a in out["avisos"])


def test_diametros_mezclados_usa_el_mayor_y_avisa():
    secciones = {**SECCIONES, "P60": {"diametro": 0.60, "material": "C280"}}
    pil, avisos = pl.pilotes_desde_frames([frame("A", 0, 0), frame("B", 2.4, 0, "P60")], secciones)
    assert any("Diametros mezclados" in a for a in avisos)
    out = pl.evaluar_separacion(pil)
    assert all(p.s_b == 4.0 and p.factor == 0.8 for p in out["pilotes"])


def test_sin_secciones_circulares_exige_filtro_y_diametro():
    with pytest.raises(pl.PilotesError, match="circulares"):
        pl.pilotes_desde_frames(malla_3x3(), {})
    with pytest.raises(pl.PilotesError, match="diametro"):
        pl.pilotes_desde_frames(malla_3x3(), {}, sections=["P45"])
    pil, _ = pl.pilotes_desde_frames(malla_3x3(), {}, sections=["P45"], diameter=0.45)
    assert len(pil) == 9 and pil[0].diametro == 0.45


def test_filtro_explicito_no_adivina_por_nombre():
    frames = malla_3x3() + [frame("COL", 50, 50, "C40x40")]
    pil, _ = pl.pilotes_desde_frames(frames, SECCIONES, sections=["P45"])
    assert {p.seccion for p in pil} == {"P45"}
    with pytest.raises(pl.PilotesError):
        pl.pilotes_desde_frames(frames, SECCIONES, sections=[])
    with pytest.raises(pl.PilotesError):
        pl.pilotes_desde_frames(frames, SECCIONES, sections="P45")


def test_cabeza_es_la_z_mayor_y_los_inclinados_se_marcan():
    pil, avisos = pl.pilotes_desde_frames(
        [frame("V", 1, 1, z_top=-12.0, z_bot=0.0), frame("I", 5, 5, x2=5.5, y2=5.0)], SECCIONES)
    v = next(p for p in pil if p.id == "V")
    assert v.z_cabeza == 0.0 and v.punto_cabeza == "BV" and v.punto_punta == "TV" and not v.inclinado
    i = next(p for p in pil if p.id == "I")
    assert i.inclinado and (i.x, i.y) == (5.0, 5.0)
    assert any("inclinado" in a for a in avisos)


def test_todo_filtrado_es_error_no_informe_vacio():
    with pytest.raises(pl.PilotesError, match="Ningun pilote"):
        pl.evaluar_separacion([])


# ------------------------------------------------------------- envolvente

def test_envolvente_axial_critico_y_ratio():
    regs = [{"pilote": "A", "caso": "ENV", "paso": "Max", "axial": 70.0},
            {"pilote": "A", "caso": "ENV", "paso": "Min", "axial": -5.0},
            {"pilote": "B", "caso": "C1", "paso": "", "axial": 90.0},
            {"pilote": "B", "caso": "C2", "paso": "", "axial": 60.0}]
    out = pl.envolvente_axial(regs, q_adm=85.0)
    assert out["critico"]["pilote"] == "B" and out["critico"]["caso"] == "C1"
    assert out["ratio_max"] == round(90 / 85, 4) and out["no_cumplen"] == ["B"]
    a = next(f for f in out["pilotes"] if f["pilote"] == "A")
    assert a["traccion_max"] == 5.0 and a["caso_traccion"] == "ENV" and a["cumple_q_adm"]
    assert "cumple_q_adm" not in pl.envolvente_axial(regs)["pilotes"][0]


def test_envolvente_ratio_sin_redondear_y_traccion_pura_no_cumple_por_defecto():
    regs = [{"pilote": "A", "caso": "C", "paso": "", "axial": 85.004},
            {"pilote": "T", "caso": "C", "paso": "", "axial": -12.0}]
    out = pl.envolvente_axial(regs, q_adm=85.0)
    a = next(f for f in out["pilotes"] if f["pilote"] == "A")
    assert a["ratio"] == 1.0 and a["cumple_q_adm"] is False and out["no_cumplen"] == ["A"]
    t = next(f for f in out["pilotes"] if f["pilote"] == "T")
    assert t["cumple_q_adm"] is None and out["solo_traccion_sin_evaluar"] == ["T"]
