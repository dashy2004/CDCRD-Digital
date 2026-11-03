"""Capa COM de get_pile_spacing / get_pile_axial_reactions sobre el mock de conftest.

Contratos py-> del typelib SAFEv1 (ver bloque PILOTES en Safe.py). Fixture
SINTETICA: malla 3x3 a 2.25 m con P45 (T3 = 0.45 m) -> S/B 5.00, factor 0.90.
Estos tests prueban el cliente, NO prueban SAFE.
"""
import json

import pytest
from Safe import SafeError

PASO = 2.25
UNITS_KN_M = 6   # "kN, m, C"


def malla(n=3, paso=PASO, z_top=0.0, z_bot=-12.0):
    frames = []
    for i in range(n):
        for j in range(n):
            frames.append((f"F{i}{j}", "P45", f"T{i}{j}", f"B{i}{j}", i * paso, j * paso, z_top,
                           i * paso, j * paso, z_bot))
    return frames


def get_all_frames(frames):
    """py-> (n, Name, PropName, StoryName, P1, P2, X1, Y1, Z1, X2, Y2, Z2, Angle, Offset x6, CardinalPoint, ret)."""
    cols = [list(c) for c in zip(*frames)]
    n = len(frames)
    return (n, cols[0], cols[1], ["Base"] * n, *cols[2:], [0.0] * n, *[[0.0] * n for _ in range(6)], [8] * n, 0)


@pytest.fixture
def pile_api(api):
    safe, model, state = api
    state["units"] = UNITS_KN_M
    state["frames"] = malla()
    model.FrameObj.GetAllFrames.side_effect = lambda *a: get_all_frames(state["frames"])
    state["props"] = {"P45": (9, 0.45, "C280"), "C40x40": (8, 0.0, "C280")}
    def name_list(n=0, names=None, prop_type=0):
        keys = [k for k, v in state["props"].items() if prop_type in (0, v[0])]
        return (len(keys), keys, 0)
    model.PropFrame.GetNameList.side_effect = name_list
    model.PropFrame.GetTypeOAPI.side_effect = lambda name: (state["props"][name][0], 0)
    model.PropFrame.GetCircle.side_effect = lambda name: ("", state["props"][name][2], state["props"][name][1], -1, "", "g", 0)
    # Cabezal: el area A1 de conftest envuelve toda la malla.
    model.AreaObj.GetAllAreas.return_value = (1, ["A1"], [1], 4, [3], ["P1", "P2", "P3", "P4"],
                                              [-0.5, 5.0, 5.0, -0.5], [-0.5, -0.5, 5.0, 5.0], [0.] * 4, 0)
    # Resultados
    model.Analyze.GetCaseStatus.return_value = (2, ["Dead", "Live"], [4, 4], 0)
    model.RespCombo.GetNameList.return_value = (2, ["COMB1", "ENV"], 0)
    state["combos"] = {"COMB1": ([0, 0], ["Dead", "Live"], [1.0, 1.0]),
                       "ENV": ([0, 0, 1], ["Dead", "Live", "QX"], [1.165, 1.0, 0.714])}
    model.RespCombo.GetCaseList.side_effect = lambda name: (len(state["combos"][name][0]), *state["combos"][name], 0)
    model.LoadCases.GetTypeOAPI_1.side_effect = lambda name: (1, 0, 5 if name.startswith("Q") else 1, 0, 0, 0)
    model.Results.Setup.DeselectAllCasesAndCombosForOutput.return_value = 0
    model.Results.Setup.SetComboSelectedForOutput.return_value = 0
    model.Results.Setup.SetCaseSelectedForOutput.return_value = 0
    state["react"] = {}
    def joint_react(point, item_type):
        rows = state["react"].get(point, [])
        return (len(rows), [point] * len(rows), [point] * len(rows), [r[0] for r in rows],
                [r[1] for r in rows], [0.0] * len(rows), [0.0] * len(rows), [0.0] * len(rows),
                [r[2] for r in rows], [0.0] * len(rows), [0.0] * len(rows), [0.0] * len(rows), 0)
    model.Results.JointReact.side_effect = joint_react
    state["force"] = {}
    def frame_force(name, item_type):
        rows = state["force"].get(name, [])
        n = len(rows)
        return (n, [name] * n, [r[3] for r in rows], [name] * n, [r[3] for r in rows], [r[0] for r in rows],
                [r[1] for r in rows], [0.0] * n, [r[2] for r in rows], *[[0.0] * n for _ in range(5)], 0)
    model.Results.FrameForce.side_effect = frame_force
    return safe, model, state


