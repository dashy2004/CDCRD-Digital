"""Validate PENZD data and prepare a bounded Civil 3D COM/AutoLISP request.

Never executes CAD commands. Coordinates are metres, no CRS conversion is made.
"""

import argparse
import csv
import json
import math
import re
from pathlib import Path, PureWindowsPath

HEADER = ["number", "easting", "northing", "elevation", "description"]
ACTIONS = {"audit", "import", "group", "survey-import", "survey-read"}


def safe_text(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError("Text must not contain control characters")
    return value


def read_points(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != HEADER:
            raise ValueError("Required CSV order: " + ",".join(HEADER))
        points, numbers = [], set()
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed CSV row")
            if not re.fullmatch(r"[1-9][0-9]*", row["number"]):
                raise ValueError("Point numbers must be positive integers")
            n = int(row["number"])
            if n > 2147483647 or n in numbers:
                raise ValueError("Duplicate/out-of-range point number")
            xyz = [float(row[k]) for k in HEADER[1:4]]
            if not all(math.isfinite(v) and abs(v) < 1e9 for v in xyz):
                raise ValueError("Invalid coordinate")
            points.append([n, *xyz, safe_text(row["description"])])
            numbers.add(n)
    if not points or len(points) > 10000:
        raise ValueError("Expected 1..10000 points per request")
    return points


def windows_path(value):
    safe_text(value)
    p = PureWindowsPath(value)
    if not p.is_absolute() or ".." in p.parts:
        raise ValueError("An absolute Windows path without .. is required")
    return p.as_posix()


def lisp(value):
    if isinstance(value, str):
        return json.dumps(safe_text(value), ensure_ascii=False)
    if isinstance(value, list):
        return "(" + " ".join(lisp(v) for v in value) + ")"
    if type(value) in (int, float) and math.isfinite(value):
        return repr(value)
    raise ValueError("Unsupported Lisp data")


def prepare(config, points, backend_path):
    action = config["action"]
    if action not in ACTIONS:
        raise ValueError("Unknown action")
    count = config["expected_count"]
    if type(count) is not int or count < 0:
        raise ValueError("expected_count must be a non-negative integer")
    name = config.get("name", "")
    if action != "audit" and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Use a unique simple name, up to 64 characters")
    if action != "audit" and not points:
        raise ValueError("Points required")
    numbers = set()
    for p in points:
        if (
            len(p) != 5
            or type(p[0]) is not int
            or not 0 < p[0] <= 2147483647
            or p[0] in numbers
        ):
            raise ValueError("Invalid or duplicate point number")
        if not all(
            type(v) in (int, float) and math.isfinite(v) and abs(v) < 1e9
            for v in p[1:4]
        ):
            raise ValueError("Invalid coordinate")
        safe_text(p[4])
        numbers.add(p[0])
    if len(points) > 10000:
        raise ValueError("Too many points")
    if action.startswith("survey") and any(p[4] != p[4].strip() for p in points):
        raise ValueError(
            "Survey trims descriptions; normalize explicitly before import"
        )
    if action == "import" and count != 0:
        raise ValueError("Import is restricted to an empty disposable drawing")
    values = [
        action,
        windows_path(config["drawing"]),
        count,
        windows_path(config["output"]),
        name,
        points,
        windows_path(config["survey_folder"]) if action.startswith("survey") else "",
        safe_text(config.get("zone", "")),
    ]
    return (
        "(load "
        + lisp(windows_path(backend_path))
        + ")\n(cdr:run "
        + " ".join("'" + lisp(v) if isinstance(v, list) else lisp(v) for v in values)
        + ")\n(princ)\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--points", type=Path)
    parser.add_argument(
        "--backend",
        required=True,
        help="Absolute Windows path to native/points-survey.lsp",
    )
    parser.add_argument("--runner", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    points = read_points(args.points) if args.points else []
    source = prepare(config, points, args.backend)
    with args.runner.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(source)
    print("Prepared only; inspect and load the runner in the exact drawing copy.")


if __name__ == "__main__":
    main()
