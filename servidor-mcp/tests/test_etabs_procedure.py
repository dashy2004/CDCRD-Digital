import copy
import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from etabs_procedure import (PROFILE_ID, calculate_loads, ceil_step, get_procedure,
                             grouped_masonry_totals, load_to_tfm2, prepare_modeling,
                             verify_spectrum)
from modeling_checks import audit_modeling
from beam_procedure import (bar_area, proposal, read_design_summary_csv,
                            review_longitudinal, review_torsion_faces, span_minimum)
from procedure_tools import PROCEDURE_TOOLS, register_procedure_tools


@pytest.fixture
def project():
    return {"model_path": r"C:\Models\Synthetic.edb", "usage": "residential",
            "has_parking": False, "stories": [
                {"name": "E1", "architectural_height_m": 3.0},
                {"name": "E2", "architectural_height_m": 3.5}]}


def seismic():
    return {"ss_g": .8, "s1_g": .35, "fa": 1.1, "fv": 1.4, "u": 1., "rd": 4.5,
            "near_fault": False, "source": "synthetic checked workbook",
            "reentrant": "no", "nonorthogonal": "no", "torsion": "no",
            "scale_mps2": 1., "required_periods_s": [0., .2, 1.],
            "samples": [{"period_s": t, "excel_sa_mps2": sa, "function_ordinate": sa}
                        for t, sa in [(0., .4), (.2, 1.), (1., .5)]]}


def test_profile_requires_explicit_name_and_is_not_shared_mutable():
    with pytest.raises(ValueError):
        get_procedure("../profiles/other")
    one = get_procedure(PROFILE_ID)
    one["mass_source"]["factors"]["Live"] = 99
    assert get_procedure(PROFILE_ID)["mass_source"]["factors"]["Live"] == .15
    assert [s["id"] for s in one["steps"]] == list(range(1, 23))
    assert one["steps"][18]["tools"] == []
    assert one["analysis_authorized"] is False


def test_preparation_keeps_source_heights_and_has_no_implicit_livep(project):
    before = copy.deepcopy(project)
    plan = prepare_modeling(PROFILE_ID, project)
    assert [s["model_height_m"] for s in plan["stories"]] == [3.5, 3.5]
    assert [s["elevation_m"] for s in plan["stories"]] == [3.5, 7.]
    assert plan["modal_max_modes"] == 6
    assert plan["mass_source"]["factors"] == {"Dead": 1, "Live": .15, "LiveT": .1}
    assert plan["pdelta"]["factors"] == {"Dead": 1.2, "Live": 1.6, "LiveT": 1.6}
    assert all(p["name"] != "LiveP" for p in plan["patterns"])
    assert next(p for p in plan["patterns"] if p["name"] == "LiveT")["type"] == "Live"
    assert plan["spectrum"] is None and not plan["analysis_authorized"]
    assert project == before


def test_parking_changes_mass_and_pdelta_separately(project):
    project["has_parking"] = True
    plan = prepare_modeling(PROFILE_ID, project)
    assert plan["mass_source"]["factors"]["LiveP"] == .25
    assert plan["pdelta"]["factors"]["LiveP"] == 1.6
    assert plan["mass_source"]["source_self"] is False
    assert plan["mass_source"]["vertical"] is False


@pytest.mark.parametrize("field,value", [
    ("has_parking", None), ("has_parking", "false"), ("usage", "office"),
    ("model_path", "relative.edb"), ("model_path", r"C:\Models\test.$et"),
    ("stories", []), ("stories", [{"name": "Base", "architectural_height_m": 3}]),
    ("stories", [{"name": "E1", "architectural_height_m": float("nan")}]),
])
def test_invalid_project_rejected(project, field, value):
    project[field] = value
    with pytest.raises(ValueError):
        prepare_modeling(PROFILE_ID, project)


def test_two_directions_no_double_gravity_and_source_distinction(project):
    project["seismic"] = seismic()
    plan = prepare_modeling(PROFILE_ID, project)
    spectrum = plan["spectrum"]
    assert spectrum["function_parameters"]["ss"] == pytest.approx(.8 * 9.81)
    assert plan["patterns"][-1]["parameters"]["ss_g"] == .8
    ex, ey = spectrum["cases"]
    assert [r["direction"] for r in ex["loads"]] == ["U1", "U2"]
    assert [r["direction"] for r in ey["loads"]] == ["U2", "U1"]
    assert [r["scale_mps2"] for r in ex["loads"]] == [1, .3]
    assert ex["eccentricity"] == 0 and plan["patterns"][-1]["eccentricity"] == .05
    assert ex["modal_combination"] == "CQC" and ex["directional_combination"] == "SRSS"


