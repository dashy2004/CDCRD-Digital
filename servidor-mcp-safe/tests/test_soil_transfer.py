"""Soil writes are bounded, independently dimensioned and checked after effects."""
import copy
from unittest.mock import MagicMock

import pytest

from soil_transfer import apply_plan, capture_context, digest, validate_plan


@pytest.fixture
def fixture():
    model = MagicMock()
    state = {"units": 9, "assignments": {"A1": "None", "A2": "None"}, "props": {}, "k": None,
             "nonlinear": "Compression Only", "locked": False}
    model.GetModelFilename.return_value = r"C:\test\SYNTHETIC_SOIL.FDB"
    model.GetPresentUnits.side_effect = lambda: state["units"]
    model.GetModelIsLocked.side_effect = lambda: state["locked"]
    model.PointObj.Count.return_value = 4
    model.PointObj.GetAllPoints.return_value = (4, ["P1","P2","P3","P4"], [0,2000,2000,0], [0,0,2000,2000], [0,0,0,0], 0)
    model.AreaObj.GetNameList.return_value = (2, ["A1","A2"], 0)
    model.AreaObj.GetPoints.return_value = (4, ["P1","P2","P3","P4"], 0)
    model.AreaObj.GetProperty.return_value = ("MAT", 0)
    model.AreaObj.GetOpening.return_value = (False, 0)
    model.AreaObj.GetTransformationMatrix.return_value = ([1,0,0,0,1,0,0,0,1], 0)
    model.AreaObj.GetSpringAssignment.side_effect = lambda aid: (state["assignments"][aid], 0)
    model.PropAreaSpring.GetNameList.side_effect = lambda: (len(state["props"]), list(state["props"]), 0)
    key = "Area Assignments - Area Springs"
    model.DatabaseTables.GetAllTables.side_effect = lambda: (1,[key],[key],[2],
        [all(v == "None" for v in state["assignments"].values())],0)
    def assignments(*args):
        rows = [(aid, name) for aid,name in state["assignments"].items() if name != "None"]
        return ([],1,["UniqueName","SpringProp"],len(rows),[v for row in rows for v in row],0)
    model.DatabaseTables.GetTableForDisplayArray.side_effect = assignments
    def prop(name, u1, u2, k, nonlin):
        state["props"][name] = k
        state["k"] = k
        return 0
    def assign(aid, name, item):
        state["assignments"][aid] = name
        return 0
    model.PropAreaSpring.SetAreaSpringProp.side_effect = prop
    model.AreaObj.SetSpringAssignment.side_effect = assign
    def table(key):
        return (1, ["Name","StiffU1","StiffU2","StiffU3","NonlinOpt3"],
                [[name,"0","0",str(k),state["nonlinear"]] for name,k in state["props"].items()])
    context = capture_context(model, model.GetModelFilename(), "TEST")
    plan = {"schema":"cdcrd.safe-soil-plan/1", "target": {key:context["geometry"][key] for key in ("model","units_enum","frame")},
            "geometry_sha256":context["geometry_sha256"], "soil_state_before":copy.deepcopy(context["soil_state"]),
            "property_name":"CDX_SOIL", "compression_only":True, "area_ids":["A1"],
            "geotechnical":{"source":"Synthetic independent data", "allowable_bearing_kpa":150.,
                            "subgrade_modulus_kn_m3":18000., "applicable_point_ids":["P1","P2","P3","P4"]},
            "terrain_rows":[{"id":p,"status":"ok","terrain_z_m":10.,"site_xyz_m":[0.,0.,9.]} for p in ("P1","P2","P3","P4")]}
    seal(plan)
    return model, state, plan, table


def seal(plan):
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = digest(plan)


def test_apply_changes_only_selected_soil(fixture):
    model, state, plan, table = fixture
    result = apply_plan(model, table, plan, plan["plan_sha256"], True)
    assert result["ok"] and result["geometry_unchanged"] and result["k_native"] == pytest.approx(.018)
    assert state["assignments"] == {"A1":"CDX_SOIL", "A2":"None"}
    model.PropAreaSpring.SetAreaSpringProp.assert_called_once_with("CDX_SOIL",0.,0.,.018,1)
    model.SetPresentUnits.assert_not_called()
    model.File.Save.assert_not_called()
    model.Analyze.RunAnalysis.assert_not_called()
    with pytest.raises(ValueError, match="cambiaron"):
        apply_plan(model, table, plan, plan["plan_sha256"], True)
    assert model.PropAreaSpring.SetAreaSpringProp.call_count == 1


