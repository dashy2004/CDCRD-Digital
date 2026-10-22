"""Executable synthetic OAPI fixture, including failures; never imports COM."""

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from audit_capture import LENGTH_TO_M, READ_METHODS, collect_snapshot, mass_source

MODEL = r"C:\Synthetic\AUDIT_DEMO.EDB"
PROJECT = {
    "model_path": MODEL,
    "usage": "residential",
    "has_parking": False,
    "stories": [{"name": "E1", "architectural_height_m": 3.0}],
}


def mass_table():
    fields = [
        "Name",
        "IsDefault",
        "SourceSelf",
        "SourceAdded",
        "SourceLoads",
        "IncLateral",
        "IncVertical",
        "LoadPattern",
        "Multiplier",
    ]
    rows = [
        ["M1", "Yes", "No", "No", "Yes", "Yes", "No", "Dead", "1"],
        ["", "", "", "", "", "", "", "Live", "0.15"],
        ["", "", "", "", "", "", "", "LiveT", "0.1"],
    ]
    return [[], 1, fields, len(rows), [cell for row in rows for cell in row], 0]


class FakeModel:
    """Literal responses follow the documented typelib, not collector helpers."""

    def __init__(self, units=12):
        self.units = units
        self.calls = []
        self.overrides = {}
        self.xyz = {
            "P1": [0, 0, 3.5],
            "P2": [5, 0, 3.5],
            "P3": [5, 4, 3.5],
            "P4": [0, 4, 3.5],
            "P0": [0, 0, 0],
        }

    def read(self, path, *args):
        self.calls.append((path, args))
        if path in self.overrides:
            override = self.overrides[path]
            if isinstance(override, Exception):
                raise override
            return copy.deepcopy(override(*args) if callable(override) else override)
        scale = LENGTH_TO_M[self.units - 1]
        if path == "GetModelFilename":
            return MODEL
        if path == "GetPresentUnits":
            return self.units
        if path == "GetModelIsLocked":
            return True
        if path == "GetVersion":
            return ["23.3.0", 23.3, 0]
        if path == "Story.GetStories_2":
            return [
                0.0,
                1,
                ["E1"],
                [3.5 / scale],
                [3.5 / scale],
                [True],
                ["None"],
                [False],
                [0.0],
                [0],
                0,
            ]
        lists = {
            "PointObj": list(self.xyz),
            "FrameObj": ["B1"],
            "AreaObj": ["A1"],
            "PropArea": ["L15"],
            "PropMaterial": ["C210"],
            "LoadPatterns": ["Dead", "Live", "LiveT"],
        }
        if path.endswith(".GetNameList"):
            names = lists[path.split(".")[0]]
            return [len(names), names, 0]
        if path == "PointObj.GetCoordCartesian":
            return [*[v / scale for v in self.xyz[args[0]]], 0]
        if path == "PointObj.GetRestraint":
            return [[args[0] == "P0"] * 6, 0]
        if path == "PointObj.GetDiaphragm":
            return [2, "", 0]
        if path == "PointObj.GetLabelFromName":
            return [args[0], "Base" if args[0] == "P0" else "E1", 0]
        if path == "FrameObj.GetPoints":
            return ["P1", "P2", 0]
        if path == "FrameObj.GetSection":
            return ["B30x50", "", 0]
        if path == "FrameObj.GetEndLengthOffset":
            return [True, 0.0, 0.0, 1.0, 0]
        if path == "AreaObj.GetDesignOrientation":
            return [2, 0]
        if path == "AreaObj.GetPoints":
            return [4, ["P1", "P2", "P3", "P4"], 0]
        if path == "AreaObj.GetProperty":
            return ["L15", 0]
        if path == "AreaObj.GetOpening":
            return [False, 0]
        if path == "AreaObj.GetDiaphragm":
            return ["D1", 0]
        if path == "AreaObj.GetLabelFromName":
            return ["F1", "E1", 0]
        if path == "AreaObj.GetLoadUniform":
            return [1, ["A1"], ["Dead"], ["Global"], [10], [-0.16], 0]
        if path == "AreaObj.GetLoadUniformToFrame":
            return [0, None, None, None, None, None, None, 0]
        if path == "PropArea.GetTypeOAPI":
            return [2, 0]
        if path == "PropArea.GetSlab":
            return [0, 2, "C210", 0.15 / scale, 0, "", "guid", 0]
        if path == "PropMaterial.GetMaterial":
            return [2, 0, "", "guid-mat", 0]
        if path == "LoadPatterns.GetLoadType":
            return [1 if args[0] == "Dead" else 3, 0]
        if path == "LoadPatterns.GetSelfWTMultiplier":
            return [1.0 if args[0] == "Dead" else 0.0, 0]
        if path == "LoadCases.GetTypeOAPI":
            return [3, 1, 0]
        if path == "LoadCases.ModalEigen.GetNumberModes":
            return [3, 1, 0]
        if path == "DatabaseTables.GetTableForDisplayArray":
            return mass_table()
        if path == "Analyze.GetCaseStatus":
            return [2, ["Dead", "Modal"], [4, 4], 0]
        raise AssertionError(f"Unexpected call {path}")


