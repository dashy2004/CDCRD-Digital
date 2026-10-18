"""Check the pinned normative snapshot; hash identity is not technical approval.

Text uses LF normalization for Windows/Linux portability. Does not rewrite files.
"""

import argparse
import hashlib
import json
from pathlib import Path

ROOTS = ("datos", "md", "corpus-reglamentos/data", "verificacion-vols")
EXTRA = ("corpus-reglamentos/sources.json",)


def digest(path):
    data = path.read_bytes()
    if path.suffix in (".json", ".md", ".txt", ".csv"):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    files = [p for name in ROOTS for p in (root / name).rglob("*") if p.is_file()]
    files += [root / name for name in EXTRA if (root / name).is_file()]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(files)}


def verify(root, manifest):
    actual = inventory(root)
    expected = manifest["files"]
    return {
        "added": sorted(actual.keys() - expected.keys()),
        "removed": sorted(expected.keys() - actual.keys()),
        "changed": sorted(
            p for p in actual.keys() & expected.keys() if actual[p] != expected[p]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest = json.loads(
        (args.manifest or args.root / "normativa-lock.json").read_text(encoding="utf-8")
    )
    result = verify(args.root, manifest)
    print(
        json.dumps(
            {
                "ok": not any(result.values()),
                "file_count": len(manifest["files"]),
                **result,
            },
            indent=2,
        )
    )
    return int(any(result.values()))


if __name__ == "__main__":
    raise SystemExit(main())