@pytest.mark.parametrize("units,expected", [(6,18000.),(9,.018),(10,18000000.)])
def test_explicit_dimensional_conversion(fixture, units, expected):
    _, _, plan, _ = fixture
    plan["target"]["units_enum"] = units
    seal(plan)
    assert validate_plan(plan, plan["plan_sha256"]) == pytest.approx(expected)
    plan["geotechnical"]["allowable_bearing_kpa"] *= 2
    seal(plan)
    assert validate_plan(plan, plan["plan_sha256"]) == pytest.approx(expected)


@pytest.mark.parametrize("mutation", [
    lambda p:p.update(compression_only=1), lambda p:p.update(property_name="bad name"),
    lambda p:p.update(area_ids=[]), lambda p:p.update(area_ids=["A1","A1"]),
    lambda p:p["target"].update(units_enum=7),
    lambda p:p["geotechnical"].update(subgrade_modulus_kn_m3=0),
    lambda p:p["geotechnical"].update(allowable_bearing_kpa=-1),
    lambda p:p["geotechnical"].update(source=" "),
    lambda p:p["terrain_rows"][0].update(status="error"),
    lambda p:p["terrain_rows"].pop(),
    lambda p:p["geotechnical"].update(applicable_point_ids=["P1"]),
    lambda p:p.update(area_ids=["UNKNOWN"]),
])
def test_invalid_plan_rejected_before_setter(fixture, mutation):
    model, _, plan, table = fixture
    mutation(plan)
    seal(plan)
    with pytest.raises((ValueError, KeyError)):
        apply_plan(model, table, plan, plan["plan_sha256"], True)
    model.PropAreaSpring.SetAreaSpringProp.assert_not_called()
    model.AreaObj.SetSpringAssignment.assert_not_called()


def test_hash_and_confirmation_required(fixture):
    model, _, plan, table = fixture
    with pytest.raises(ValueError, match="copia"):
        apply_plan(model, table, plan, plan["plan_sha256"])
    plan["area_ids"] = ["A2"]
    with pytest.raises(ValueError, match="hash"):
        apply_plan(model, table, plan, plan["plan_sha256"], True)
    model.PropAreaSpring.SetAreaSpringProp.assert_not_called()


@pytest.mark.parametrize("units,k", [(10,1e308),(9,5e-324)])
def test_converted_overflow_or_underflow_rejected(fixture, units, k):
    _, _, plan, _ = fixture
    plan["target"]["units_enum"] = units
    plan["geotechnical"]["subgrade_modulus_kn_m3"] = k
    seal(plan)
    with pytest.raises(ValueError):
        validate_plan(plan, plan["plan_sha256"])


def test_non_synthetic_target_rejected_before_any_live_read(fixture):
    model, _, plan, table = fixture
    plan["target"]["model"] = r"C:\project\copy.fdb"
    seal(plan)
    model.reset_mock()
    with pytest.raises(ValueError, match="SYNTHETIC"):
        apply_plan(model, table, plan, plan["plan_sha256"], True)
    model.GetModelFilename.assert_not_called()
    model.PropAreaSpring.SetAreaSpringProp.assert_not_called()


def test_second_area_failure_retains_first_confirmed(fixture):
    model, state, plan, table = fixture
    plan["area_ids"] = ["A1", "A2"]
    seal(plan)
    def assign(aid, name, item):
        if aid == "A2":
            return 1
        state["assignments"][aid] = name
        return 0
    model.AreaObj.SetSpringAssignment.side_effect = assign
    result = apply_plan(model, table, plan, plan["plan_sha256"], True)
    assert not result["ok"] and result["partial_write_possible"]
    assert result["attempted"] == [{"property":"CDX_SOIL"},{"area":"A1"},{"area":"A2"}]
    assert result["confirmed"] == [{"property":"CDX_SOIL"},{"area":"A1"}]
    assert state["assignments"] == {"A1":"CDX_SOIL","A2":"None"}
    assert model.AreaObj.SetSpringAssignment.call_count == 2


