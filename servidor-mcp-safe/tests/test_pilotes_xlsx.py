"""Libro de verificacion (pilotes_xlsx) sobre datos SINTETICOS: malla 3x3 a 2.25 m, dos cabezales."""
import pytest
from openpyxl import load_workbook

import pilotes as pl
import pilotes_xlsx as px


def frame(fid, x, y, seccion="P45"):
    return {"id": fid, "seccion": seccion, "p1": f"T{fid}", "p2": f"B{fid}",
            "x1": x, "y1": y, "z1": 0.0, "x2": x, "y2": y, "z2": -12.0}


SECC = {"P45": {"diametro": 0.45, "material": "C"}}
COMBOS = {"D": {"tipos": [0], "casos": ["Dead"], "sf": [1.0]},
          "DL": {"tipos": [0, 0], "casos": ["Dead", "Live"], "sf": [1.0, 1.0]},
          "DLS": {"tipos": [0, 0, 1], "casos": ["Dead", "Live", "QX"], "sf": [1.165, 1.0, 0.714]},
          "DCon1": {"tipos": [0], "casos": ["Dead"], "sf": [1.4]},
          "U": {"tipos": [0, 0], "casos": ["Dead", "Live"], "sf": [1.2, 1.6]},
          "E": {"tipos": [1, 1], "casos": ["DLS", "DL"], "sf": [1.0, 1.0]}}


def separacion(frames, cabezales):
    pil, avisos = pl.pilotes_desde_frames(frames, SECC)
    out = pl.evaluar_separacion(pil, "by_footing", 1, "step_down", cabezales)
    return {"alcance": "by_footing", "modelo": "m.fdb", "unidades": {"preset": "kN, m, C", "fuerza": "kN", "longitud": "m"},
            "n_frames_modelo": len(frames), "pilotes": [pl.pilote_a_dict(p, 1000.0) for p in out["pilotes"]],
            "grupos": out["grupos"], "resumen": out["resumen"], "avisos": avisos + out["avisos"]}


def reacciones(cargas, combos=("D", "DL", "DLS", "DCon1", "U")):
    """cargas: {pilote: carga base}; cada combo escala la base por un factor fijo."""
    esc = {"D": 0.6, "DL": 1.0, "DLS": 1.1, "DCon1": 0.84, "U": 1.5}
    regs = [{"pilote": p, "punto": f"B{p}", "caso": c, "paso": "Max" if c == "DLS" else "", "axial": v * esc[c]}
            for p, v in cargas.items() for c in combos]
    regs += [{"pilote": p, "punto": f"B{p}", "caso": "DLS", "paso": "Min", "axial": v * 0.2 - 50}
             for p, v in cargas.items()]
    return {"unidades": {"preset": "kN, m, C", "fuerza": "kN", "longitud": "m"}, "registros": regs, "avisos": []}


def malla():
    return [frame(f"F{i}{j}", i * 2.25, j * 2.25) for i in range(3) for j in range(3)]


CAB9 = [{"id": "C9", "xs": [-0.6, 5.1, 5.1, -0.6], "ys": [-0.6, -0.6, 5.1, 5.1]}]


def test_clasifica_combos_por_definicion_no_por_nombre():
    c = px.clasificar_combos(COMBOS)
    assert c["D"] == px.CLASE_SERV_GRAV and c["DL"] == px.CLASE_SERV_GRAV
    assert c["DLS"] == px.CLASE_SERV_SISMO
    assert c["DCon1"].startswith("diseno") and c["U"] == px.CLASE_DISENO
    assert c["E"] == px.CLASE_ENVOLVENTE
    # Con tipos de caso: una combo de solo espectros (QX) es envolvente aunque sus factores sean 1.0,
    # y una gravitatoria con un caso de espectro es servicio sismico.
    extra = {"QX": {"tipos": [0, 0], "casos": ["Qx1", "Qx2"], "sf": [1.0, 1.0], "tipos_caso": [4, 4]},
             "DQ": {"tipos": [0, 0], "casos": ["Dead", "Qx1"], "sf": [1.0, 0.714], "tipos_caso": [1, 4]},
             "DQU": {"tipos": [0, 0], "casos": ["Dead", "Qx1"], "sf": [1.4, 1.0], "tipos_caso": [1, 4]},
             # Sismo estatico equivalente: caso lineal (1) con patron Quake (5), como Qx(1/2) en SAFE.
             "QXS": {"tipos": [0, 0], "casos": ["Qx1", "Qx2"], "sf": [1.0, 1.0], "tipos_caso": [1, 1], "tipos_patron": [5, 5]},
             "DQS": {"tipos": [0, 0], "casos": ["Dead", "Qx1"], "sf": [0.735, 0.714], "tipos_caso": [1, 1], "tipos_patron": [1, 5]}}
    c2 = px.clasificar_combos(extra)
    assert c2["QX"] == px.CLASE_ENVOLVENTE and c2["DQ"] == px.CLASE_SERV_SISMO and c2["DQU"] == px.CLASE_DISENO
    assert c2["QXS"] == px.CLASE_ENVOLVENTE and c2["DQS"] == px.CLASE_SERV_SISMO


