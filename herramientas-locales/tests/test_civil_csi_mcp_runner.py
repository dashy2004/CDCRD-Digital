"""Offline acceptance-runner guards; these tests do not establish native CAD proof."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_civil_csi_mcp.py"
SPEC = importlib.util.spec_from_file_location("civil_csi_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def manifest(tmp_path):
    drawing = tmp_path / "SYNTHETIC_TERRAIN.dwg"
    drawing.write_bytes(b"test fixture, not a native drawing")
    data = {"schema": "cdcrd.civil-csi-test/1", "tolerance_m": 1e-6,
            "site_frame": "SITE", "vertical_datum": "TEST", "surface_handle": "ABC",
            "drawing": str(drawing), "models": {},
            "expected_points": {"A": {"site_xyz_m": [100, 200, 9], "terrain_z_m": 10}}}
    for product, suffix, units, unit in (("ETABS", "EDB", 6, "m"), ("SAFE", "FDB", 9, "mm")):
        path = tmp_path / f"SYNTHETIC_{product}.{suffix}"
        path.write_bytes(b"test fixture, not a native CSI model")
        config = tmp_path / f"{product}.json"
        config.write_text(json.dumps({"source_frame": product, "site_frame": "SITE",
                                      "vertical_datum": "TEST", "point_ids": ["A"]}))
        data["models"][product] = {
            "path": str(path), "config": str(config), "process_id": 123,
            "source_frame": product, "expected_units_enum": units,
            "expected_length_unit": unit, "expected_source_points": {"A": [0, 0, -1]}}
    return data


def test_explicit_manifest_acceptance_has_no_native_side_effects(manifest):
    before = copy.deepcopy(manifest)
    assert runner.validate_manifest(manifest) == before


@pytest.mark.parametrize("key,value", [
    ("schema", "unknown"), ("tolerance_m", 0), ("tolerance_m", .01),
    ("tolerance_m", True), ("tolerance_m", float("nan")),
    ("surface_handle", "not a hex handle"), ("expected_points", {}),
    ("site_frame", ""), ("drawing", "SYNTHETIC_RELATIVE.dwg"),
])
def test_invalid_manifest_is_rejected_before_mcp(manifest, key, value):
    manifest[key] = value
    with pytest.raises(ValueError):
        runner.validate_manifest(manifest)


@pytest.mark.parametrize("key,value", [
    ("process_id", True), ("process_id", 0), ("process_id", "123"),
    ("expected_length_unit", "mm"), ("expected_units_enum", 17),
    ("expected_source_points", {}), ("expected_source_points", {"B": [0, 0, 0]}),
])
def test_wrong_model_contract_rejected(manifest, key, value):
    manifest["models"]["ETABS"][key] = value
    with pytest.raises(ValueError):
        runner.validate_manifest(manifest)


def test_existing_original_named_model_is_forbidden(manifest, tmp_path):
    original = tmp_path / "client.EDB"
    original.write_bytes(b"protected")
    manifest["models"]["ETABS"]["path"] = str(original)
    with pytest.raises(ValueError, match="SYNTHETIC"):
        runner.validate_manifest(manifest)
    assert original.read_bytes() == b"protected"


def test_incomplete_and_disagreeing_config_rejected(manifest):
    del manifest["models"]["SAFE"]["source_frame"]
    with pytest.raises(ValueError, match="Incomplete"):
        runner.validate_manifest(manifest)


def test_config_cannot_select_different_points(manifest):
    config = Path(manifest["models"]["SAFE"]["config"])
    value = json.loads(config.read_text())
    value["point_ids"] = ["A", "A"]
    config.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Config"):
        runner.validate_manifest(manifest)


@pytest.mark.parametrize("result", [
    {"isError": True, "content": []},
    {"content": [{"type": "text", "text": '{"error":"failed"}'}]},
    {"structuredContent": {"error": None}},
    {"content": [{"type": "text", "text": "not JSON"}]},
    {"content": [{"type": "text", "text": "[]"}]},
    {},
    {"structuredContent": {"ok": True},
     "content": [{"type": "text", "text": '{"ok":false}'}]},
])
def test_tool_error_or_ambiguous_response_cannot_pass(result):
    with pytest.raises(RuntimeError):
        runner.parse_tool_result(result)


def test_fastmcp_object_and_wrapped_string_results():
    value = {"schema": "test", "rows": []}
    text = {"type": "text", "text": json.dumps(value)}
    assert runner.parse_tool_result({"content": [text]}) == value
    assert runner.parse_tool_result({"structuredContent": value, "content": [text]}) == value
    assert runner.parse_tool_result({"structuredContent": {"result": json.dumps(value)},
                                     "content": [text]}) == value


def snapshot(spec):
    return {"schema": "cdcrd.csi-points/1", "source": {
        "application": "ETABS", "model": spec["path"], "units_enum": 6,
        "captured_utc": "first"}, "frame": {"id": "ETABS", "axes": "Global", "length_unit": "m"},
        "points": [{"id": "A", "xyz": [0, 0, -1]}], "model_writes": 0}


def test_snapshot_checks_all_points_and_identity(manifest):
    spec = manifest["models"]["ETABS"]
    data = snapshot(spec)
    runner.check_snapshot(data, "ETABS", spec, 1e-6)
    before = runner.snapshot_identity(data)
    data["source"]["captured_utc"] = "second"
    assert runner.snapshot_identity(data) == before
    data["points"].append({"id": "UNEXPECTED", "xyz": [0, 0, 0]})
    with pytest.raises(ValueError, match="IDs"):
        runner.check_snapshot(data, "ETABS", spec, 1e-6)


def test_source_coordinate_error_is_checked_in_metres(manifest):
    spec = manifest["models"]["SAFE"]
    data = snapshot(spec)
    data["source"].update(application="SAFE", units_enum=9)
    data["frame"].update(id="SAFE", length_unit="mm")
    data["points"][0]["xyz"][0] = .0005  # Half a micrometre in mm.
    runner.check_snapshot(data, "SAFE", spec, 1e-6)
    data["points"][0]["xyz"][0] = .01
    with pytest.raises(ValueError, match="source XYZ"):
        runner.check_snapshot(data, "SAFE", spec, 1e-6)


@pytest.mark.parametrize("change", ["units", "path", "frame", "writes"])
def test_snapshot_identity_guards(manifest, change):
    spec = manifest["models"]["ETABS"]
    data = snapshot(spec)
    if change == "units":
        data["source"]["units_enum"] = 9
    elif change == "path":
        data["source"]["model"] += ".other"
    elif change == "frame":
        data["frame"]["axes"] = "Local"
    else:
        data["model_writes"] = 1
    with pytest.raises(ValueError, match="mismatch"):
        runner.check_snapshot(data, "ETABS", spec, 1e-6)


@pytest.mark.parametrize("change", ["elevation", "delta", "missing", "duplicate", "xyz", "nan"])
def test_independent_terrain_expectations_reject_bad_results(manifest, change):
    rows = [{"id": "A", "site_xyz_m": [100, 200, 9], "terrain_z_m": 10,
             "terrain_minus_joint_m": 1, "status": "ok"}]
    runner.check_result(rows, manifest["expected_points"], 1e-6, review=True)
    if change == "elevation":
        rows[0]["terrain_z_m"] = 11
    elif change == "delta":
        rows[0]["terrain_minus_joint_m"] = -1
    elif change == "missing":
        rows[0]["status"] = "sin_cota"
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif change == "xyz":
        rows[0]["site_xyz_m"][0] = 100.01
    else:
        rows[0]["terrain_z_m"] = float("nan")
    with pytest.raises(ValueError):
        runner.check_result(rows, manifest["expected_points"], 1e-6, review=True)


def test_exclusive_receipt_and_hash_change_detection(tmp_path):
    output = tmp_path / "result.json"
    runner.write_new(output, {"ok": True})
    before = runner.sha256(output)
    with pytest.raises(FileExistsError):
        runner.write_new(output, {"ok": False})
    assert runner.sha256(output) == before
    output.write_text("changed")
    assert runner.sha256(output) != before


def test_help_needs_no_mcp_or_native_app(capsys):
    with pytest.raises(SystemExit) as exit_info:
        runner.main(["--help"])
    assert exit_info.value.code == 0
    assert "--python-csi" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["changed_model", "execute_exception"])
def test_main_seals_failure_on_changed_file_or_execution_error(
    manifest, tmp_path, monkeypatch, failure
):
    """Only the async boundary is replaced; real file hashing and report sealing run."""
    repo = tmp_path / "checkout"
    for folder, section in (("servidor-mcp", "fea"), ("servidor-mcp-safe", "safe")):
        src = repo / folder / "src"
        src.mkdir(parents=True)
        (src / "config.json").write_text(json.dumps({
            section: {"auto_start": False, "software": "ETABS"}}))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    runtime = tmp_path / "python.exe"
    runtime.write_bytes(b"placeholder, never executed")

    async def fail_without_native_calls(self, data):
        if failure == "changed_model":
            Path(data["models"]["ETABS"]["path"]).write_bytes(b"changed fixture")
        else:
            raise RuntimeError("offline injected execution failure")

    monkeypatch.setattr(runner.Runner, "execute", fail_without_native_calls)
    exit_code = runner.main([
        "--manifest", str(manifest_path), "--repo", str(repo),
        "--python-csi", str(runtime), "--python-local", str(runtime), "--run-id", "negative"])
    result_path = repo / "herramientas-locales" / "salidas" / "negative" / "RESULT.json"
    result = runner.read_json(result_path)
    assert exit_code == 1
    assert result["status"] == "failed"
    assert result["native_verified"] is False
    if failure == "changed_model":
        assert result["model_files_unchanged"] is False
        assert "changed" in result["integrity_error"]
    else:
        assert result["model_files_unchanged"] is True
        assert "offline injected execution failure" in result["error"]