def test_bad_or_absent_curve_does_not_generate_cases(project):
    project["seismic"] = seismic()
    project["seismic"]["scale_mps2"] = 9.81
    result = prepare_modeling(PROFILE_ID, project)
    assert result["spectrum"]["cases"] == []
    assert not result["spectrum"]["curve_verification"]["matches"]
    del project["seismic"]["scale_mps2"]
    assert prepare_modeling(PROFILE_ID, project)["spectrum"]["cases"] == []


def test_pending_penalty_remains_pending(project):
    project["seismic"] = seismic()
    project["seismic"]["torsion"] = "pending"
    assert any("torsion: decision pendiente" in s
               for s in prepare_modeling(PROFILE_ID, project)["pending"])


def test_spectrum_requires_breakpoints_and_distinct_periods():
    s = seismic()
    with pytest.raises(ValueError, match="Faltan periodos"):
        verify_spectrum(s["samples"], 1, [0, .3, 1])
    with pytest.raises(ValueError, match="crecientes"):
        verify_spectrum(s["samples"][::-1], 1, s["required_periods_s"])


@pytest.mark.parametrize("original,expected", [
    (1.56, 1.60), (1.51, 1.55), (1.55, 1.55), (.121, .15),
    (.156, .20), (.631, .65), (.20, .20), (.1 + .2, .30),
])
def test_round_only_at_assignment(original, expected):
    assert ceil_step(original) == pytest.approx(expected)


@pytest.mark.parametrize("value", [None, True, "0.1", float("nan"), float("inf"), -1])
def test_invalid_number_never_becomes_zero(value):
    with pytest.raises(ValueError):
        ceil_step(value)


def test_load_unit_conversion():
    assert load_to_tfm2(200, "kgf/m2") == .2
    assert load_to_tfm2(9.80665, "kN/m2") == 1.
    assert load_to_tfm2(.00980665, "N/mm2") == pytest.approx(1.)
    with pytest.raises(ValueError):
        load_to_tfm2(200, "kg/m2")  # ambiguous mass is not force


def slab(**changes):
    row = {"id": "A1", "support": "supported", "set": "Entrepisos", "is_opening": False,
           "architecture_set": "Entrepisos", "excel_live": .2,
           "excel_masonry": .121, "unit": "tonf/m2", "existing_components": []}
    return {**row, **changes}


def test_slab_components_and_cantilever_exception():
    rows = [slab(), slab(id="A2", support="cantilever"), slab(id="A3", excel_masonry=0)]
    result = calculate_loads(PROFILE_ID, {"has_parking": False, "slabs": rows})
    assert [r["masonry_assigned_tfm2"] for r in result["slabs"]] == [.15, 0, .1]
    assert result["slabs"][0]["dead_tfm2"] == .16
    assert result["slabs"][0]["live_tfm2"] == .2
    assert result["slabs"][0]["masonry_calculated_tfm2"] == .121


@pytest.mark.parametrize("change", [
    {"architecture_set": "Techo"}, {"excel_live": .1},
    {"existing_components": ["finishes"]}, {"excel_masonry": None},
    {"is_opening": True}, {"is_opening": None},
    {"set": "Parqueos", "architecture_set": "Parqueos"},
])
def test_load_conflicts_block_calculation(change):
    with pytest.raises(ValueError):
        calculate_loads(PROFILE_ID, {"has_parking": False, "slabs": [slab(**change)]})


def test_parking_value_is_explicit_not_historical_default():
    row = slab(set="Parqueos", architecture_set="Parqueos", excel_live=.4)
    with pytest.raises(ValueError, match="confirmed_live"):
        calculate_loads(PROFILE_ID, {"has_parking": True, "slabs": [row]})
    row["confirmed_live_tfm2"] = .4
    assert calculate_loads(PROFILE_ID, {"has_parking": True, "slabs": [row]})["slabs"][0]["live_tfm2"] == .4


def wall(**changes):
    return {**{"id": "W1", "beam": "B1", "start": .1, "end": .4,
               "beam_depth_m": .7, "thickness_m": .15,
               "space_above_start_m": 3, "space_above_end_m": 3.5, "reverse_ij": False},
            **changes}


def test_variable_wall_intensity_and_ij_reversal():
    result = calculate_loads(PROFILE_ID, {"has_parking": False,
                                        "walls_on_beams": [wall(reverse_ij=True)]})["walls_on_beams"][0]
    assert result["start"] == pytest.approx(.6)
    assert result["end"] == pytest.approx(.9)
    assert result["calculated_tfm"] == pytest.approx([.756, .621])
    assert result["assigned_tfm"] == [.8, .65]


