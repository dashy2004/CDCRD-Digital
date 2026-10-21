"""Command-line entry point; requires no Civil 3D process, AI or MCP server."""

import argparse
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from .package import build_package, verify_package
from .receipts import record_operation
from .validation import validate_interchange


def source_arguments(parser):
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--terrain-landxml", type=Path)
    parser.add_argument("--terrain-surface")
    parser.add_argument("--road-landxml", type=Path)
    parser.add_argument("--road-surface")
    parser.add_argument("--road-guide", type=Path, help="JSON nodes_abs_m [E,N,Z,full width], optional station_m")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build a new interchange folder; existing outputs are refused")
    source_arguments(build)
    build.add_argument("--road-is-drivable", action="store_true", help="Explicitly declare a pavement-only road TIN")
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--level-id", required=True)
    build.add_argument("--size", type=int, help="Power-of-two samples, 128..8192; automatic when omitted")
    build.add_argument("--square-size", type=float, default=1.0, help="Metres per sample, default 1")
    build.add_argument("--margin", type=float, default=2.0, help="Bounding margin in metres, default 2")
    verify = commands.add_parser("verify", help="Validate manifest, safe paths, PNG formats and SHA256 hashes")
    verify.add_argument("folder", type=Path)
    validate = commands.add_parser("validate", help="Check source units, coordinates, IDs and references without building")
    source_arguments(validate)
    for operation in (build, verify, validate):
        operation.add_argument("--receipt", type=Path, help="Save a new unified JSON receipt outside the package")
        operation.add_argument("--evidence", type=Path, action="append", default=[],
                               help="Attach an existing file as hash-only evidence; repeatable")
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    receipt, evidence = args.pop("receipt"), args.pop("evidence")
    if evidence and receipt is None:
        parser.error("--evidence requires --receipt")
    if receipt is not None:
        try:
            report = record_operation(command, receipt, evidence=evidence, **args)
        except (ValueError, OSError) as error:
            parser.exit(2, f"ERROR: {error}\n")
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["ok"] else 1
    if command == "validate":
        report = validate_interchange(**args)
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["ok"] else 1
    try:
        manifest = build_package(**args) if command == "build" else verify_package(args["folder"])
    except (ValueError, OSError, ParseError, DefusedXmlException) as error:
        parser.exit(2, f"ERROR: {error}\n")
    print(json.dumps({"schema": manifest["schema"], "level_id": manifest["level_id"],
                      "counts": manifest["counts"], "warnings": manifest["warnings"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
