import copy
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from audit_capture import collect_snapshot
from audit_report import build_report, render_html, write_report
from test_audit_capture import MODEL, PROJECT, FakeModel

PROFILE = "modeling_20261015"


@pytest.fixture
def fake():
    return FakeModel()


@pytest.fixture
def capture(fake):
    return collect_snapshot(fake.read, MODEL, 123, "Modal")


def test_report_reuses_auditor_and_keeps_unknowns(capture):
    report = build_report(PROFILE, PROJECT, capture)
    assert report["overall"] == "incomplete"
    assert report["summary"]["pending"] > 0
    assert report["engineering_approval"] is False
    assert any(
        f["code"] == "persistence" and f["status"] == "pending"
        for f in report["findings"]
    )
    assert not any(f["code"] == "story_geometry" for f in report["findings"])
    assert report["capture_sha256"]


def test_known_difference_and_read_error_are_separate(fake):
    fake.overrides["PropArea.GetSlab"] = [0, 3, "C210", 0.15, 0, "", "g", 0]
    fake.overrides["PointObj.GetRestraint"] = [[], 8]
    c = collect_snapshot(fake.read, MODEL, 123)
    report = build_report(PROFILE, PROJECT, c)
    assert report["summary"]["difference"] > 0 and report["summary"]["error"] > 0
    f = next(f for f in report["findings"] if f.get("observed") == "Membrane")
    assert f["expected"] == "Shell-Thick" and f["evidence_ids"]


def test_reference_levels_are_compared(capture):
    capture["snapshot"]["stories"][0]["elevation_m"] = 4
    r = build_report(PROFILE, PROJECT, capture)
    assert any(
        f["code"] == "story_geometry" and f["observed"] == 4 for f in r["findings"]
    )


def test_html_treats_names_messages_and_json_as_text(capture):
    attack = '</pre><script>alert("x")</script><img src=x onerror=alert(1)>'
    capture["observations"][0]["object"] = attack
    capture["observations"][0]["message"] = attack
    capture["snapshot"]["slabs"][0]["id"] = attack
    html = render_html(build_report(PROFILE, PROJECT, capture), capture)
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert "Content-Security-Policy" in html and 'lang="es"' in html


def test_bundle_is_complete_hashed_and_never_overwritten(tmp_path, capture):
    target = tmp_path / "report"
    receipt = write_report(PROFILE, PROJECT, capture, str(target))
    assert not (target / "INCOMPLETE").exists()
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    assert json.loads(before["proyecto.json"]) == {
        "profile": PROFILE,
        "project": PROJECT,
    }
    assert (
        json.loads(before["informe.json"])["reference_sha256"]
        == sha256(before["proyecto.json"]).hexdigest()
    )
    for name, digest in receipt["files"].items():
        assert sha256(before[name]).hexdigest() == digest
    with pytest.raises(FileExistsError):
        write_report(PROFILE, PROJECT, capture, str(target))
    assert before == {p.name: p.read_bytes() for p in target.iterdir()}