def salida(texto):
    return json.loads(texto)


# ------------------------------------------------------------ get_pile_spacing

def test_spacing_malla_3x3_sb_5_factor_0_90(pile_api):
    safe, model, state = pile_api
    out = salida(safe.get_pile_spacing())
    assert out["solo_lectura"] and out["n_pilotes"] == 9 and out["n_frames_modelo"] == 9
    assert out["unidades"] == {"preset": "kN, m, C", "fuerza": "kN", "longitud": "m"}
    assert out["secciones_circulares"] == {"P45": {"diametro": 0.45, "material": "C280", "diametro_mm": 450.0}}
    assert out["resumen"]["s_b"]["min"] == out["resumen"]["s_b"]["max"] == 5.0
    assert out["resumen"]["factor_minimo"] == 0.9 and out["resumen"]["fuera_de_tabla"]["n"] == 0
    assert all(p["factor"] == 0.9 and p["diametro_mm"] == 450.0 for p in out["pilotes"])
    assert out["criterio"]["interpolacion"] == "step_down"
    assert "cumple" not in json.dumps(out["capacidad"]).lower().replace("no determinada", "")
    model.File.Save.assert_not_called()


def test_spacing_fija_unidades_y_las_restaura(pile_api):
    safe, model, state = pile_api
    state["units"] = 9  # N, mm, C
    out = salida(safe.get_pile_spacing(units="kN, m, C"))
    assert model.SetPresentUnits.call_args_list[0].args == (UNITS_KN_M,)
    assert state["units"] == 9 and out["unidades"]["preset"] == "kN, m, C"


def test_spacing_en_mm_convierte_diametro_y_tolerancia(pile_api):
    safe, model, state = pile_api
    state["frames"] = [f[:4] + (f[4] * 1000, f[5] * 1000, f[6], f[7] * 1000, f[8] * 1000, f[9]) for f in malla()]
    state["props"]["P45"] = (9, 450.0, "C280")
    out = salida(safe.get_pile_spacing(units="N, mm, C"))
    assert out["unidades"]["longitud"] == "mm" and out["pilotes"][0]["diametro_mm"] == 450.0
    assert out["resumen"]["s_b"]["mediana"] == 5.0 and out["resumen"]["separacion"]["min"] == 2250.0


def test_spacing_verifica_tipo_circular_y_no_adivina_por_nombre(pile_api):
    safe, model, state = pile_api
    state["frames"] = malla() + [("COL1", "C40x40", "TC", "BC", 1.0, 1.0, 0.0, 1.0, 1.0, -3.0)]
    model.PropFrame.GetNameList.side_effect = lambda *a: (2, ["P45", "C40x40"], 0)  # ret=0 fuera de filtro
    out = salida(safe.get_pile_spacing())
    assert out["n_pilotes"] == 9 and list(out["secciones_circulares"]) == ["P45"]
    model.PropFrame.GetCircle.assert_called_once_with("P45")


def test_spacing_sin_circulares_exige_seccion_y_diametro(pile_api):
    safe, model, state = pile_api
    state["props"] = {"C40x40": (8, 0.0, "C280")}
    state["frames"] = [f[:1] + ("C40x40",) + f[2:] for f in malla()]
    with pytest.raises(SafeError, match="circulares"):
        safe.get_pile_spacing()
    out = salida(safe.get_pile_spacing(sections=["C40x40"], diameter_mm=450.0))
    assert out["n_pilotes"] == 9 and out["pilotes"][0]["diametro"] == 0.45 and out["resumen"]["s_b"]["min"] == 5.0