def test_filas_cabezal_y_candidatos_por_baja_demanda():
    cargas = {f"F{i}{j}": 300.0 for i in range(3) for j in range(3)}
    cargas["F11"] = 120.0  # el menos cargado
    ver = px.armar_verificacion(separacion(malla(), CAB9), reacciones(cargas), COMBOS, q_adm=800.0)
    r = ver["resumen"]
    assert r["servicio"] == ["D", "DL", "DLS"] and r["geometria_conforme"] and r["n_no_cumplen"] == 0
    f = next(x for x in ver["filas"] if x["id"] == "F00")
    assert f["q_red"] == 720.0 and f["p_serv"] == 330.0 and f["c_serv"] == "DLS Max" and f["p_dis"] == 450.0
    assert f["p_trac"] == 0.0 and f["ratio"] == pytest.approx(330 / 720) and f["estado"] == "OK"
    cab = ver["cabezales"][0]
    assert cab["cabezal"] == "C9" and cab["n"] == 9 and cab["suma_f"] == 8.1 and cab["cap_a"] == pytest.approx(6480.0)
    assert cab["dem"] == pytest.approx((8 * 300 + 120) * 1.1) and cab["combo_dem"] == "DLS Max"
    assert cab["estado"].startswith("OK frente a (a); (b) PENDIENTE")
    # con un pilote menos: 0.9 * 8 * 0.9 * 800 = 5184 >= 2772 -> sobran varios; el primero es F11
    assert cab["sobran"] >= 1 and ver["candidatos"][0]["id"] == "F11" and "baja demanda" in ver["candidatos"][0]["motivo"]
    assert r["candidatos_por_motivo"]["baja demanda"] == cab["sobran"] and r["critico"]["id"] != "F11"


def test_no_cumple_traccion_y_cabezal_sobre_a():
    cargas = {f"F{i}{j}": 900.0 for i in range(3) for j in range(3)}
    ver = px.armar_verificacion(separacion(malla(), CAB9), reacciones(cargas), COMBOS, q_adm=800.0)
    assert ver["resumen"]["n_no_cumplen"] == 9 and ver["resumen"]["cabezales_no_cumplen"] == ["C9"]
    assert ver["cabezales"][0]["sobran"] == 0 and ver["resumen"]["n_candidatos"] == 0
    f = ver["filas"][0]
    assert f["estado"].startswith("NO CUMPLE") and f["p_trac"] == 0.0
    ver2 = px.armar_verificacion(separacion(malla(), CAB9), reacciones({k: 100.0 for k in cargas}), COMBOS, 800.0)
    assert ver2["resumen"]["n_con_traccion"] == 9 and ver2["filas"][0]["p_trac"] == 30.0 and ver2["filas"][0]["c_trac"] == "DLS Min"


def test_pareja_fuera_de_tabla_duplicado_e_inclinado():
    frames = malla() + [frame("A", 20.0, 0.0), frame("B", 21.2, 0.0), frame("DUP", 2.25, 2.25)]
    frames[-1]["x1"] = 2.25  # misma coordenada que F11
    inclinado = frame("INC", 20.0, 3.0)
    inclinado["x2"] = 20.6
    frames.append(inclinado)
    caps = CAB9 + [{"id": "C2", "xs": [19, 22, 22, 19], "ys": [-1, -1, 4, 4]}]
    cargas = {f["id"]: 300.0 for f in frames}
    ver = px.armar_verificacion(separacion(frames, caps), reacciones(cargas), COMBOS, q_adm=800.0)
    r = ver["resumen"]
    assert not r["geometria_conforme"] and r["fuera_de_tabla"]["ids"] == ["A", "B"]
    por = {f["id"]: f for f in ver["filas"]}
    assert por["DUP"]["revisar"] == "duplicado de F11" and por["DUP"]["estado"] == "REVISAR MODELO" and por["DUP"]["cabezal"] == "C9"
    assert por["INC"]["revisar"] == "frame inclinado" and por["INC"]["estado"] == "REVISAR MODELO"
    assert por["A"]["estado"].startswith("SIN FACTOR") and por["A"]["q_red"] is None
    c2 = next(c for c in ver["cabezales"] if c["cabezal"] == "C2")
    assert c2["estado"].startswith("SIN FACTOR") and c2["excluidos"] == "INC" and c2["cap_a"] is None
    motivos = {c["id"]: c["motivo"] for c in ver["candidatos"]}
    assert motivos["DUP"].startswith("modelo") and motivos["A"].startswith("geometria") and motivos["B"].startswith("geometria")
    assert r["candidatos_por_motivo"] == {"baja demanda": r["candidatos_por_motivo"]["baja demanda"], "geometria": 2, "modelo": 1}
    assert r["cabezales_sin_factor"] == ["C2"] and "DUP (duplicado de F11)" in r["revisar_modelo"]


