"""Verify a native audit of prepare_demo.py; emit only synthetic summary data."""

import argparse
import json
from pathlib import Path
from terrain_tools import profile_at_x, section_areas
from prepare_demo import demo_requests


def require(condition, message):
    if not condition:
        raise ValueError(message)


def interpolate(profile, x):
    for a, b in zip(profile, profile[1:]):
        if a[0] - 1e-7 <= x <= b[0] + 1e-7:
            return a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])
    raise ValueError("Point outside TIN profile")


def verify(receipt, before=None):
    require(receipt.get("ok") is True, "Native command did not succeed")
    a = receipt["result"]
    verify_units(a)
    require(a["cogo"] == [], "Unexpected demo COGO content")
    require(
        len(a["surfaces"]) == 8 and len(a["alignments"]) == 2,
        "Unexpected native object count",
    )
    verify_style_units(a)
    surfaces = {s["name"]: s for s in a["surfaces"]}
    require(all(not s["isOutOfDate"] for s in surfaces.values()), "Stale surface")
    report = {
        "fixture": "synthetic, local coordinates in meters",
        "checks": [],
        "section_count": 0,
        "sample_line_count": 0,
        "view_count": 0,
        "max_section_elevation_error_m": 0.0,
    }
    expected = demo_requests("unused", "unused")
    for label in ["flat", "sloped"]:
        request = expected["build-" + label]
        base = request["baseSurface"]
        alignment = next(
            x
            for x in a["alignments"]
            if x["name"] == "CDCRD_DEMO_AXIS_" + label.upper()
        )
        lines = alignment["groups"][0]["lines"]
        require(len(lines) == 97, "Expected 0.25 m sample interval over 24 m")
        rows = {m["name"]: [] for m in request["meshes"]}
        for line in lines:
            report["sample_line_count"] += 1
            report["view_count"] += len(line["views"])
            profiles = {}
            for section in line["sections"]:
                report["section_count"] += 1
                require(section["updateMode"] == "Dynamic", "Non-dynamic section")
                pts = section["points"]
                require(
                    all(
                        p["segmentTo"] == (i + 1 if i < len(pts) - 1 else -1)
                        for i, p in enumerate(pts)
                    ),
                    "Disconnected native section",
                )
                profile = sorted((p["location"][0], p["location"][1]) for p in pts)
                profiles[section["source"]] = profile
                tin = profile_at_x(
                    surfaces[section["source"]]["triangles"], -12 + line["station"]
                )
                for offset, z in profile:
                    error = abs(
                        z - interpolate(tin, -offset)
                    )  # Right offset is south on eastbound axis.
                    report["max_section_elevation_error_m"] = max(
                        report["max_section_elevation_error_m"], error
                    )
            for mesh in request["meshes"]:
                rows[mesh["name"]].append(
                    (
                        line["station"],
                        section_areas(profiles[base], profiles[mesh["name"]], -9, 9),
                    )
                )
        for mesh in request["meshes"]:
            v = surfaces[mesh["name"] + "_VOLUME"]["volume"]
            require(v["cutFactor"] == v["fillFactor"] == 1, "Unexpected volume factors")
            samples = rows[mesh["name"]]
            aea = {
                part: sum(
                    (b[0] - a[0]) * (a[1][part + "_m2"] + b[1][part + "_m2"]) / 2
                    for a, b in zip(samples, samples[1:])
                )
                for part in ["cut", "fill"]
            }
            errors = {
                part: abs(v[part] - mesh["expected"][part + "_m3"])
                for part in ["cut", "fill"]
            }
            require(max(errors.values()) <= 0.0001, "Native TIN volume mismatch")
            for part in ["cut", "fill"]:
                require(
                    abs(aea[part] - v[part]) <= max(0.0001, 0.01 * v[part]),
                    "Section volume error exceeds 1%",
                )
            report["checks"].append(
                {
                    "surface": mesh["name"],
                    "cut_m3": v["cut"],
                    "fill_m3": v["fill"],
                    "independent_expected": {
                        p + "_m3": mesh["expected"][p + "_m3"] for p in ["cut", "fill"]
                    },
                    "absolute_error_m3": errors,
                    "native_sections_aea_m3": aea,
                    "pass": True,
                }
            )
    require(
        report["max_section_elevation_error_m"] <= 1e-6,
        "Section elevations differ from TIN",
    )
    if before:
        require(before.get("ok") is True, "Invalid before audit")
        verify_units(before["result"])
        verify_style_units(before["result"])
        for key in ["cogo", "surfaces", "alignments", "sectionViewStyles"]:
            require(
                before["result"][key] == a[key], "Native persistence mismatch: " + key
            )
        report["native_data_unchanged_since_before_audit"] = True
    return report


def verify_units(a):
    """Require both native settings; old INSUNITS-only receipts cannot prove this."""
    require(
        a.get("units") == "Meters"
        and a.get("civilUnits") == "Meters"
        and a.get("metricDrawingUnits") is True,
        "Both AutoCAD INSUNITS and Civil DrawingUnits must be verified as Meters",
    )


def verify_style_units(a):
    styles = a.get("sectionViewStyles", [])
    require(len(styles) == 2, "Expected two audited section graph styles")
    for style in styles:
        axes = style.get("axes", [])
        require(len(axes) == 5, "Incomplete section axis audit")
        for axis in axes:
            for tick in ("major", "minor"):
                text = axis.get(tick, "")
                require(
                    text.startswith("<[Section View Point ")
                    and "(Um|" in text and "Uft" not in text and text.endswith("> m"),
                    "Section tick is not explicitly metric",
                )
            require(axis.get("title", "").endswith("(m)"), "Axis title lacks meters")
        title = style.get("title", "")
        require(
            title.startswith("<[Section View Station(Um|")
            and "Uft" not in title and title.endswith("> m"),
            "Section station title is not explicitly metric",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(
        json.loads(args.audit.read_text(encoding="utf-8-sig")),
        (
            json.loads(args.before.read_text(encoding="utf-8-sig"))
            if args.before
            else None
        ),
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        "PASS:",
        len(result["checks"]),
        "surfaces;",
        result["section_count"],
        "native sections",
    )


if __name__ == "__main__":
    main()
