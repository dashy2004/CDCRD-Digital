"""Unify file-operation results and evidence; never infer a native CAD/game run."""
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from . import __version__
from .package import build_package, file_hash, relative_file, verify_package
from .sources import read_json
from .validation import validate_interchange

SCHEMA = "cdcrd.operation-receipt/1"
SOURCE_FILES = ("snapshot", "terrain_landxml", "road_landxml", "road_guide")
KNOWN_ERRORS = (ValueError, OSError, ParseError, DefusedXmlException, OverflowError)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _error(stage, error):
    message = (f"File access failed ({type(error).__name__})"
               if isinstance(error, OSError) else str(error))
    return {"code": stage, "type": type(error).__name__, "message": message}


def _fingerprint(path):
    before = path.stat()
    if not path.is_file():
        raise ValueError("Expected a regular file")
    digest = file_hash(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size, after.st_mtime_ns, after.st_ino
    ):
        raise ValueError("File changed while hashing")
    return {"bytes": after.st_size, "sha256": digest}


def _path(path, base):
    try:
        return Path(os.path.relpath(path.resolve(), base)).as_posix()
    except ValueError:  # Different Windows drives cannot form a relative path.
        return path.resolve().as_posix()


def _track(identifier, path, base, errors):
    item = {"id": identifier, "path": _path(path, base), "before": None,
            "after": None, "state": "unavailable"}
    try:
        item["before"] = _fingerprint(path)
    except (OSError, ValueError) as error:
        errors.append(_error("input_unavailable", error))
    return item


def _finish(item, path, errors):
    try:
        item["after"] = _fingerprint(path)
    except (OSError, ValueError) as error:
        errors.append(_error("input_unavailable", error))
    if item["before"] is not None and item["after"] == item["before"]:
        item["state"] = "unchanged"
    else:
        item["state"] = "changed" if item["before"] is not None else "unavailable"
        errors.append({"code": "files_changed", "message": "Input or evidence changed or is unavailable"})


def _package_files(folder):
    if folder.is_symlink():
        raise ValueError("Package folder must not be a symlink")
    manifest = read_json(relative_file(folder, "manifest.json"))
    hashes = manifest.get("sha256s") if isinstance(manifest, dict) else None
    if not isinstance(hashes, dict):
        raise ValueError("Package requires a manifest hash map")
    return [("manifest", relative_file(folder, "manifest.json"))] + [
        (name, relative_file(folder, name)) for name in sorted(hashes)]


def _publish(receipt, report):
    # A hard link atomically claims the final name without replacing another writer.
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=".receipt-", dir=receipt.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, receipt)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def record_operation(operation, receipt, *, evidence=(), **options):
    """Execute validate/build/verify once and save a new, unsigned receipt.

    The receipt belongs outside package folders. Referenced evidence is hashed,
    not interpreted as proof. File stability is checked around the operation;
    callers must still avoid concurrent writers (this is not a file lock).
    """
    if operation not in {"validate", "build", "verify"}:
        raise ValueError("Receipt operation must be validate, build or verify")
    target = Path(receipt).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError("Receipt already exists; choose a new file")
    target = target.resolve()
    folder = (Path(options["output" if operation == "build" else "folder"]).absolute()
              if operation != "validate" else None)
    if folder is not None and target.is_relative_to(folder.resolve()):
        raise ValueError("Receipt must be outside the package folder")
    started = time.monotonic()
    report = {"schema": SCHEMA, "id": str(uuid4()), "module": "beamng",
              "tool": {"name": "cdcrd-civil3d-beamng", "version": __version__},
              "operation": operation, "started_utc": _utc(), "finished_utc": None,
              "duration_seconds": None, "ok": False, "status": "failed",
              "authenticity": "unsigned", "path_base": "receipt_directory",
              "parameters": {key: value for key, value in options.items()
                             if key not in SOURCE_FILES and key not in {"output", "folder"}},
              "files": {"inputs": [], "outputs": []}, "result": None, "errors": [],
              "execution": {"attempted": False, "completed": False},
              "evidence": {"level": "none", "native_operation": "not_checked",
                           "consumer_validation": "not_checked", "attachments": []}}
    inputs = []
    if operation == "verify":
        # Preserve the manifest fingerprint even if its asset references are invalid.
        inputs.append(("manifest", folder / "manifest.json"))
        try:
            inputs = _package_files(folder)
        except KNOWN_ERRORS as error:
            report["errors"].append(_error("package_references", error))
    else:
        inputs = [(key, Path(options[key]).resolve()) for key in SOURCE_FILES
                  if options.get(key) is not None]
    tracked = []
    for identifier, path in inputs:
        item = _track(identifier, path, target.parent, report["errors"])
        report["files"]["inputs"].append(item)
        tracked.append((item, path))
    for index, path in enumerate(evidence):
        path = Path(path).resolve()
        item = _track(f"evidence.{index}", path, target.parent, report["errors"])
        item["assessment"] = "hash_only"
        report["evidence"]["attachments"].append(item)
        tracked.append((item, path))
    if not report["errors"]:
        report["execution"]["attempted"] = True
        try:
            if operation == "validate":
                result = validate_interchange(**options)
                success = result["ok"]
            else:
                manifest = (build_package(**options) if operation == "build"
                            else verify_package(folder))
                result = {key: manifest[key] for key in ("schema", "level_id", "counts", "warnings")}
                success = True
            report["result"] = result
            report["ok"] = success
            report["execution"]["completed"] = True
            if operation == "build":
                if verify_package(folder) != manifest:
                    raise ValueError("Published manifest changed after build")
                for identifier, path in _package_files(folder):
                    item = {"id": identifier, "path": _path(path, target.parent)}
                    item.update(_fingerprint(path))
                    report["files"]["outputs"].append(item)
                    if identifier != "manifest" and item["sha256"] != manifest["sha256s"][identifier]:
                        raise ValueError("Output asset changed after package verification")
            report["evidence"]["level"] = ("source_contract" if operation == "validate"
                                             else "package_file_integrity") if success else "none"
        except KNOWN_ERRORS as error:
            report["errors"].append(_error("operation_failed", error))
    for item, path in tracked:
        _finish(item, path, report["errors"])
    if report["errors"]:
        report["ok"] = False
        report["evidence"]["level"] = "none"
    report["status"] = "succeeded" if report["ok"] else "failed"
    report["finished_utc"] = _utc()
    report["duration_seconds"] = time.monotonic() - started
    _publish(target, report)
    return report