def test_service_combos_explicitas_y_errores():
    cargas = {f"F{i}{j}": 300.0 for i in range(3) for j in range(3)}
    sep, rea = separacion(malla(), CAB9), reacciones(cargas)
    ver = px.armar_verificacion(sep, rea, COMBOS, 800.0, service_combos=["D", "U"])
    assert ver["resumen"]["servicio"] == ["D", "U"] and ver["filas"][0]["p_serv"] == 450.0
    assert ver["clase_combos"]["U"].startswith("servicio (indicada")
    with pytest.raises(pl.PilotesError, match="inexistentes"):
        px.armar_verificacion(sep, rea, COMBOS, 800.0, service_combos=["NO"])
    with pytest.raises(pl.PilotesError, match="q_adm"):
        px.armar_verificacion(sep, rea, COMBOS, 0.0)
    with pytest.raises(pl.PilotesError, match="margen"):
        px.armar_verificacion(sep, rea, COMBOS, 800.0, margen_candidato=1.5)
    with pytest.raises(pl.PilotesError, match="by_footing"):
        px.armar_verificacion({**sep, "alcance": "nearest_neighbor"}, rea, COMBOS, 800.0)
    with pytest.raises(pl.PilotesError, match="servicio"):
        px.armar_verificacion(sep, rea, {"DCon1": COMBOS["DCon1"]}, 800.0)


def test_escribe_libro_legible(tmp_path):
    cargas = {f"F{i}{j}": 300.0 for i in range(3) for j in range(3)}
    ver = px.armar_verificacion(separacion(malla(), CAB9), reacciones(cargas), COMBOS, q_adm=800.0)
    path = str(tmp_path / "v.xlsx")
    hojas = px.escribir_libro(ver, path, {"modelo": "m.fdb", "unidades": "kN, m, C"})
    assert hojas == ["Resumen", "Pilotes", "Cabezales", "Candidatos", "Propuesta", "Combos", "Criterios"]
    wbp = load_workbook(path)["Propuesta"]
    assert wbp["A1"].value == "Cabezal" and wbp["A2"].value == "C9" and wbp["K2"].value == "quitar"
    assert any("reanalizar" in str(c.value) or "Reanaliz" in str(c.value) or "reanalisis" in str(c.value).lower()
               for row in wbp.iter_rows() for c in row)
    wb = load_workbook(path)
    resumen = {r[0].value: r[1].value for r in wb["Resumen"].iter_rows() if r[0].value}
    assert resumen["GEOMETRIA CONFORME A TABLA 5.1"] == "SI" and resumen["Modelo"] == "m.fdb"
    assert "PENDIENTE" in resumen["Capacidad (b) pila equivalente"] and "cumple" in resumen["Capacidad (b) pila equivalente"]
    p = wb["Pilotes"]
    assert p["A1"].value == "Pilote" and p.max_row == 10 and p["L2"].value == 0.9
    assert wb["Cabezales"]["A2"].value == "C9" and wb["Combos"].max_row == 7
    assert any("reanalizar" in str(c.value) for row in wb["Candidatos"].iter_rows() for c in row)


# ------------------------------------------------------------- propuesta

