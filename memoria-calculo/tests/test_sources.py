"""Safety regressions using synthetic temporary files only."""

import hashlib
import os
from pathlib import Path

import pytest

from cdcrd_memoria.sources import (
    HARD_LIMITS,
    OutputPackage,
    SourceError,
    hash_source,
    inspect_sources,
    verify_sources,
)


def declaration(path: str, data: bytes = b"synthetic", **kwargs):
    return {"id": "S-001", "path": path, "sha256": hashlib.sha256(data).hexdigest(),
            "kind": "document", "title": "Synthetic source", **kwargs}


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "inputs"
    root.mkdir()
    path = root / "source.txt"
    path.write_bytes(b"synthetic")
    return root, path


def test_inspection_preserves_bytes_and_mtime(source, tmp_path):
    _, path = source
    before = path.stat().st_mtime_ns
    records = inspect_sources([declaration("inputs/source.txt")], ["inputs"], tmp_path)
    assert records == [{**declaration(str(path.resolve())), "size": 9}]
    verify_sources(records)
    assert path.read_bytes() == b"synthetic"
    assert path.stat().st_mtime_ns == before


def test_empty_sources_are_valid_without_roots(tmp_path):
    assert inspect_sources([], [], tmp_path) == []


@pytest.mark.parametrize("path", ["../outside.txt", "outside.txt"])
def test_paths_outside_roots_rejected(source, tmp_path, path):
    root, _ = source
    outside = (tmp_path / path).resolve()
    outside.write_bytes(b"synthetic")
    with pytest.raises(SourceError, match="escapes"):
        inspect_sources([declaration(str(outside))], [str(root)], tmp_path)


def test_missing_root_and_file_root_rejected(source, tmp_path):
    root, path = source
    with pytest.raises(SourceError, match="explicit source root"):
        inspect_sources([declaration(str(path))], [], tmp_path)
    with pytest.raises(SourceError, match="not a directory"):
        inspect_sources([declaration(str(path))], [str(path)], tmp_path)
    with pytest.raises(SourceError, match="resolve"):
        inspect_sources([], [str(root / "missing")], tmp_path)


def test_hash_mismatch_and_later_change_rejected(source, tmp_path):
    root, path = source
    with pytest.raises(SourceError, match="mismatch"):
        inspect_sources([declaration(str(path), b"different")], [str(root)], tmp_path)
    records = inspect_sources([declaration(str(path))], [str(root)], tmp_path)
    path.write_bytes(b"different")
    with pytest.raises(SourceError, match="changed"):
        verify_sources(records)


def test_source_disappearing_rejected(source, tmp_path):
    root, path = source
    records = inspect_sources([declaration(str(path))], [str(root)], tmp_path)
    path.unlink()
    with pytest.raises(SourceError, match="Cannot read"):
        verify_sources(records)


@pytest.mark.parametrize("limits", [
    {"files": HARD_LIMITS["files"] + 1}, {"total_bytes": HARD_LIMITS["total_bytes"] + 1},
    {"file_bytes": HARD_LIMITS["file_bytes"] + 1}, {"files": True}, {"file_bytes": 0},
    {"files": 1.0}, {"unknown": 10},
])
def test_limit_escalation_and_invalid_limits_rejected(tmp_path, limits):
    with pytest.raises(SourceError):
        inspect_sources([], [], tmp_path, limits)


def test_size_and_count_limits_enforced(source, tmp_path):
    root, path = source
    specs = [declaration(str(path)), declaration(str(path), id="S-002")]
    for limits, message in [({"files": 1}, "file limit"),
                            ({"file_bytes": 8}, "per-file"),
                            ({"total_bytes": 17}, "total byte")]:
        with pytest.raises(SourceError, match=message):
            inspect_sources(specs, [str(root)], tmp_path, limits)


@pytest.mark.parametrize("updates", [
    {"id": "../unsafe"}, {"sha256": "none"}, {"kind": "macro"}, {"title": ""},
])
def test_invalid_declarations_rejected(source, tmp_path, updates):
    root, path = source
    with pytest.raises(SourceError):
        inspect_sources([declaration(str(path), **updates)], [str(root)], tmp_path)


def test_case_insensitive_duplicate_ids_rejected(source, tmp_path):
    root, path = source
    with pytest.raises(SourceError, match="Duplicate"):
        inspect_sources([declaration(str(path)), declaration(str(path), id="s-001")],
                        [str(root)], tmp_path)