def test_spacing_seccion_sin_frames_es_error_claro(pile_api):
    safe, model, state = pile_api
    state["props"]["P60"] = (9, 0.6, "C280")
    with pytest.raises(SafeError, match="Ningun frame usa"):
        safe.get_pile_spacing(sections=["P60"])


def test_spacing_by_footing_lee_cabezales_tipo_footing(pile_api):
    safe, model, state = pile_api
    out = salida(safe.get_pile_spacing(scope="by_footing"))
    assert out["grupos"][0]["cabezal"] == "A1" and out["grupos"][0]["n_pilotes"] == 9
    assert out["capacidad"][0]["cabezal"] == "A1"
    model.PropArea.GetSlab.assert_called_with("S1")
    model.PropArea.GetSlab.return_value = (0, 1, "C1", 400., -1, "", "guid", 0)  # Slab, no cabezal
    out = salida(safe.get_pile_spacing(scope="by_footing"))
    assert out["grupos"] == [] and any("fuera de todo cabezal" in a for a in out["avisos"])
    with pytest.raises(SafeError, match="cap_types"):
        safe.get_pile_spacing(scope="by_footing", cap_types="pedestal")


def test_spacing_capacidad_y_linear_declarados(pile_api):
    safe, model, state = pile_api
    out = salida(safe.get_pile_spacing(scope="by_footing", interpolation="linear", q_ult=191.25, fs=2.25))
    assert out["criterio"]["interpolacion"] == "linear"
    cap = out["capacidad"][0]
    assert cap["a_suma_ultimas_reducidas"] == round(191.25 * 0.9 * 9, 4) and "PENDIENTE" in cap["b_pila_equivalente"]


def test_spacing_duplicado_y_max_detail(pile_api):
    safe, model, state = pile_api
    state["frames"] = malla() + [("DUP", "P45", "TD", "BD", PASO, PASO, 0.0, PASO, PASO, -12.0)]
    out = salida(safe.get_pile_spacing(max_detail=2))
    assert out["n_pilotes"] == 9 and len(out["pilotes"]) == 2 and out["pilotes_omitidos_en_detalle"] == 7
    assert any("DUP duplica" in a for a in out["avisos"])


@pytest.mark.parametrize("path", ["FrameObj.GetAllFrames", "PropFrame.GetNameList", "PropFrame.GetTypeOAPI", "PropFrame.GetCircle"])
def test_spacing_ret_no_cero_es_safeerror(pile_api, path):
    safe, model, state = pile_api
    fn = model
    for part in path.split("."):
        fn = getattr(fn, part)
    old = fn.side_effect
    fn.side_effect = lambda *a: (*old(*a)[:-1], 5)
    with pytest.raises(SafeError):
        safe.get_pile_spacing()


def test_spacing_longitud_incoherente_no_es_exito(pile_api):
    safe, model, state = pile_api
    model.FrameObj.GetAllFrames.side_effect = lambda *a: (*get_all_frames(malla())[:1], ["F00"], *get_all_frames(malla())[2:])
    with pytest.raises(SafeError, match="incoherente"):
        safe.get_pile_spacing()


# ---------------------------------------------------- get_pile_axial_reactions