def test_propuesta_anadir_quitar_reespaciar_y_totales():
    frames = malla() + [frame("A", 20.0, 0.0), frame("B", 21.2, 0.0), frame("S", 40.0, 40.0)]
    caps = CAB9 + [{"id": "C2", "xs": [19, 22, 22, 19], "ys": [-1, -1, 1, 1]},
                   {"id": "C1", "xs": [39, 41, 41, 39], "ys": [39, 39, 41, 41]}]
    cargas = {f"F{i}{j}": 300.0 for i in range(3) for j in range(3)}   # 9 x 330 = 2970 < 0.9*8*0.9*800
    cargas.update({"A": 400.0, "B": 400.0, "S": 900.0})                  # S: 990 > 0.9*800 -> anadir
    ver = px.armar_verificacion(separacion(frames, caps), reacciones(cargas), COMBOS, q_adm=800.0)
    prop = ver["propuesta"]
    por = {f["cabezal"]: f for f in prop["filas"]}
    assert por["C9"]["accion"] == "quitar" and por["C9"]["n_min_xi"] == 5 and por["C9"]["delta"] == -4
    assert por["C9"]["pilotes"].count(",") == 3 and "quitar hasta 4" in por["C9"]["detalle"]
    assert por["C1"]["accion"] == "anadir" and por["C1"]["n_min_xi"] == 2 and por["C1"]["delta"] == 1
    assert por["C2"]["accion"] == "reespaciar" and por["C2"]["n_min_malla"] == 2 and por["C2"]["n_min_xi"] is None
    assert prop["totales"] == {"anadir": 1, "quitar": 1, "redistribuir": 0, "reespaciar": 1, "mantener": 0, "sin_resultado": 0}
    assert prop["n_pilotes_hoy"] == 12 and prop["n_pilotes_propuesta"] == 12 - 4 + 1 + 0
    assert [f["accion"] for f in prop["filas"]] == ["reespaciar", "anadir", "quitar"]
    assert ver["resumen"]["propuesta"]["totales"] == prop["totales"] and len(prop["advertencias"]) == 4
    with pytest.raises(pl.PilotesError):
        px.proponer_cambios(ver, 800.0, xi_malla=1.5)


def test_propuesta_mantener_y_sin_resultado():
    cargas = {f"F{i}{j}": 500.0 for i in range(3) for j in range(3)}  # 9 x 550 = 4950 -> n_min 8*... 4950/(0.9*800*0.9)=7.6 -> 8
    ver = px.armar_verificacion(separacion(malla(), CAB9), reacciones(cargas), COMBOS, q_adm=800.0)
    f = ver["propuesta"]["filas"][0]
    assert f["accion"] == "quitar" and f["n_min_xi"] == 8 and f["delta"] == -1
    ver2 = px.armar_verificacion(separacion(malla(), CAB9), reacciones({"ZZ": 1.0}), COMBOS, q_adm=800.0)
    assert ver2["propuesta"]["filas"][0]["accion"] == "sin_resultado"


def test_comparar_verificaciones_detecta_mejora_y_empeora():
    cargas = {f"F{i}{j}": 300.0 for i in range(3) for j in range(3)}
    antes = px.armar_verificacion(separacion(malla(), CAB9), reacciones(cargas), COMBOS, q_adm=800.0)
    frames2 = [f for f in malla() if f["id"] != "F11"]
    cargas2 = {k: 340.0 for k in cargas if k != "F11"}
    cargas2["F00"] = -200.0
    despues = px.armar_verificacion(separacion(frames2, CAB9), reacciones(cargas2), COMBOS, q_adm=800.0)
    cmp_ = px.comparar_verificaciones(antes, despues)
    assert cmp_["global"]["n_pilotes"] == (9, 8) and cmp_["cabezales"][0]["n"] == (9, 8)
    assert cmp_["empeoran"] == [] and cmp_["mejoran"] == ["C9"]  # la demanda total baja con F00 en traccion
    assert cmp_["traccion_max"][0] == 0.0 and cmp_["traccion_max"][1] == pytest.approx(220.0)  # F00 solo despues
    assert cmp_["critico"][1]["id"] != "F11"


def test_propuesta_redistribuir_cuando_la_suma_cumple_pero_un_pilote_no():
    cargas = {f"F{i}{j}": 200.0 for i in range(3) for j in range(3)}
    cargas["F22"] = 700.0   # 770 > 720: NO CUMPLE individual; suma 2370 < 0.9*8*720 -> sobrarian 2 por suma
    ver = px.armar_verificacion(separacion(malla(), CAB9), reacciones(cargas), COMBOS, q_adm=800.0)
    f = ver["propuesta"]["filas"][0]
    assert f["accion"] == "redistribuir" and f["delta"] == 0 and "F22" in f["detalle"] and f["n_min_xi"] < 9
    assert ver["propuesta"]["totales"]["redistribuir"] == 1 and ver["propuesta"]["n_pilotes_propuesta"] == 9
