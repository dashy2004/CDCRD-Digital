"""Bounded, read-only source inspection and exclusive output directories.

Paths are resolved before access and checked again around output creation. These
guards prevent accidental overlap and ordinary symlink/junction escapes; they
are not a sandbox against an attacker concurrently rewriting the filesystem.
Run the generator in a directory controlled by the operator.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self


class SourceError(ValueError):
    """A source, resource limit or output location is unsafe or inconsistent."""


HARD_LIMITS = {"files": 100, "total_bytes": 512 * 1024 * 1024, "file_bytes": 256 * 1024 * 1024}
ALLOWED_SUFFIXES = {".json", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}
ALLOWED_KINDS = {"snapshot", "table", "document", "figure", "other"}
_ID = re.compile(r"[A-Za-z0-9_-]+\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


def _limits(limits: dict[str, int] | None) -> dict[str, int]:
    result = HARD_LIMITS.copy()
    if limits is None:
        return result
    if not isinstance(limits, dict) or set(limits) - set(result):
        raise SourceError("Unknown source limit; use files, total_bytes and file_bytes")
    for name, value in limits.items():
        if type(value) is not int or not 1 <= value <= HARD_LIMITS[name]:
            raise SourceError(f"{name} must be a positive integer <= {HARD_LIMITS[name]}")
        result[name] = value
    return result


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolve(path: str | Path, base: Path, *, strict: bool = True) -> Path:
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise SourceError("Paths must be nonempty local filesystem paths")
    candidate = Path(path)
    if candidate.drive and not candidate.is_absolute():
        raise SourceError("Drive-relative paths are not supported")
    # NTFS alternate data streams must never be accepted as ordinary files.
    if any(":" in part for part in candidate.parts if part != candidate.anchor):
        raise SourceError("Alternate data streams and URI paths are not supported")
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.resolve(strict=strict)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SourceError(f"Cannot resolve filesystem path: {path}") from exc


def _roots(source_roots: list[str | Path], base: Path) -> list[Path]:
    if not isinstance(source_roots, list):
        raise SourceError("source_roots must be a list of directories")
    result: list[Path] = []
    for item in source_roots:
        root = _resolve(item, base)
        if not root.is_dir():
            raise SourceError(f"Source root is not a directory: {root}")
        if root not in result:
            result.append(root)
    return result


def _signature(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def hash_source(path: Path, max_bytes: int = HARD_LIMITS["file_bytes"]) -> str:
    """Hash a regular file without writing, with an enforced streaming bound."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= HARD_LIMITS["file_bytes"]:
        raise SourceError("Invalid per-file byte limit")
    path = Path(path)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise SourceError(f"Source must be a regular file: {path}")
        if before.st_size > max_bytes:
            raise SourceError(f"Source exceeds the per-file byte limit: {path}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _signature(opened) != _signature(before):
                raise SourceError(f"Source changed while opening: {path}")
            digest = hashlib.sha256()
            count = 0
            while chunk := stream.read(min(1024 * 1024, max_bytes - count + 1)):
                count += len(chunk)
                if count > max_bytes:
                    raise SourceError(f"Source exceeds the per-file byte limit: {path}")
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        if _signature(before) != _signature(after) or _signature(before) != _signature(path.lstat()):
            raise SourceError(f"Source changed while hashing: {path}")
        return digest.hexdigest()
    except OSError as exc:
        raise SourceError(f"Cannot read source: {path}") from exc


def inspect_sources(
    sources: list[dict[str, Any]],
    source_roots: list[str],
    base_directory: Path,
    limits: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Validate declarations and hash sources under explicit read-only roots.

    Caller-supplied limits may only reduce the hard caps. File type is checked
    by extension here; content-specific readers remain responsible for parsing
    safely. No file is executed, unpacked, edited, or opened in an application.
    """
    bounds = _limits(limits)
    if not isinstance(sources, list) or len(sources) > bounds["files"]:
        raise SourceError("Source count exceeds the file limit or is not a list")
    base = _resolve(base_directory, Path.cwd())
    if not base.is_dir():
        raise SourceError("base_directory must be an existing directory")
    roots = _roots(source_roots, base)
    if sources and not roots:
        raise SourceError("Sources require at least one explicit source root")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for source in sources:
        if not isinstance(source, dict):
            raise SourceError("Each source must be an object")
        identifier = source.get("id")
        expected = source.get("sha256")
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise SourceError("Invalid source id")
        if identifier.casefold() in seen:
            raise SourceError(f"Duplicate source id: {identifier}")
        seen.add(identifier.casefold())
        if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            raise SourceError(f"Source requires an expected SHA-256: {identifier}")
        if source.get("kind") not in ALLOWED_KINDS:
            raise SourceError(f"Invalid source kind: {identifier}")
        if not isinstance(source.get("title"), str) or not source["title"].strip():
            raise SourceError(f"Source requires a title: {identifier}")
        path = _resolve(source.get("path"), base)
        if not any(_is_within(path, root) for root in roots):
            raise SourceError(f"Source escapes the declared roots: {identifier}")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise SourceError(f"Unsupported source format: {identifier}")
        try:
            before = path.stat()
        except OSError as exc:
            raise SourceError(f"Cannot stat source: {identifier}") from exc
        if not stat.S_ISREG(before.st_mode):
            raise SourceError(f"Source is not a regular file: {identifier}")
        total += before.st_size
        if total > bounds["total_bytes"]:
            raise SourceError("Sources exceed the total byte limit")
        actual = hash_source(path, bounds["file_bytes"])
        try:
            after = path.stat()
        except OSError as exc:
            raise SourceError(f"Cannot stat source after hashing: {identifier}") from exc
        if _signature(before) != _signature(after):
            raise SourceError(f"Source changed during inspection: {identifier}")
        if actual != expected.lower():
            raise SourceError(f"Source SHA-256 mismatch: {identifier}")
        records.append({
            "id": identifier,
            "path": str(path),
            "sha256": actual,
            "size": after.st_size,
            "kind": source["kind"],
            "title": source["title"],
        })
    return records


def verify_sources(records: list[dict[str, Any]]) -> None:
    """Verify inspected sources again before considering an output complete."""
    if not isinstance(records, list) or len(records) > HARD_LIMITS["files"]:
        raise SourceError("Invalid inspected source records")
    total = 0
    for record in records:
        if not isinstance(record, dict):
            raise SourceError("Invalid inspected source record")
        try:
            path = Path(record["path"])
            expected = record["sha256"]
            size = record["size"]
        except (KeyError, TypeError) as exc:
            raise SourceError("Incomplete inspected source record") from exc
        if not path.is_absolute():
            raise SourceError("Inspected source paths must be absolute")
        if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            raise SourceError("Invalid inspected source hash")
        if type(size) is not int or size < 0:
            raise SourceError("Invalid inspected source size")
        total += size
        if total > HARD_LIMITS["total_bytes"]:
            raise SourceError("Inspected sources exceed the total byte limit")
        actual = hash_source(path)
        try:
            unchanged_size = path.stat().st_size == size
        except OSError as exc:
            raise SourceError(f"Source disappeared after verification: {path}") from exc
        if actual != expected.lower() or not unchanged_size:
            raise SourceError(f"Source changed after inspection: {path}")


@dataclass
class OutputPackage:
    """Create an output directory exclusively, retaining a failure marker.

    Only call ``complete()`` after all artifacts and source checks succeed. An
    existing destination is never reused, including a previous failed package.
    """

    output_directory: Path
    source_roots: list[Path]
    source_paths: list[Path]
    path: Path = field(init=False)
    _entered: bool = field(default=False, init=False)
    _active: bool = field(default=False, init=False)
    _completed: bool = field(default=False, init=False)
    _identity: tuple[int, int] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.path = _resolve(self.output_directory, Path.cwd(), strict=False)

    def _guard(self) -> None:
        candidate = _resolve(self.output_directory, Path.cwd(), strict=False)
        if candidate != self.path:
            raise SourceError("Output path changed after validation")
        roots = _roots(self.source_roots, Path.cwd())
        protected = roots + [_resolve(item, Path.cwd()) for item in self.source_paths]
        for source in protected:
            if _is_within(candidate, source) or _is_within(source, candidate):
                raise SourceError("Output overlaps a source root or source file")

    def __enter__(self) -> Self:
        if self._entered:
            raise SourceError("OutputPackage cannot be entered more than once")
        self._guard()
        # lexists also catches a dangling symlink at the requested destination.
        if os.path.lexists(self.output_directory) or os.path.lexists(self.path):
            raise SourceError("Output directory already exists; choose a new path")
        try:
            self.path.mkdir(parents=True, exist_ok=False)
            self._guard()
            info = self.path.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise SourceError("Output is not a regular directory")
            self._identity = info.st_dev, info.st_ino
            with (self.path / "INCOMPLETE").open("x", encoding="utf-8") as stream:
                stream.write("Generation has not completed; do not treat this package as delivered.\n")
        except OSError as exc:
            raise SourceError("Cannot create an exclusive output package") from exc
        self._entered = True
        self._active = True
        return self

    def _check_identity(self) -> None:
        self._guard()
        try:
            info = self.path.lstat()
        except OSError as exc:
            raise SourceError("Output directory disappeared") from exc
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self._identity:
            raise SourceError("Output directory changed during generation")

    def complete(self) -> None:
        if not self._active or self._completed:
            raise SourceError("Output package is not active or was already completed")
        self._check_identity()
        marker = self.path / "INCOMPLETE"
        try:
            if not stat.S_ISREG(marker.lstat().st_mode):
                raise SourceError("Completion marker is not a regular file")
            marker.unlink()
        except OSError as exc:
            raise SourceError("Cannot complete output package") from exc
        self._completed = True

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self._active = False
        if exc_type is not None and self._completed:
            # A late exception must not leave an apparently completed delivery.
            self._check_identity()
            try:
                with (self.path / "INCOMPLETE").open("x", encoding="utf-8") as stream:
                    stream.write("Generation failed after completion was requested.\n")
            except FileExistsError:
                pass
            self._completed = False
        return False