def test_reactions_envolvente_y_critico_por_joint(pile_api):
    safe, model, state = pile_api
    for f in state["frames"]:
        state["react"][f[3]] = [("COMB1", "", 400.0), ("ENV", "Max", 450.0), ("ENV", "Min", 380.0)]
    state["react"]["B11"] = [("COMB1", "", 700.0), ("ENV", "Max", 820.0), ("ENV", "Min", -30.0)]
    out = salida(safe.get_pile_axial_reactions(q_adm=800.0))
    assert out["salida_seleccionada"]["combos"] == ["COMB1", "ENV"] and out["salida_seleccionada"]["casos"] == []
    model.Results.Setup.DeselectAllCasesAndCombosForOutput.assert_called_once()
    assert model.Results.Setup.SetComboSelectedForOutput.call_count == 2
    env = out["envolvente"]
    assert env["critico"]["pilote"] == "F11" and env["critico"]["caso"] == "ENV" and env["critico"]["compresion_max"] == 820.0
    assert env["no_cumplen"] == ["F11"] and env["ratio_max"] == 1.025
    f11 = next(f for f in env["pilotes"] if f["pilote"] == "F11")
    assert f11["traccion_max"] == 30.0 and not f11["cumple_q_adm"]
    assert out["n_pilotes"] == 9 and len(out["registros"]) == 27
    assert out["avisos"] == ["q_adm es carga de servicio: el ratio solo vale contra combinaciones "
                             "de servicio; con combos mayoradas (diseno) no significa nada."]
    model.File.Save.assert_not_called()


def test_reactions_por_frame_toma_la_peor_estacion(pile_api):
    safe, model, state = pile_api
    for f in state["frames"]:
        state["force"][f[0]] = [("COMB1", "", -100.0, 0.0), ("COMB1", "", -140.0, 6.0), ("COMB1", "", 20.0, 12.0)]
    out = salida(safe.get_pile_axial_reactions(source="frame", combos=["COMB1"]))
    assert out["fuente"] == "frame" and "-P" in out["convencion"]
    assert out["envolvente"]["critico"]["compresion_max"] == 140.0 and out["registros"][0]["estacion"] == 6.0
    model.Results.Setup.SetComboSelectedForOutput.assert_called_once_with("COMB1")
    # La estacion traccionada (P=+20 en 12.0) tambien se reporta, no se pierde tras la mas comprimida.
    f00 = [r for r in out["registros"] if r["pilote"] == "F00"]
    assert [r["axial"] for r in f00] == [140.0, -20.0] and f00[1]["estacion"] == 12.0
    assert out["envolvente"]["pilotes"][0]["traccion_max"] == 20.0


def test_reactions_paso_conserva_el_numero_de_paso_multistep(pile_api):
    safe, model, state = pile_api
    def joint_react(point, item_type):
        return (2, [point] * 2, [point] * 2, ["NL", "NL"], ["Step", "Step"], [1.0, 2.0],
                [0.] * 2, [0.] * 2, [100.0, 130.0], [0.] * 2, [0.] * 2, [0.] * 2, 0)
    model.Results.JointReact.side_effect = joint_react
    model.RespCombo.GetNameList.return_value = (0, [], 0)
    model.Analyze.GetCaseStatus.return_value = (1, ["NL"], [4], 0)
    out = salida(safe.get_pile_axial_reactions())
    assert out["envolvente"]["critico"]["paso"] == "Step 2" and out["envolvente"]["critico"]["compresion_max"] == 130.0


def test_unidades_se_restauran_aunque_la_lectura_falle(pile_api):
    safe, model, state = pile_api
    state["units"] = 9
    model.FrameObj.GetAllFrames.side_effect = lambda *a: (*get_all_frames(malla())[:-1], 3)
    with pytest.raises(SafeError):
        safe.get_pile_spacing(units="kN, m, C")
    assert state["units"] == 9
    assert model.SetPresentUnits.call_args_list[-1].args == (9,)


def test_reactions_sin_analisis_o_combo_inexistente(pile_api):
    safe, model, state = pile_api
    with pytest.raises(SafeError, match="inexistentes"):
        safe.get_pile_axial_reactions(combos=["NOEXISTE"])
    with pytest.raises(SafeError, match="sin resultados"):
        safe.get_pile_axial_reactions(cases=["Wind"])
    model.Analyze.GetCaseStatus.return_value = (2, ["Dead", "Live"], [1, 1], 0)
    with pytest.raises(SafeError, match="run_analysis"):
        safe.get_pile_axial_reactions()
    model.Results.Setup.SetComboSelectedForOutput.assert_not_called()


