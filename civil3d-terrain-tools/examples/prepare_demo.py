"""Generate synthetic API requests; never reads a client drawing or survey."""

import argparse
import json
from pathlib import Path, PureWindowsPath
from terrain_tools import Platform, prepare_platform


def demo_requests(drawing, receipts):
    common = dict(
        expectedDrawing=drawing,
        outputDirectory=receipts,
        namePrefix="CDCRD_DEMO_",
        expectedCogoCount=0,
        volumeTolerance=0.0001,
    )
    flat = [[-12, -9, 10], [12, -9, 10], [12, 9, 10], [-12, 9, 10]]
    slope = [[x, y, z + 0.05 * x] for x, y, z in flat]
    faces = [[0, 1, 2], [0, 2, 3]]
    cases = []
    for name, z, ratio, base in [
        ("CUT", 8, 1.5, flat),
        ("FILL", 12, 1.5, flat),
        ("MIXED", 10, 2, slope),
    ]:
        mesh = prepare_platform(
            [[base[i] for i in f] for f in faces],
            Platform(0, 0, 12, 6, z, ratio, 24, 18),
        )
        mesh.update(
            name="CDCRD_DEMO_" + name, colorAci={"CUT": 1, "FILL": 5, "MIXED": 3}[name]
        )
        cases.append(mesh)
    requests = {}
    for label, vertices, meshes in [
        ("flat", flat, cases[:2]),
        ("sloped", slope, cases[2:]),
    ]:
        base_name = "CDCRD_DEMO_BASE_" + label.upper()
        requests["build-" + label] = dict(
            common,
            action="build",
            runId="demo-" + label,
            baseSurface=base_name,
            baseMesh=dict(name=base_name, vertices=vertices, faces=faces, colorAci=8),
            meshes=meshes,
            expectedBaseTriangleCount=2,
            baseCheckPoints=vertices,
        )
        requests["sections-" + label] = dict(
            common,
            action="sections",
            runId="demo-" + label,
            sections=dict(
                alignmentName="CDCRD_DEMO_AXIS_" + label.upper(),
                groupName="CDCRD_DEMO_SECTIONS_" + label.upper(),
                start=[-12, 0, 0],
                end=[12, 0, 0],
                halfWidth=9,
                spacing=0.25,
                viewEvery=16,
                viewOrigin=[-20, -40 if label == "flat" else -100, 0],
                elevationRange=[7, 13] if label == "flat" else [9, 11],
                surfaces=[base_name] + [m["name"] for m in meshes],
            ),
        )
    requests["audit"] = dict(common, action="audit", runId="demo-audit")
    return requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drawing", required=True, help="Absolute Windows path to an EMPTY meter DWG"
    )
    parser.add_argument(
        "--receipts", required=True, help="Absolute Windows output directory"
    )
    parser.add_argument(
        "--requests",
        type=Path,
        required=True,
        help="Directory for generated request files",
    )
    args = parser.parse_args()
    if not all(PureWindowsPath(p).is_absolute() for p in [args.drawing, args.receipts]):
        parser.error("Drawing and receipts must be absolute Windows paths")
    args.requests.mkdir(parents=True, exist_ok=True)
    for name, request in demo_requests(args.drawing, args.receipts).items():
        path = args.requests / (name + ".json")
        if path.exists():
            parser.error("Refusing to overwrite " + str(path))
        path.write_text(json.dumps(request, indent=2), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