def test_wall_overlap_is_rejected():
    with pytest.raises(ValueError, match="solapados"):
        calculate_loads(PROFILE_ID, {"has_parking": False,
                                    "walls_on_beams": [wall(), wall(id="W2", start=.3, end=.5)]})


def test_overlap_is_checked_after_ij_normalization():
    with pytest.raises(ValueError, match="solapados"):
        calculate_loads(PROFILE_ID, {"has_parking": False, "walls_on_beams": [
            wall(reverse_ij=True), wall(id="W2", start=.6, end=.8)]})


def test_water_conserves_total_without_masonry_rounding():
    water = {"id": "P1", "wet_horizontal_area_m2": 10, "mean_depth_m": 1.231,
             "application_horizontal_area_m2": 20, "equivalent_over_dry_area": True,
             "existing_water_assigned": False}
    result = calculate_loads(PROFILE_ID, {"has_parking": False, "water": [water]})["water"][0]
    assert result["weight_tf"] == pytest.approx(12.31)
    assert result["load_tfm2"] * 20 == pytest.approx(result["weight_tf"])
    water["equivalent_over_dry_area"] = False
    with pytest.raises(ValueError):
        calculate_loads(PROFILE_ID, {"has_parking": False, "water": [water]})


def test_grouped_masonry_maximum_preserves_precision_and_governing_floor():
    result = grouped_masonry_totals({"E1": {"A1/15": 2.321, "A1/10": 1.5},
                                    "E2": {"A1/15": 3.123, "A1/10": 1.2}})
    assert result["A1/15"] == {"length_m": 3.123, "governing_stories": ["E2"]}
    with pytest.raises(ValueError):
        grouped_masonry_totals({"E1": {"A": 1}, "E2": {"A": None}})


def panel(id="A1", story="E1", z=3.5, **changes):
    return {**{"id": id, "story": story, "vertices_m": [[0, 0, z], [5, 0, z], [5, 4, z], [0, 4, z]],
               "structural_block": "main", "diaphragm": "D1", "directions": 1,
               "mesh": "No Auto Mesh", "is_opening": False, "support": "supported",
               "load_components": ["set", "masonry"]}, **changes}


def snapshot(project):
    project["seismic"] = seismic()
    plan = prepare_modeling(PROFILE_ID, project)
    return {**{k: plan[k] for k in ("model_path", "units", "mass_source", "pdelta",
                                   "modal_max_modes", "patterns")},
            "spectrum_cases": plan["spectrum"]["cases"],
            "slab_definitions": [{"name": "S", "type": "Slab", "modeling_type": "Shell-Thick"}],
            "slabs": [panel()], "walls": [], "frames": [],
            "joints": [{"id": "P1", "at_base": True, "restraints": [True] * 6}],
            "check_model": {"completed": True, "warnings": []}, "saved_readback_verified": True}


def codes(project, state):
    return {r["code"] for r in audit_modeling(PROFILE_ID, project, state)["findings"]}


def test_diaphragm_reuse_between_stories_is_valid(project):
    state = snapshot(project)
    state["slabs"].append(panel("A2", "E2", 7))
    assert audit_modeling(PROFILE_ID, project, state)["checked_snapshot_matches"]
    state["slabs"][1]["story"] = "E1"
    assert "mixed_elevations" in codes(project, state)


def test_independent_blocks_cannot_share_diaphragm(project):
    state = snapshot(project)
    state["slabs"].append(panel("A2", structural_block="independent"))
    assert "mixed_blocks" in codes(project, state)
    assert "duplicate_shell" in codes(project, state)


def test_inclined_and_nonplanar_panels(project):
    state = snapshot(project)
    state["slabs"][0]["vertices_m"][1][2] = 4.
    assert {"nonplanar", "inclined_diaphragm"} <= codes(project, state)


def test_unused_membrane_and_one_way_solid_mesh_are_checked(project):
    state = snapshot(project)
    state["slab_definitions"].append({"name": "unused", "type": "Slab", "modeling_type": "Membrane"})
    state["slabs"][0]["mesh"] = "Default"
    assert sum(f["code"] == "setting" for f in audit_modeling(PROFILE_ID, project, state)["findings"]) == 2


def test_unknown_check_model_and_persistence_cannot_pass(project):
    state = snapshot(project)
    state.pop("check_model")
    state["saved_readback_verified"] = False
    assert {"check_model", "persistence"} <= codes(project, state)


