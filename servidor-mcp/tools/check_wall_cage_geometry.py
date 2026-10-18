"""Read-only check of a native bar-cage JSON; all geometric inputs are explicit."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from wall_cage_geometry import WallPlan, audit_bars, elevation_spacing, native_bars


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--start", nargs=2, type=float, required=True)
    parser.add_argument("--end", nargs=2, type=float, required=True)
    parser.add_argument("--thickness-mm", type=float, required=True)
    parser.add_argument("--required-cover-mm", type=float, required=True)
    parser.add_argument("--maximum-spacing-mm", type=float)
    args = parser.parse_args()
    if args.capture.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Capture exceeds 32 MiB budget")
    raw = args.capture.read_bytes()
    bars = native_bars(json.loads(raw))
    wall = WallPlan(tuple(args.start), tuple(args.end), args.thickness_mm)
    result = audit_bars(bars, wall, args.required_cover_mm)
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    result["input_units"] = "mm_declared_by_caller_not_inferred"
    if args.maximum_spacing_mm is not None:
        result["elevation_spacing"] = elevation_spacing(bars, args.maximum_spacing_mm)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
