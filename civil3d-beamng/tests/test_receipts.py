"""Synthetic operation receipts: evidence cannot promote itself to native proof."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from uuid import UUID

import pytest

from cdcrd_beamng import build_package, verify_package

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def source(tmp_path):
    data = json.loads((REPO / "civil3d-beamng/examples/snapshot-synthetic.json").read_text())
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def record(operation, receipt, **options):
    from cdcrd_beamng.receipts import record_operation
    return record_operation(operation, receipt, **options)


def test_validate_receipt_records_identity_times_hashes_result_and_evidence(source):
    receipt = source.parent / "receipt.json"
    attachment = source.parent / "native.json"
    attachment.write_text('{"correcto":true,"saved_reopened":true}')
    report = record("validate", receipt, snapshot=source, evidence=[attachment])
    assert report == json.loads(receipt.read_text(encoding="utf-8"))
    assert report["schema"] == "cdcrd.operation-receipt/1"
    assert report["ok"] and report["status"] == "succeeded"
    assert UUID(report["id"]) and report["module"] == "beamng"
    assert report["tool"]["version"]
    assert datetime.fromisoformat(report["finished_utc"]) >= datetime.fromisoformat(report["started_utc"])
    assert report["duration_seconds"] >= 0
    assert report["result"]["schema"] == "cdcrd.interchange-validation/1"
    item = report["files"]["inputs"][0]
    assert item["id"] == "snapshot" and item["path"] == "snapshot.json"
    assert item["state"] == "unchanged"
    assert item["before"] == item["after"]
    assert item["before"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert item["before"]["bytes"] == source.stat().st_size
    assert report["files"]["outputs"] == []
    assert report["evidence"]["attachments"][0]["assessment"] == "hash_only"
    assert report["evidence"]["native_operation"] == "not_checked"
    assert report["evidence"]["consumer_validation"] == "not_checked"
    assert report["authenticity"] == "unsigned"


def test_failed_validation_is_saved_with_its_real_result(source):
    source.write_text('{"schema":"cdcrd.civil3d.snapshot/1","units":"ft"}')
    report = record("validate", source.parent / "failed.json", snapshot=source)
    assert not report["ok"] and report["status"] == "failed"
    assert report["execution"]["attempted"]
    assert not report["result"]["ok"]
    assert report["files"]["inputs"][0]["before"]["sha256"]


def test_build_and_verify_receipts_reuse_the_package_manifest(source):
    folder = source.parent / "package"
    report = record("build", source.parent / "build.json", snapshot=source,
                    output=folder, level_id="synthetic_receipt", road_is_drivable=True)
    assert report["ok"] and report["result"]["level_id"] == "synthetic_receipt"
    manifest = verify_package(folder)
    outputs = report["files"]["outputs"]
    assert len(outputs) == len(manifest["sha256s"]) + 1
    for item in outputs:
        path = source.parent / item["path"]
        assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["evidence"]["level"] == "package_file_integrity"
    assert report["parameters"]["road_is_drivable"] is True
    verified = record("verify", source.parent / "verify.json", folder=folder)
    assert verified["ok"] and verified["files"]["outputs"] == []
    assert len(verified["files"]["inputs"]) == len(outputs)
    asset = folder / "art/shapes/road.dae"
    asset.write_bytes(asset.read_bytes() + b"changed")
    corrupted = record("verify", source.parent / "corrupted.json", folder=folder)
    assert not corrupted["ok"] and corrupted["errors"]


def test_preserves_existing_receipts_and_refuses_receipts_inside_packages(source):
    receipt = source.parent / "existing.json"
    receipt.write_bytes(b"keep original")
    folder = source.parent / "package"
    with pytest.raises(FileExistsError):
        record("build", receipt, snapshot=source, output=folder, level_id="synthetic_receipt")
    assert receipt.read_bytes() == b"keep original" and not folder.exists()
    with pytest.raises(ValueError):
        record("build", folder / "receipt.json", snapshot=source, output=folder,
               level_id="synthetic_receipt")
    assert not folder.exists()


@pytest.mark.parametrize("missing", ["source", "evidence"])
def test_unavailable_inputs_save_failure_without_executing_the_operation(source, missing):
    from cdcrd_beamng import receipts
    if missing == "source":
        source.unlink()
    evidence = [source.parent / "missing.png"] if missing == "evidence" else []
    with patch.object(receipts, "validate_interchange") as operation:
        report = record("validate", source.parent / "unavailable.json", snapshot=source,
                        evidence=evidence)
    operation.assert_not_called()
    assert not report["ok"] and not report["execution"]["attempted"]
    assert report["errors"]


def test_changed_source_invalidates_receipt_even_if_validation_returned_success(source):
    from cdcrd_beamng import receipts
    def mutate(**options):
        source.write_text("changed during operation")
        return {"ok": True, "schema": "cdcrd.interchange-validation/1"}
    with patch.object(receipts, "validate_interchange", side_effect=mutate):
        report = record("validate", source.parent / "changed.json", snapshot=source)
    assert not report["ok"] and report["result"]["ok"]
    assert report["files"]["inputs"][0]["state"] == "changed"
    assert any(error["code"] == "files_changed" for error in report["errors"])


def test_failed_build_is_recorded_without_claiming_outputs(source):
    report = record("build", source.parent / "failed-build.json", snapshot=source,
                    output=source.parent / "package", level_id="INVALID")
    assert not report["ok"] and report["errors"]
    assert report["files"]["outputs"] == []


def test_unknown_operation_never_creates_a_receipt(source):
    target = source.parent / "bad.json"
    with pytest.raises(ValueError):
        record("execute-native", target, snapshot=source)
    assert not target.exists()


def test_atomic_publication_preserves_a_concurrent_receipt(source):
    from cdcrd_beamng import receipts
    real_link = os.link
    target = source.parent / "concurrent.json"
    def competing_writer(src, dst):
        target.write_text("other writer")
        return real_link(src, dst)
    with patch.object(receipts.os, "link", side_effect=competing_writer):
        with pytest.raises(FileExistsError):
            record("validate", target, snapshot=source)
    assert target.read_text() == "other writer"
    assert not list(source.parent.glob(".receipt-*"))


def test_build_receipt_detects_asset_change_after_package_verification(source):
    from cdcrd_beamng import receipts
    real_fingerprint = receipts._fingerprint
    def changed_asset(path):
        if path.name == "road.dae":
            path.write_bytes(path.read_bytes() + b"changed after verification")
        return real_fingerprint(path)
    with patch.object(receipts, "_fingerprint", side_effect=changed_asset):
        report = record("build", source.parent / "changed-output.json", snapshot=source,
                        output=source.parent / "package", level_id="synthetic_receipt")
    assert not report["ok"] and report["errors"]
    assert report["evidence"]["level"] == "none"
    assert report["result"]["level_id"] == "synthetic_receipt"
    assert report["execution"]["completed"]


def test_verify_receipt_keeps_existing_package_symlink_rejection(source):
    folder = source.parent / "package"
    build_package(snapshot=source, output=folder, level_id="synthetic_receipt")
    alias = source.parent / "alias"
    alias.symlink_to(folder, target_is_directory=True)
    report = record("verify", source.parent / "symlink.json", folder=alias)
    assert not report["ok"]


def test_common_cli_refuses_a_dangling_receipt_symlink(source):
    alias, destination = source.parent / "alias.json", source.parent / "not-created.json"
    alias.symlink_to(destination)
    env = dict(os.environ, PYTHONUTF8="1")
    env["PYTHONPATH"] = str(REPO / "herramientas-locales/src")
    result = subprocess.run([sys.executable, "-m", "cdcrd_local.cli", "validar-intercambio",
        "--modulo", "beamng", "--repo", str(REPO), "--snapshot", str(source),
        "--recibo", str(alias)], cwd=source.parent, env=env, capture_output=True, timeout=60)
    assert result.returncode == 2
    assert alias.is_symlink() and not destination.exists()


@pytest.mark.parametrize("module,command,flag", [
    ("cdcrd_beamng", ["validate"], "--receipt"),
    ("cdcrd_local.cli", ["validar-intercambio", "--modulo", "beamng", "--repo", str(REPO)], "--recibo"),
])
def test_real_cli_receipt_success_failure_and_no_overwrite(source, module, command, flag):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "civil3d-beamng"),
                                        str(REPO / "herramientas-locales/src")])
    target = source.parent / "cli.json"
    args = [sys.executable, "-m", module, *command, "--snapshot", source.name, flag, target.name]
    result = subprocess.run(args, cwd=source.parent, env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema"] == "cdcrd.operation-receipt/1"
    assert json.loads(target.read_text())["ok"]
    original = target.read_bytes()
    result = subprocess.run(args, cwd=source.parent, env=env, capture_output=True, timeout=60)
    assert result.returncode == 2
    assert target.read_bytes() == original
    target.unlink()
    source.write_text("invalid JSON")
    result = subprocess.run(args, cwd=source.parent, env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 1, result.stderr
    assert not json.loads(target.read_text())["ok"]