def test_integer_is_not_accepted_as_verified_boolean(project):
    state = snapshot(project)
    state["mass_source"]["lateral"] = 1
    state["joints"][0]["restraints"] = [1] * 6
    assert "setting" in codes(project, state)


def test_joint_diaphragm_at_wrong_elevation(project):
    state = snapshot(project)
    state["joints"].append({"id": "P2", "at_base": False, "story": "E1",
                            "z_m": 4., "diaphragm": "D1"})
    assert "joint_diaphragm" in codes(project, state)


@pytest.mark.parametrize("span", [6, 8.5, 10, 11, 12.01])
def test_undefined_span_boundaries_do_not_choose_a_rule(span):
    with pytest.raises(ValueError):
        span_minimum(span)


def test_confirmed_750_boundary_and_adopted_total_bar_areas():
    assert span_minimum(7.5)["bottom_cm2"] == 11.4
    assert bar_area("1", 2) == 10.13
    assert bar_area("1", 6) == 30.4
    assert proposal(0, "top", additional=True) == []
    assert proposal(11.4, "bottom", additional=True)[0]["diameter_in"] == "3/4"
    assert proposal(11.41, "bottom", additional=True)[0]["diameter_in"] == "1"
    assert proposal(14.25, "top", additional=True)[0]["count"] == 5


def beam():
    return {"id": "B1", "axis": "X", "story": "E1", "clear_span_m": 5.,
            "support_mapping_verified": True, "single_span_object_verified": True,
            "design_errors": [], "demands": {
                "top": {"i": 9, "center": 8, "j": 9},
                "bottom": {"i": 6.4, "center": 6.4, "j": 6.4}},
            "bars": [
                {"id": "T1", "face": "top", "role": "continuous", "count": 2, "diameter_in": "3/4",
                 "zones": ["i", "center", "j"], "drawing_verified": True},
                {"id": "T2", "face": "top", "role": "additional", "count": 1, "diameter_in": "1",
                 "zones": ["i", "center", "j"], "drawing_verified": True},
                {"id": "B1", "face": "bottom", "role": "continuous", "count": 3, "diameter_in": "3/4",
                 "zones": ["i", "center", "j"], "drawing_verified": True}]}


def review(b):
    return review_longitudinal(PROFILE_ID, {"model_source": "synthetic", "demand_kind": "total_longitudinal",
                                           "area_unit": "cm2", "beams": [b]})


def test_continuous_additional_counts_at_center_once_but_not_for_base():
    result = review(beam())["beams"][0]
    center = next(c for c in result["checks"] if c["face"] == "top" and c["zone"] == "center")
    assert center["provided_cm2"] == pytest.approx(5.7 + 5.07)
    assert center["covers_area"]
    assert result["base_from_continuous_bar_count_m"] == .25
    assert not result["structural_approval"]


def test_duplicate_physical_bar_is_not_counted_twice():
    b = beam()
    b["bars"].append(copy.deepcopy(b["bars"][1]))
    with pytest.raises(ValueError, match="duplicado"):
        review(b)


def test_design_errors_survive_area_coverage_and_fixed_section_no_reduction():
    b = beam()
    b["design_errors"] = ["combined shear and torsion"]
    b["fixed_section"] = True
    result = review(b)["beams"][0]
    assert result["status"] == "conditional" and result["warnings"]
    assert all(c["continuous_area_options"] == [] for c in result["checks"])


def test_continuous_proposal_uses_maximum_of_entire_axis():
    a, b = beam(), beam()
    b["id"] = "B2"
    b["demands"]["bottom"]["center"] = 15
    data = {"model_source": "synthetic", "demand_kind": "total_longitudinal",
            "area_unit": "cm2", "beams": [a, b]}
    first = review_longitudinal(PROFILE_ID, data)["beams"][0]
    bottom = next(c for c in first["checks"] if c["face"] == "bottom" and c["zone"] == "center")
    assert bottom["axis_continuous_target_cm2"] == 15
    assert bottom["continuous_area_options"][0]["diameter_in"] == "1"
    assert bottom["diameter_rule_issues"] == ["B1"]


def torsion_data():
    return {"model_source": "synthetic", "demand_kind": "flexure_only",
            "torsion_kind": "longitudinal_area_per_face", "area_unit": "cm2",
            "faces": [{"id": "T", "beam": "B1", "story": "E1", "zone": "i", "face": "top",
                       "flexure_demand": 8., "flexure_provided": 10.,
                       "torsion_demand": 3.755, "torsion_provided": 2.54,
                       "design_errors": [], "disjoint_bar_allocation_verified": True}]}