@pytest.fixture
def fake():
    return FakeModel()


@pytest.fixture
def capture(fake):
    return collect_snapshot(fake.read, MODEL, 123, "Modal")


def test_snapshot_is_real_reading_not_profile_echo(capture, fake):
    s = capture["snapshot"]
    assert s["slabs"][0]["vertices_m"] == [
        [0, 0, 3.5],
        [5, 0, 3.5],
        [5, 4, 3.5],
        [0, 4, 3.5],
    ]
    assert s["slab_definitions"][0]["h_m"] == 0.15
    assert s["joints"][-1]["at_base"] is True
    assert s["modal_max_modes"] == 3
    assert s["mass_source"]["factors"] == {"Dead": 1, "Live": 0.15, "LiveT": 0.1}
    assert "directions" not in s["slabs"][0] and "load_components" not in s["slabs"][0]
    assert "pdelta" not in s and "saved_readback_verified" not in s
    assert capture["coverage"] == "partial" and not capture["model_modified"]
    assert all(
        path in READ_METHODS and path.split(".")[-1].startswith("Get")
        for path, _ in fake.calls
    )
    assert not any("Mesh" in path for path, _ in fake.calls)
    json.dumps(capture, allow_nan=False)


@pytest.mark.parametrize("units", range(1, 17))
def test_geometry_conversion_does_not_change_active_units(units):
    fake = FakeModel(units)
    c = collect_snapshot(fake.read, MODEL, 123)
    assert c["snapshot"]["slabs"][0]["vertices_m"][2] == pytest.approx([5, 4, 3.5])
    assert c["snapshot"]["slab_definitions"][0]["h_m"] == pytest.approx(0.15)
    assert c["source"]["units_enum"] == units
    assert not any(path.startswith("Set") for path, _ in fake.calls)


@pytest.mark.parametrize(
    "result", [[1, ["A1"], 7], [2, ["A1"], 0], [True, [], 0], [1, [""], 0]]
)
def test_failed_inventory_never_becomes_empty_model(fake, result):
    fake.overrides["AreaObj.GetNameList"] = result
    c = collect_snapshot(fake.read, MODEL, 123)
    assert "slabs" not in c["snapshot"] and "walls" not in c["snapshot"]
    assert any(
        o["status"] == "error" and o["section"] == "AreaObj" for o in c["observations"]
    )


def test_verified_empty_and_unavailable_are_distinct(fake):
    fake.overrides["FrameObj.GetNameList"] = [0, None, 0]
    fake.overrides["PropMaterial.GetNameList"] = AttributeError("unsupported")
    c = collect_snapshot(fake.read, MODEL, 123)
    assert c["snapshot"]["frames"] == [] and "materials" not in c["snapshot"]
    assert any(o["status"] == "unavailable" for o in c["observations"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "0.15"])
def test_invalid_numbers_are_read_errors_not_values(fake, bad):
    fake.overrides["PropArea.GetSlab"] = [0, 2, "C210", bad, 0, "", "g", 0]
    c = collect_snapshot(fake.read, MODEL, 123)
    assert "h_m" not in c["snapshot"]["slab_definitions"][0]
    json.dumps(c, allow_nan=False)


def test_wrong_model_rejected_before_geometry(fake):
    with pytest.raises(ValueError, match="Identidad"):
        collect_snapshot(fake.read, r"C:\Synthetic\OTHER.EDB", 123)
    assert not any(path.startswith("AreaObj") for path, _ in fake.calls)


@pytest.mark.parametrize(
    "field,new",
    [
        ("GetPresentUnits", 6),
        ("GetModelIsLocked", False),
        ("GetModelFilename", r"C:\Synthetic\OTHER.EDB"),
    ],
)
def test_boundary_change_invalidates_capture(fake, field, new):
    original = {
        "GetPresentUnits": 12,
        "GetModelIsLocked": True,
        "GetModelFilename": MODEL,
    }[field]
    fake.overrides[field] = lambda: (
        original if sum(p == field for p, _ in fake.calls) == 1 else new
    )
    with pytest.raises(ValueError):
        collect_snapshot(fake.read, MODEL, 123)


def test_inventory_change_invalidates_capture(fake):
    fake.overrides["FrameObj.GetNameList"] = lambda: (
        [1, ["B1"], 0]
        if sum(p == "FrameObj.GetNameList" for p, _ in fake.calls) == 1
        else [0, [], 0]
    )
    with pytest.raises(ValueError, match="Inventario"):
        collect_snapshot(fake.read, MODEL, 123)