def test_reactions_sin_combos_usa_casos_listos_y_avisa_puntas_sin_reaccion(pile_api):
    safe, model, state = pile_api
    model.RespCombo.GetNameList.return_value = (0, [], 0)
    state["react"]["B00"] = [("Dead", "", 300.0)]
    out = salida(safe.get_pile_axial_reactions())
    assert out["salida_seleccionada"]["combos"] == [] and out["salida_seleccionada"]["casos"] == ["Dead", "Live"]
    assert out["envolvente"]["n_pilotes_con_resultado"] == 1 and "8 pilote(s) sin reaccion" in out["avisos"][0]


def test_reactions_source_invalido_y_secciones_no_circulares(pile_api):
    safe, model, state = pile_api
    with pytest.raises(SafeError, match="source"):
        safe.get_pile_axial_reactions(source="table")
    state["frames"] = [f[:1] + ("C40x40",) + f[2:] for f in malla()]
    state["react"]["B00"] = [("COMB1", "", 300.0)]
    out = salida(safe.get_pile_axial_reactions(sections=["C40x40"]))
    assert out["n_pilotes"] == 9 and out["secciones"] == ["P45"]


@pytest.mark.parametrize("path", ["Results.JointReact", "RespCombo.GetNameList"])
def test_reactions_ret_no_cero_es_safeerror(pile_api, path):
    safe, model, state = pile_api
    fn = model
    for part in path.split("."):
        fn = getattr(fn, part)
    old, value = fn.side_effect, fn.return_value
    fn.side_effect = lambda *a: (*(old(*a) if callable(old) else value)[:-1], 5)
    with pytest.raises(SafeError):
        safe.get_pile_axial_reactions()


def test_reactions_avisa_duplicados_y_servicio_pero_lee_todos(pile_api):
    safe, model, state = pile_api
    state["frames"] = malla() + [("DUP", "P45", "TD", "BD", PASO, PASO, 0.0, PASO, PASO, -12.0)]
    for f in state["frames"]:
        state["react"][f[3]] = [("COMB1", "", 300.0)]
    out = salida(safe.get_pile_axial_reactions(q_adm=800.0))
    assert out["n_pilotes"] == 10 and out["envolvente"]["n_pilotes_con_resultado"] == 10
    assert any("DUP duplica" in a and "incluido en la lectura" in a for a in out["avisos"])
    assert any("carga de servicio" in a for a in out["avisos"])
    out = salida(safe.get_pile_axial_reactions(q_adm=800.0, combos=[], cases=["Dead"]))
    assert not any("carga de servicio" in a for a in out["avisos"])


