"""El plan de ETABS respeta las reglas duras del prompt de Arlette."""
import json

from puente_losas.contrato import PanoLosa, asignar_bordes
from puente_losas.etabs_plan import ajustar_005, escribir_plan, plan_etabs
from puente_losas.motor import analizar_panos


def _resultados(usos=("entrepisos", "techo"), con_hueco=False):
    panos = []
    for i, uso in enumerate(usos):
        hueco = [[1.0 + i * 5, 1.0], [2.0 + i * 5, 1.0], [2.0 + i * 5, 2.0], [1.0 + i * 5, 2.0]]
        panos.append(PanoLosa(
            mark=f"LE{i + 1}", nivel="N1", z_tope=3.0, lx=5.0, ly=6.0, espesor=0.25,
            contorno=[[i * 5.0, 0.0], [i * 5.0 + 5.0, 0.0], [i * 5.0 + 5.0, 6.0], [i * 5.0, 6.0]],
            huecos=[hueco] if (con_hueco and i == 0) else [], uso=uso))
    return analizar_panos(asignar_bordes(panos))


def _pasos(plan, tool=None, method=None):
    for paso in plan["pasos"]:
        if tool and paso["tool"] != tool:
            continue
        if method and paso["args"].get("method") != method:
            continue
        yield paso


def test_unidades_primero_y_material_c210():
    plan = plan_etabs(_resultados())
    assert plan["pasos"][0] == {"tool": "set_units", "args": {"units": "Ton, m, C"},
                                "nota": plan["pasos"][0]["nota"]}
    (mat,) = _pasos(plan, tool="define_concrete_material")
    assert mat["args"]["name"] == "C210"
    assert mat["args"]["E"] == 2188197.76 and mat["args"]["unit_weight"] == 2.4028


def test_todas_las_losas_shell_thick():
    plan = plan_etabs(_resultados())
    slabs = list(_pasos(plan, tool="call_oapi", method="SetSlab"))
    assert slabs, "el plan debe definir secciones de losa"
    for s in slabs:
        args = s["args"].get("args_nombrados", {})
        if args:                                   # definición de biblioteca
            assert args["ShellType"] == "ShellThick"
        assert "describe_oapi" in s.get("verificar", "")


def test_coordenadas_en_multiplos_de_005():
    assert ajustar_005(5.37) == 5.35
    assert ajustar_005(5.38) == 5.40
    plan = plan_etabs(_resultados())
    for paso in _pasos(plan, tool="create_objects_by_coordinates"):
        for obj in paso["args"]["objects"]:
            for v in obj["xs"] + obj["ys"] + obj["zs"]:
                assert abs(v / 0.05 - round(v / 0.05)) < 1e-9


def test_patrones_livet_solo_si_hay_techo_livep_solo_con_parqueos():
    nombres = [p["args"].get("name") for p in plan_etabs(_resultados())["pasos"]
               if p["tool"] == "add_load_pattern"]
    assert nombres == ["Dead", "Live", "LiveT"]
    nombres2 = [p["args"].get("name") for p in plan_etabs(_resultados(("entrepisos", "parqueos")))["pasos"]
                if p["tool"] == "add_load_pattern"]
    assert "LiveP" in nombres2 and "LiveT" not in nombres2


def test_cargas_por_pano_y_patron_dead_sin_duplicar_pp():
    plan = plan_etabs(_resultados())
    cargas = list(_pasos(plan, tool="call_oapi", method="SetLoadUniform"))
    assert len(cargas) == 4                         # Dead + viva por cada paño
    dead = [c for c in cargas if c["args"]["args_nombrados"]["LoadPat"] == "Dead"]
    # Dead superficial = acabados + mampostería; el peso propio va en el patrón.
    assert dead[0]["args"]["args_nombrados"]["Value"] == 0.16 + 0.10
    assert "peso propio" in dead[0]["nota"]


def test_huecos_se_vuelven_aberturas():
    plan = plan_etabs(_resultados(con_hueco=True))
    aberturas = list(_pasos(plan, tool="call_oapi", method="SetOpening"))
    assert len(aberturas) == 1
    assert aberturas[0]["args"]["args_nombrados"]["IsOpening"] is True


def test_requisitos_incluyen_lock_y_no_run(tmp_path):
    ruta = tmp_path / "plan.json"
    plan = escribir_plan(_resultados(), str(ruta))
    texto = " ".join(plan["meta"]["requisitos"])
    assert "lock" in texto and "NO correr el análisis" in texto
    assert json.loads(ruta.read_text(encoding="utf-8"))["meta"]["unidades"] == "Ton, m, C"