@pytest.mark.parametrize("changed", ["units","path","geometry","lock","soil","opening","axis"])
def test_stale_live_context_rejected(fixture, changed):
    model, state, plan, table = fixture
    if changed == "units": state["units"] = 6
    if changed == "path": model.GetModelFilename.return_value = r"C:\original.fdb"
    if changed == "geometry": model.AreaObj.GetProperty.return_value = ("OTHER",0)
    if changed == "lock": state["locked"] = True
    if changed == "soil": state["assignments"]["A1"] = "OTHER"
    if changed == "opening": model.AreaObj.GetOpening.return_value = (True,0)
    if changed == "axis": model.AreaObj.GetTransformationMatrix.return_value = ([1,0,0,0,-1,0,0,0,-1],0)
    with pytest.raises(ValueError):
        apply_plan(model, table, plan, plan["plan_sha256"], True)
    model.PropAreaSpring.SetAreaSpringProp.assert_not_called()


@pytest.mark.parametrize("failure", ["wrong_stiffness","wrong_option","assign_ret","silent_assign","changed_geometry"])
def test_partial_failure_is_visible_and_never_retried(fixture, failure):
    model, state, plan, table = fixture
    if failure == "wrong_stiffness":
        original = table
        def table(key):
            version, fields, rows = original(key)
            rows[0][3] = ".02"
            return version, fields, rows
    if failure == "wrong_option": state["nonlinear"] = "Tension Only"
    if failure == "assign_ret": model.AreaObj.SetSpringAssignment.side_effect = lambda *args: 1
    if failure == "silent_assign": model.AreaObj.SetSpringAssignment.side_effect = lambda *args: 0
    if failure == "changed_geometry":
        def assign(*args):
            model.AreaObj.GetProperty.return_value = ("CHANGED",0)
            state["assignments"]["A1"] = "CDX_SOIL"
            return 0
        model.AreaObj.SetSpringAssignment.side_effect = assign
    result = apply_plan(model, table, plan, plan["plan_sha256"], True)
    assert not result["ok"] and result["partial_write_possible"] and result["error"]
    assert model.PropAreaSpring.SetAreaSpringProp.call_count == 1
    assert model.AreaObj.SetSpringAssignment.call_count <= 1
    if failure in ("wrong_stiffness","wrong_option"):
        model.AreaObj.SetSpringAssignment.assert_not_called()


def test_nonfinite_and_inconsistent_capture_rejected(fixture):
    model, _, _, _ = fixture
    model.AreaObj.GetTransformationMatrix.return_value = ([1,0,0,0,1,0,0,0,float('nan')],0)
    with pytest.raises(ValueError, match="finito"):
        capture_context(model, model.GetModelFilename(), "TEST")


def test_empty_assignment_is_confirmed_from_table_not_failed_getter(fixture):
    model, _, _, _ = fixture
    model.AreaObj.GetSpringAssignment.side_effect = lambda aid: (None, 1)
    context = capture_context(model, model.GetModelFilename(), "TEST")
    assert context["soil_state"]["assignments"] == {"A1":"None","A2":"None"}
    model.AreaObj.GetSpringAssignment.assert_not_called()
    model.DatabaseTables.GetAllTables.side_effect = None
    model.DatabaseTables.GetAllTables.return_value = (0,[],[],[],[],0)
    with pytest.raises(RuntimeError, match="incompleto"):
        capture_context(model, model.GetModelFilename(), "TEST")


def test_wrappers_keep_com_boundary_and_forward_confirmation(api, monkeypatch):
    safe, model, _ = api
    import soil_transfer
    read = MagicMock(return_value={"context":"test"})
    write = MagicMock(return_value={"ok":True})
    monkeypatch.setattr(soil_transfer, "capture_context", read)
    monkeypatch.setattr(soil_transfer, "apply_plan", write)
    assert safe.get_soil_transfer_context(r"C:\test.fdb", "TEST") == {"context":"test"}
    read.assert_called_once_with(model, r"C:\test.fdb", "TEST")
    assert safe.apply_soil_transfer({"plan":1}, "hash", True) == {"ok":True}
    write.assert_called_once_with(model, safe._read_table, {"plan":1}, "hash", True)