def test_torsion_coverage_same_face_and_unrounded_shortfall():
    data = torsion_data()
    bottom = {**data["faces"][0], "id": "B", "face": "bottom", "flexure_provided": 8}
    data["faces"].append(bottom)
    result = review_torsion_faces(PROFILE_ID, data)["faces"]
    assert result[0]["status"] == "CUBRE POR AREA"
    assert result[0]["torsion_shortfall_cm2"] == pytest.approx(1.215)
    assert result[1]["status"] == "NO CUBRE"


@pytest.mark.parametrize("field,value", [("demand_kind", "total_longitudinal"),
                                       ("torsion_kind", "At/s"), ("torsion_kind", "Al_total")])
def test_reject_double_torsion_and_wrong_quantity(field, value):
    data = torsion_data()
    data[field] = value
    with pytest.raises(ValueError):
        review_torsion_faces(PROFILE_ID, data)


def test_missing_torsion_input_is_not_zero_and_errors_exclude_explanation():
    data = torsion_data()
    data["faces"][0]["design_errors"] = ["design failure"]
    assert not review_torsion_faces(PROFILE_ID, data)["faces"][0]["eligible_for_area_explanation"]
    data["faces"][0]["torsion_demand"] = None
    assert review_torsion_faces(PROFILE_ID, data)["faces"][0]["status"] == "FALTAN DATOS"


def test_csv_envelope_units_faces_and_center_and_error_retention(tmp_path):
    path = tmp_path / "summary.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Story", "UniqueName", "DesignSect", "Station", "AsTopTotal", "AsBotTotal", "WarnMsg", "ErrMsg"])
        for s, top, bot in [(250, 1000, 600), (1500, 700, 700), (2500, 800, 900),
                            (3500, 750, 650), (4750, 1200, 600)]:
            w.writerow(["E1", "10", "B", s, top, bot, "No Message", "torsion error"])
    result = read_design_summary_csv(str(path), "mm2", "mm", "synthetic.edb", "2026-01-01", True)
    b = result["beams"][0]
    assert b["clear_span_m"] == 4.5
    assert b["demands"]["top"] == {"i": 10, "center": 8, "j": 12}
    assert b["demands"]["bottom"]["center"] == 9
    assert b["design_errors"] == ["torsion error"] and not result["live_read"]
    with pytest.raises(ValueError):
        read_design_summary_csv(str(path), "mm2", "mm", "x", "date", False)


def test_all_tools_register_without_importing_com():
    registered = []
    class Registry:
        def tool(self):
            return lambda fn: registered.append(fn.__name__)
    register_procedure_tools(Registry())
    assert set(registered) == {fn.__name__ for fn in PROCEDURE_TOOLS}
    assert len(registered) == 8


def test_cli_real_execution_preserves_existing_receipt(tmp_path, project):
    payload = tmp_path / "input.json"
    output = tmp_path / "receipt.json"
    payload.write_text(json.dumps({"profile": PROFILE_ID, "project": project}))
    cmd = [sys.executable, str(ROOT / "tools/etabs_procedure.py"), "prepare_etabs_modeling",
           str(payload), "--output", str(output)]
    first = subprocess.run(cmd, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    before = output.read_bytes()
    assert json.loads(before)["result"]["model_modified"] is False
    second = subprocess.run(cmd, capture_output=True)
    assert second.returncode == 1 and output.read_bytes() == before


def test_real_mcp_sdk_schema_and_example_calls():
    import asyncio
    sdk = pytest.importorskip("mcp.server.fastmcp")

    async def check():
        server = sdk.FastMCP("offline-procedure-test")
        register_procedure_tools(server)
        tools = await server.list_tools()
        assert len(tools) == 8
        plan_tool = next(t for t in tools if t.name == "prepare_etabs_modeling")
        assert "profile" in plan_tool.inputSchema["required"]
        examples = {
            "model": "prepare_etabs_modeling", "loads": "calculate_etabs_project_loads",
            "beams": "review_etabs_longitudinal", "torsion": "review_etabs_flexure_torsion"}
        for example, name in examples.items():
            payload = json.loads((ROOT / "examples" / f"procedure-{example}.json").read_text())
            result = await server.call_tool(name, payload)
            parsed = json.loads(result[0].text)
            assert parsed["model_modified"] is False
        with pytest.raises(Exception, match="profile"):
            await server.call_tool("get_etabs_procedure", {})

    asyncio.run(check())