def test_export_pile_check_xlsx_escribe_y_resume(pile_api, tmp_path):
    safe, model, state = pile_api
    for f in state["frames"]:
        state["react"][f[3]] = [("COMB1", "", 300.0), ("ENV", "Max", 330.0), ("ENV", "Min", 20.0)]
    path = str(tmp_path / "verificacion.xlsx")
    out = salida(safe.export_pile_check_xlsx(path, q_adm=800.0))
    assert out["archivo"] == path and out["bytes"] > 0 and out["hojas"][0] == "Resumen"
    assert out["resumen"]["geometria_conforme"] and sorted(out["resumen"]["servicio"]) == ["COMB1", "ENV"]
    assert out["resumen"]["n_cabezales"] == 1 and out["resumen"]["critico"]["p_serv"] == 330.0
    assert out["combos_leidas"] == ["COMB1", "ENV"] and out["unidades"]["preset"] == "kN, m, C"
    model.File.Save.assert_not_called()
    model.RespCombo.GetCaseList.assert_any_call("ENV")
    model.LoadCases.GetTypeOAPI_1.assert_any_call("Dead")  # QX es combo en ENV: no se consulta como caso
    assert out["resumen"]["servicio"] == ["ENV", "COMB1"]  # ENV = 1.165 D + L + 0.714 QX: servicio sismico
    import os
    from unittest.mock import patch

    def existe(p):  # conftest deja os.path.exists en False; os.stat no esta parcheado.
        try:
            os.stat(p)
            return True
        except OSError:
            return False
    with patch("Safe.os.path.exists", existe), pytest.raises(SafeError, match="overwrite"):
        safe.export_pile_check_xlsx(path, q_adm=800.0)
    out2 = salida(safe.export_pile_check_xlsx(path, q_ult=1800.0, fs=2.25, overwrite=True))
    assert out2["resumen"]["q_adm"] == 800.0
    with pytest.raises(SafeError, match="no ambos"):
        safe.export_pile_check_xlsx(str(tmp_path / "x.xlsx"), q_adm=1.0, fs=2.0)
    with pytest.raises(SafeError, match="xlsx"):
        safe.export_pile_check_xlsx(str(tmp_path / "x.csv"), q_adm=1.0)
    model.Analyze.GetCaseStatus.return_value = (2, ["Dead", "Live"], [1, 1], 0)
    with pytest.raises(SafeError, match="run_analysis"):
        safe.export_pile_check_xlsx(str(tmp_path / "y.xlsx"), q_adm=800.0)


def _mock_edicion(model, state):
    """Delete/AddByCoord sobre state['frames'] y apoyos de punta leibles."""
    def delete(name, item=0):
        state["frames"] = [f for f in state["frames"] if f[0] != name]
        return 0
    model.FrameObj.Delete.side_effect = delete
    def add(x1, y1, z1, x2, y2, z2, name="", prop="Default", user="", csys="Global"):
        n = f"N{len(state['frames'])}"
        state["frames"].append((n, prop, f"T{n}", f"B{n}", x1, y1, z1, x2, y2, z2))
        return (n, 0)
    model.FrameObj.AddByCoord.side_effect = add
    model.PointObj.GetRestraint.return_value = ([False, False, True, False, False, False], 0)
    model.PointObj.GetSpring.return_value = ((), 1)          # ret=1: sin resorte (visto en vivo)
    model.PointObj.GetSpringAssignment.return_value = ("", 1)
    model.FrameObj.GetSpringAssignment.return_value = ("SOILP", 0)
    for ns, m in (("PointObj", "SetRestraint"), ("PointObj", "SetSpring"), ("PointObj", "SetSpringAssignment"),
                  ("FrameObj", "SetSpringAssignment")):
        getattr(getattr(model, ns), m).return_value = 0


def test_suggest_pile_changes_devuelve_propuesta(pile_api):
    safe, model, state = pile_api
    for f in state["frames"]:
        state["react"][f[3]] = [("COMB1", "", 300.0), ("ENV", "Max", 330.0), ("ENV", "Min", 20.0)]
    out = salida(safe.suggest_pile_changes(q_adm=800.0))
    assert out["solo_lectura"] and out["propuesta"]["filas"][0]["cabezal"] == "A1"
    assert out["propuesta"]["filas"][0]["accion"] == "quitar" and out["propuesta"]["totales"]["quitar"] == 1
    model.File.Save.assert_not_called()
    with pytest.raises(SafeError, match="q_adm"):
        safe.suggest_pile_changes()


