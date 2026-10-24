import copy
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from cdcrd_local.foundation_exchange import prepare, review, run_files

ROOT = Path(__file__).resolve().parents[2]


def load(relative):
    spec = importlib.util.spec_from_file_location("test_adapter", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs():
    snapshot = {"schema": "cdcrd.csi-points/1", "source": {"application": "SAFE"},
                "frame": {"id": "LOCAL", "axes": "Global", "length_unit": "mm"},
                "points": [{"id": "A", "xyz": [0, 0, -1000]},
                           {"id": "B", "xyz": [6000, 0, -1000]}]}
    config = {"source_frame": "LOCAL", "source_origin": [0, 0, 0],
              "site_origin_m": [100, 200, 10], "rotation_deg": 90,
              "site_frame": "SITE", "vertical_datum": "TEST-DATUM", "point_ids": ["A", "B"],
              "control_tolerance_m": 0.002,
              "controls": [{"id": "C1", "source_xyz": [0, 0, 0], "site_xyz_m": [100, 200, 10]},
                           {"id": "C2", "source_xyz": [6000, 0, 0], "site_xyz_m": [100, 206, 10]}]}
    return snapshot, config


def samples(query):
    return {"schema": "cdcrd.foundation-samples/1", "query_sha256": query["query_sha256"],
            "site_frame": "SITE", "vertical_datum": "TEST-DATUM", "length_unit": "m",
            "source": {"drawing": "synthetic.dwg", "surface": "ABC", "is_out_of_date": False},
            "samples": [{"id": p["id"], "xy_m": p["site_xyz_m"][:2],
                         "terrain_z_m": 11, "status": "ok"} for p in query["points"]]}


def test_rotation_units_datum_and_no_inferred_soil(inputs):
    source, config = inputs
    before = copy.deepcopy(inputs)
    q = prepare(source, config)
    assert q["points"][1]["site_xyz_m"] == pytest.approx([100, 206, 9])
    report = review(q, samples(q))
    assert report["ok"] and report["rows"][0]["terrain_minus_joint_m"] == 2
    assert report["geotechnical"] is None and report["model_writes"] == 0
    assert not report["analysis_run"] and not report["design_approved"]
    assert inputs == before


@pytest.mark.parametrize("key,value", [("rotation_deg", 0), ("rotation_deg", float("nan")),
    ("source_frame", "OTHER"), ("point_ids", ["A", "A"]), ("point_ids", ["X"]),
    ("point_ids", []), ("site_origin_m", [100, 200, 11]), ("control_tolerance_m", 1)])
def test_wrong_transform_and_scope_rejected(inputs, key, value):
    source, config = inputs
    config[key] = value
    with pytest.raises(ValueError):
        prepare(source, config)


def test_controls_must_be_distinct_and_present(inputs):
    source, config = inputs
    config["controls"] = [config["controls"][0], dict(config["controls"][0], id="OTHER")]
    with pytest.raises(ValueError, match="separacion"):
        prepare(source, config)


@pytest.mark.parametrize("mutate", [lambda r: r.update(query_sha256="bad"),
    lambda r: r["samples"].pop(), lambda r: r["samples"].append(r["samples"][0]),
    lambda r: r["samples"][0].update(xy_m=[0, 0]),
    lambda r: r["source"].update(is_out_of_date=True),
    lambda r: r.update(length_unit="ft")])
def test_stale_or_mismatched_samples_rejected(inputs, mutate):
    q = prepare(*inputs)
    r = samples(q)
    mutate(r)
    with pytest.raises(ValueError):
        review(q, r)


def test_missing_elevation_not_zero_and_independent_soil(inputs):
    q = prepare(*inputs)
    r = samples(q)
    r["samples"][0].update(status="error", terrain_z_m=None, error="PointNotOnEntity")
    soil = {"source": "SYNTHETIC TEST", "allowable_bearing_kpa": 100,
            "subgrade_modulus_kn_m3": 18000, "applicable_point_ids": ["B"]}
    report = review(q, r, soil)
    assert not report["ok"] and report["rows"][0]["terrain_minus_joint_m"] is None
    assert report["geotechnical"]["subgrade_modulus_kn_m3"] == 18000
    del soil["subgrade_modulus_kn_m3"]
    with pytest.raises(KeyError):
        review(q, r, soil)


def test_modified_query_and_overwrite_rejected(inputs, tmp_path):
    q = prepare(*inputs)
    q["points"][0]["site_xyz_m"][0] += 1
    with pytest.raises(ValueError, match="hash"):
        review(q, samples(q))
    source, config = [tmp_path / n for n in ("source.json", "config.json")]
    for path, value in zip((source, config), inputs):
        path.write_text(json.dumps(value))
    output = tmp_path / "result.json"
    run_files("prepare", source, config, output)
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        run_files("prepare", source, config, output)
    assert output.read_bytes() == original


@pytest.mark.parametrize("server", ["servidor-mcp", "servidor-mcp-safe"])
def test_native_read_contract_and_faults(server):
    capture = load(server + "/src/coordinate_snapshot.py").capture_points
    model = Mock()
    path = r"C:\synthetic\copy.fdb"
    model.GetModelFilename.return_value = path
    model.GetPresentUnits.return_value = 9
    model.PointObj.Count.return_value = 1
    model.PointObj.GetAllPoints.return_value = (1, ["P"], [0.], [4.], [-1.], 0)
    r = capture(model, "SAFE", path, "LOCAL")
    assert r["frame"]["length_unit"] == "mm" and r["points"][0]["xyz"] == [0, 4, -1]
    assert all("Set" not in str(call) and "Save" not in str(call) for call in model.mock_calls)
    with pytest.raises(ValueError, match="distinto"):
        capture(model, "SAFE", r"C:\other.fdb", "LOCAL")
    model.PointObj.GetAllPoints.return_value = (1, ["P"], [], [4.], [-1.], 0)
    with pytest.raises(RuntimeError, match="Arrays"):
        capture(model, "SAFE", path, "LOCAL")
    model.PointObj.GetAllPoints.return_value = (1, ["P"], [0.], [4.], [-1.], 1)
    with pytest.raises(RuntimeError, match="fallo"):
        capture(model, "SAFE", path, "LOCAL")
    model.PointObj.GetAllPoints.return_value = (1, ["P"], [0.], [4.], [-1.], 0)
    model.GetPresentUnits.side_effect = [9, 6]
    with pytest.raises(RuntimeError, match="cambio"):
        capture(model, "SAFE", path, "LOCAL")


def test_adapter_copies_stay_identical():
    assert (ROOT / "servidor-mcp/src/coordinate_snapshot.py").read_bytes() == (
        ROOT / "servidor-mcp-safe/src/coordinate_snapshot.py").read_bytes()


def test_incomplete_file_contract_is_actionable_and_writes_nothing(tmp_path):
    source, config, output = [tmp_path / name for name in ("s.json", "c.json", "out.json")]
    source.write_text('{"schema":"cdcrd.csi-points/1"}')
    config.write_text('{}')
    with pytest.raises(ValueError, match="Contrato incompleto"):
        run_files("prepare", source, config, output)
    assert not output.exists()


def test_civil_native_contract_and_outside_surface(inputs):
    adapter = load("servidor-mcp-civil3d/src/cimentaciones.py")
    q = prepare(*inputs)
    called = []
    def bridge(method, params):
        called.append(method)
        if method == "doc.info":
            return {"dibujo": r"C:\test.dwg", "civil3d": True, "insunits": 6}
        if method == "objects.read":
            return {"valor": "Meters"}
        if method == "objects.query":
            return {"objetos": [{"tipo": "Autodesk.Civil.DatabaseServices.TinSurface",
                                 "IsOutOfDate": False, "Name": "TIN"}]}
        if method == "objects.invoke":
            if params["args"][1] > 205:
                raise RuntimeError("PointNotOnEntity")
            return {"resultado": 11}
        raise AssertionError(method)
    r = adapter.sample(bridge, q, r"C:\test.dwg", "ABC", "SITE", "TEST-DATUM")
    assert not review(q, r)["ok"]
    assert set(called) == {"doc.info", "objects.read", "objects.query", "objects.invoke"}
    with pytest.raises(ValueError, match="Dibujo"):
        adapter.sample(bridge, q, r"C:\wrong.dwg", "ABC", "SITE", "TEST-DATUM")