@pytest.mark.parametrize("suffix", [".docm", ".zip", ".xlsx", ".exe", ".py"])
def test_unsupported_formats_not_opened(source, tmp_path, suffix):
    root, _ = source
    path = root / ("unsafe" + suffix)
    path.write_bytes(b"synthetic")
    with pytest.raises(SourceError, match="Unsupported"):
        inspect_sources([declaration(str(path))], [str(root)], tmp_path)


def symlink_or_skip(link: Path, target: Path, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink capability unavailable: {exc}")


def test_symlink_escape_rejected(source, tmp_path):
    root, _ = source
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"synthetic")
    link = root / "linked.txt"
    symlink_or_skip(link, outside)
    with pytest.raises(SourceError, match="escapes"):
        inspect_sources([declaration(str(link))], [str(root)], tmp_path)


def test_source_root_alias_protects_real_directory(source, tmp_path):
    root, path = source
    alias = tmp_path / "alias"
    symlink_or_skip(alias, root, directory=True)
    records = inspect_sources([declaration(str(alias / path.name))], [str(alias)], tmp_path)
    assert records[0]["path"] == str(path.resolve())
    with pytest.raises(SourceError, match="overlaps"), OutputPackage(root / "generated", [alias], [path]):
        pass


def test_output_alias_into_sources_rejected(source, tmp_path):
    root, path = source
    alias = tmp_path / "output_alias"
    symlink_or_skip(alias, root, directory=True)
    with pytest.raises(SourceError, match="overlaps"), OutputPackage(alias / "generated", [root], [path]):
        pass
    assert not (root / "generated").exists()


@pytest.mark.parametrize("location", ["root", "inside", "ancestor", "file"])
def test_output_overlap_rejected_without_creating_files(source, tmp_path, location):
    root, path = source
    destination = {"root": root, "inside": root / "nested" / "generated",
                   "ancestor": tmp_path, "file": path}[location]
    with pytest.raises(SourceError, match="overlaps"), OutputPackage(destination, [root], [path]):
        pass
    assert sorted(item.name for item in root.iterdir()) == ["source.txt"]


def test_existing_output_is_never_reused(source, tmp_path):
    root, path = source
    destination = tmp_path / "out"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(SourceError, match="already exists"), OutputPackage(destination, [root], [path]):
        pass
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (destination / "INCOMPLETE").exists()


def test_incomplete_marker_removed_only_on_explicit_success(source, tmp_path):
    root, path = source
    with OutputPackage(tmp_path / "parent" / "out", [root], [path]) as package:
        assert (package.path / "INCOMPLETE").is_file()
        (package.path / "report.txt").write_text("synthetic", encoding="utf-8")
        package.complete()
    assert not (package.path / "INCOMPLETE").exists()
    assert path.read_bytes() == b"synthetic"


def test_normal_exit_without_complete_retains_marker(source, tmp_path):
    root, path = source
    with OutputPackage(tmp_path / "out", [root], [path]) as package:
        pass
    assert (package.path / "INCOMPLETE").is_file()
    with pytest.raises(SourceError, match="not active"):
        package.complete()


@pytest.mark.parametrize("complete_first", [False, True])
def test_exception_retains_failure_marker(source, tmp_path, complete_first):
    root, path = source
    with (
        pytest.raises(RuntimeError, match="render failed"),
        OutputPackage(tmp_path / "out", [root], [path]) as package,
    ):
        if complete_first:
            package.complete()
        raise RuntimeError("render failed")
    assert (package.path / "INCOMPLETE").is_file()


def test_hash_refuses_directory_or_symlink(source, tmp_path):
    root, path = source
    with pytest.raises(SourceError, match="regular file"):
        hash_source(root)
    link = tmp_path / "link.txt"
    symlink_or_skip(link, path)
    with pytest.raises(SourceError, match="regular file"):
        hash_source(link)


def test_hash_detects_file_changed_during_read(source, monkeypatch):
    _, path = source
    original_fstat = os.fstat
    calls = 0

    def changed_fstat(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"changed source")
        return original_fstat(fd)

    monkeypatch.setattr(os, "fstat", changed_fstat)
    with pytest.raises(SourceError, match="changed while hashing"):
        hash_source(path)


def test_complete_requires_active_context(tmp_path):
    package = OutputPackage(tmp_path / "out", [], [])
    with pytest.raises(SourceError, match="not active"):
        package.complete()
