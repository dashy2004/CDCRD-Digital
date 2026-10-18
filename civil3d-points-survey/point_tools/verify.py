"""Compare exported native coordinates against a source PENZD CSV."""

import argparse
import json
from pathlib import Path
from .prepare import read_points


def compare(source, actual, tolerance=1e-7):
    a = {p[0]: p for p in source}
    b = {p[0]: p for p in actual}
    missing = sorted(a.keys() - b.keys())
    extra = sorted(b.keys() - a.keys())
    common = a.keys() & b.keys()
    errors = {n: max(abs(x - y) for x, y in zip(a[n][1:4], b[n][1:4])) for n in common}
    descriptions = [n for n in common if a[n][4] != b[n][4]]
    return dict(
        ok=not (
            missing
            or extra
            or descriptions
            or any(e > tolerance for e in errors.values())
        ),
        expected=len(a),
        actual=len(b),
        missing=missing,
        extra=extra,
        changed_descriptions=descriptions,
        max_coordinate_error_m=max(errors.values(), default=0),
        tolerance_m=tolerance,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("actual", type=Path)
    a = p.parse_args()
    result = compare(read_points(a.source), read_points(a.actual))
    print(json.dumps(result, indent=2))
    return int(not result["ok"])


if __name__ == "__main__":
    raise SystemExit(main())