def test_limits_prevent_silent_truncation(fake):
    c = collect_snapshot(fake.read, MODEL, 123, max_objects=2)
    assert "joints" not in c["snapshot"]
    assert "vertices_m" not in c["snapshot"]["slabs"][0]


@pytest.mark.parametrize(
    "args",
    [
        (MODEL, 0, 10),
        (MODEL, True, 10),
        (MODEL, 123, 0),
        ("relative.edb", 123, 10),
        (MODEL, 123, True),
    ],
)
def test_invalid_identity_limits_do_not_call_api(fake, args):
    with pytest.raises(ValueError):
        collect_snapshot(fake.read, args[0], args[1], max_objects=args[2])
    assert not fake.calls


def test_ribbed_overall_depth_and_topping(fake):
    fake.overrides["PropArea.GetSlab"] = [3, 2, "C210", 0.05, 0, "", "g", 0]
    fake.overrides["PropArea.GetSlabRibbed"] = [0.25, 0.05, 0.15, 0.15, 0.65, 1, 0]
    row = collect_snapshot(fake.read, MODEL, 123)["snapshot"]["slab_definitions"][0]
    assert row["h_m"] == 0.25 and row["topping_m"] == 0.05


def test_unclassified_area_remains_visible(fake):
    fake.overrides["AreaObj.GetDesignOrientation"] = [5, 0]
    s = collect_snapshot(fake.read, MODEL, 123)["snapshot"]
    assert s["slabs"] == [] and s["unclassified_areas"][0]["id"] == "A1"


def test_mass_source_conflict_is_not_accepted():
    r = mass_table()
    r[4][len(r[2]) + 1] = "No"
    with pytest.raises(ValueError, match="contradictorios"):
        mass_source(r)


def test_adapter_is_sta_and_refuses_unpinned_before_connect():
    tree = ast.parse((SRC / "Etabs.py").read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Etabs"
    )
    method = next(
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "capture_etabs_audit_snapshot"
    )
    assert [ast.unparse(x) for x in method.decorator_list] == ["com_call"]
    method.decorator_list = []
    ns = {"EtabsError": RuntimeError}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "adapter", "exec"), ns)  # noqa: S102 -- Local method only; isolate it from COM imports.

    class Unpinned:
        process_id = 0
        auto_start = False

        def _model(self):
            raise AssertionError("Must not connect")

    with pytest.raises(RuntimeError, match="process_id"):
        ns[method.name](Unpinned(), MODEL)


def test_mass_source_accepts_repeated_source_names():
    data = mass_table()
    data[4][9] = "M1"
    data[4][18] = "M1"
    assert mass_source(data)["factors"] == {"Dead": 1, "Live": 0.15, "LiveT": 0.1}


def test_waffle_and_ritz_use_their_own_contracts(fake):
    fake.overrides["PropArea.GetSlab"] = [4, 2, "C210", 0.05, 0, "", "g", 0]
    fake.overrides["PropArea.GetSlabWaffle"] = [0.3, 0.06, 0.15, 0.15, 0.65, 0.65, 0]
    fake.overrides["LoadCases.GetTypeOAPI"] = [3, 2, 0]
    fake.overrides["LoadCases.ModalRitz.GetNumberModes"] = [12, 1, 0]
    s = collect_snapshot(fake.read, MODEL, 123, "Modal")["snapshot"]
    assert s["slab_definitions"][0]["h_m"] == 0.3
    assert s["slab_definitions"][0]["topping_m"] == 0.06
    assert s["modal_max_modes"] == 12


def test_adapter_dispatches_only_explicit_getters(fake):
    from types import SimpleNamespace

    tree = ast.parse((SRC / "Etabs.py").read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Etabs"
    )
    method = next(
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "capture_etabs_audit_snapshot"
    )
    method.decorator_list = []
    scope = {"EtabsError": RuntimeError}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "adapter", "exec"), scope)  # noqa: S102 -- Isolated local adapter, no COM.
    model = SimpleNamespace()
    for path in READ_METHODS:
        parts = path.split(".")
        owner = model
        for part in parts[:-1]:
            if not hasattr(owner, part):
                setattr(owner, part, SimpleNamespace())
            owner = getattr(owner, part)
        setattr(owner, parts[-1], lambda *args, path=path: fake.read(path, *args))
    adapter = SimpleNamespace(process_id=123, auto_start=False, _model=lambda: model)
    c = scope[method.name](adapter, MODEL, "Modal")
    assert c["source"]["process_id"] == 123
    assert c["snapshot"]["modal_max_modes"] == 3
    assert not any(o["status"] == "error" for o in c["observations"])