def test_trial_pile_changes_copia_borra_anade_reanaliza_y_compara(pile_api, tmp_path):
    safe, model, state = pile_api
    _mock_edicion(model, state)
    for f in state["frames"]:
        state["react"][f[3]] = [("COMB1", "", 300.0), ("ENV", "Max", 330.0), ("ENV", "Min", 20.0)]
    copia = str(tmp_path / "ensayo.fdb")
    xlsx = str(tmp_path / "despues.xlsx")
    out = salida(safe.trial_pile_changes(copia, q_adm=800.0, delete_frames=["F00", "F22"],
                                         add_piles=[{"x": 1.0, "y": 1.0, "ref": "F11"}], xlsx_path=xlsx))
    import shutil
    shutil.copy2.assert_called_once_with("modelo.fdb", copia)
    model.File.OpenFile.assert_called_once_with(copia)
    assert model.FrameObj.Delete.call_args_list == [(("F00", 0),), (("F22", 0),)]
    model.FrameObj.AddByCoord.assert_called_once_with(1.0, 1.0, 0.0, 1.0, 1.0, -12.0, "", "P45")
    model.PointObj.SetRestraint.assert_called_once()
    model.PointObj.SetSpring.assert_not_called()
    model.FrameObj.SetSpringAssignment.assert_called_once_with("N7", "SOILP", 0)
    model.Analyze.RunAnalysis.assert_called_once()
    model.File.Save.assert_not_called()
    assert out["original"] == "modelo.fdb" and out["original_intacto"] and out["copia"] == copia
    assert out["cambios"]["borrados"] == ["F00", "F22"] and out["cambios"]["anadidos"][0]["frame"] == "N7"
    assert out["cambios"]["anadidos"][0]["apoyos_copiados"] == ["restraint", "line_spring_prop:SOILP"]
    assert out["comparacion"]["global"]["n_pilotes"] == [9, 8] and out["hojas"][0] == "Resumen"
    assert any("sin reaccion" in a for a in out["avisos"])  # la punta nueva no tiene resultados en el mock
    # Guardas: sin cambios, copia igual al original, modelo activo distinto de la copia.
    with pytest.raises(SafeError, match="delete_frames"):
        safe.trial_pile_changes(str(tmp_path / "x.fdb"), q_adm=800.0)
    with pytest.raises(SafeError, match="original"):
        safe.trial_pile_changes(copia, q_adm=800.0, delete_frames=["N7"])
    state["effects"] = False  # OpenFile deja de cambiar el nombre del modelo activo
    with pytest.raises(SafeError, match="no la copia"):
        safe.trial_pile_changes(str(tmp_path / "y.fdb"), q_adm=800.0, delete_frames=["F01"])
    model.FrameObj.Delete.assert_called_with("F22", 0)  # no se borro nada mas


def test_export_con_seismic_combos_lee_la_envolvente_y_compara_con_el_factor(pile_api, tmp_path):
    safe, model, state = pile_api
    state["combos"]["E"] = ([1, 1], ["ENV", "COMB1"], [1.0, 1.0])     # envolvente de combos: no se leeria sola
    model.RespCombo.GetNameList.return_value = (3, ["COMB1", "ENV", "E"], 0)
    for f in state["frames"]:
        state["react"][f[3]] = [("COMB1", "", 300.0), ("ENV", "Max", 330.0), ("ENV", "Min", 20.0),
                                ("E", "Max", 900.0), ("E", "Min", -50.0)]
    path = str(tmp_path / "s.xlsx")
    out = salida(safe.export_pile_check_xlsx(path, q_adm=800.0, service_combos=["COMB1"], seismic_combos=["E"]))
    assert "E" in out["combos_leidas"] and out["resumen"]["servicio"] == ["COMB1"] and out["resumen"]["sismo"] == ["E"]
    assert out["resumen"]["factor_sismo"] == pytest.approx(4 / 3)
    # 900 < 720*4/3 = 960: cumple; con factor 1.0 no cumpliria
    assert out["resumen"]["n_no_cumplen"] == 0
    out2 = salida(safe.export_pile_check_xlsx(path, q_adm=800.0, service_combos=["COMB1"], seismic_combos=["E"],
                                              seismic_factor=1.0, overwrite=True))
    assert out2["resumen"]["n_no_cumplen"] == 9 and out2["resumen"]["n_no_cumplen_sismo"] == 9
    with pytest.raises(SafeError, match="seismic_combos inexistentes"):
        safe.export_pile_check_xlsx(str(tmp_path / "x.xlsx"), q_adm=800.0, seismic_combos=["NOPE"])
    model.File.Save.assert_not_called()