@pytest.mark.parametrize("mutation", ["schema", "identity", "nan", "observations"])
def test_invalid_capture_does_not_create_output(tmp_path, capture, mutation):
    c = copy.deepcopy(capture)
    if mutation == "schema":
        c["schema"] = "unknown"
    if mutation == "identity":
        c["source"]["model_path"] = r"C:\Synthetic\OTHER.EDB"
    if mutation == "nan":
        c["snapshot"]["bad"] = float("nan")
    if mutation == "observations":
        c["observations"] = [{"id": "x", "status": "ok"}]
    with pytest.raises(ValueError):
        write_report(PROFILE, PROJECT, c, str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_cli_report_runs_without_com(tmp_path, capture):
    source = tmp_path / "capture.json"
    source.write_text(json.dumps(capture), encoding="utf-8")
    project = tmp_path / "project.json"
    project.write_text(
        json.dumps({"profile": PROFILE, "project": PROJECT}), encoding="utf-8"
    )
    cli = Path(__file__).resolve().parents[1] / "tools/etabs_audit.py"
    args = [
        sys.executable,
        str(cli),
        "report",
        "--project",
        str(project),
        "--snapshot",
        str(source),
        "--output",
        str(tmp_path / "out"),
    ]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "complete"
    assert subprocess.run(args, capture_output=True, check=False).returncode == 1


def test_report_tool_registers_without_live_adapter():
    from audit_tools import register_audit_tools

    names = []

    class Registry:
        def tool(self):
            return lambda fn: names.append(fn.__name__)

    register_audit_tools(Registry())
    assert names == ["write_etabs_audit_report"]


def test_failed_bundle_write_keeps_incomplete_marker(tmp_path, capture, monkeypatch):
    import audit_report

    def fail_sync(_fd):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(audit_report.os, "fsync", fail_sync)
    target = tmp_path / "partial"
    with pytest.raises(OSError, match="disk failure"):
        write_report(PROFILE, PROJECT, capture, str(target))
    assert (target / "INCOMPLETE").exists()
    assert not (target / "manifest.json").exists()


def test_unknown_opening_load_is_pending(fake):
    fake.overrides["AreaObj.GetOpening"] = [True, 0]
    capture = collect_snapshot(fake.read, MODEL, 123)
    r = build_report(PROFILE, PROJECT, capture)
    finding = next(f for f in r["findings"] if f["code"] == "loaded_opening")
    assert finding["status"] == "pending"


def test_mcp_writer_produces_same_bundle(tmp_path, capture):
    from audit_tools import write_etabs_audit_report

    r = write_etabs_audit_report(PROFILE, PROJECT, capture, str(tmp_path / "tool"))
    assert r["status"] == "complete" and r["overall"] == "incomplete"


def test_real_mcp_sdk_registers_report_schema():
    fastmcp = pytest.importorskip("mcp.server.fastmcp")
    from audit_tools import register_audit_tools

    mcp = fastmcp.FastMCP("synthetic-audit-schema")
    register_audit_tools(mcp)
    tool = mcp._tool_manager.get_tool("write_etabs_audit_report")
    assert set(tool.parameters["required"]) == {
        "profile",
        "project",
        "capture",
        "output_directory",
    }


def test_known_absence_differs_from_failed_pattern_inventory(fake):
    c = collect_snapshot(fake.read, MODEL, 123)
    r = build_report(PROFILE, PROJECT, c)
    missing = next(f for f in r["findings"] if f["code"] == "missing_pattern")
    assert missing["status"] == "difference" and missing["evidence_ids"]
    fake.overrides["LoadPatterns.GetNameList"] = [0, None, 7]
    c = collect_snapshot(fake.read, MODEL, 123)
    r = build_report(PROFILE, PROJECT, c)
    assert not any(f["code"] == "missing_pattern" for f in r["findings"])
    assert any(
        f["status"] == "pending" and f["object"] == "patterns" for f in r["findings"]
    )


def test_observational_report_never_invents_residential_reference(capture):
    report = build_report("observational", {"model_path": MODEL}, capture)
    assert report["overall"] == "incomplete"
    assert report["summary"]["difference"] == 0
    assert report["reference_status"] == "not_provided"
    assert report["inventory"]["slabs"] == 1
    assert any(f["code"] == "reference_missing" for f in report["findings"])
    assert not any(f["code"] == "missing_pattern" for f in report["findings"])
    assert "Sin referencia de diseño" in render_html(report, capture)


@pytest.mark.parametrize(
    "project",
    [
        {"model_path": "relative.edb"},
        {"model_path": MODEL, "usage": "residential"},
        None,
    ],
)
def test_observational_reference_rejects_invalid_or_ignored_criteria(project, capture):
    with pytest.raises((ValueError, TypeError)):
        build_report("observational", project, capture)


def test_observational_report_keeps_read_errors(capture):
    capture["observations"][0].update(status="error", message="synthetic read failure")
    report = build_report("observational", {"model_path": MODEL}, capture)
    assert report["summary"]["error"] == 1


def test_observational_report_still_rejects_wrong_identity(capture):
    with pytest.raises(ValueError, match="modelos distintos"):
        build_report(
            "observational", {"model_path": r"C:\Synthetic\OTHER.EDB"}, capture
        )
