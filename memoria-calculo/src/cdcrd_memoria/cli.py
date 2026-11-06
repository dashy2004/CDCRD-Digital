"""CLI with machine-readable JSON stdout and nonzero failures on stderr."""

import argparse
import json
import sys
from pathlib import Path

from .adapters import import_etabs_capture
from .compose import prepare
from .contracts import Dossier, coverage
from .pipeline import generate, inspect, load_json, parse_dossier


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generador offline de memorias de diseño")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "validate", "prepare", "render", "import-etabs"):
        command = commands.add_parser(name)
        command.add_argument("expediente", type=Path)
        if name in {"render", "import-etabs"}:
            command.add_argument("--output", type=Path, required=True)
            command.add_argument(
                "--formats", nargs="+", choices=["html", "docx", "pdf"], default=["html", "docx", "pdf"]
            )
        if name == "import-etabs":
            command.add_argument("--source-id", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--output", type=Path, required=True)
    commands.add_parser("schema")
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            result = Dossier.model_json_schema(by_alias=True)
        elif args.command == "demo":
            from .demo import create_demo

            result = create_demo(args.output)
        else:
            path = args.expediente.resolve(strict=True)
            dossier = parse_dossier(load_json(path))
            if args.command == "validate":
                result = {
                    "contract_valid": True,
                    "source_files_checked": False,
                    "coverage": coverage(dossier),
                }
            elif args.command == "inspect":
                result = {"sources": inspect(dossier, path.parent)}
            elif args.command == "prepare":
                result = prepare(dossier)
            else:
                if args.command == "import-etabs":
                    records = inspect(dossier, path.parent)
                    capture = next((r for r in records if r["id"] == args.source_id), None)
                    if capture is None or Path(capture["path"]).suffix.lower() != ".json":
                        raise ValueError("source-id debe identificar una captura JSON registrada")
                    dossier = import_etabs_capture(
                        load_json(Path(capture["path"]), capture["sha256"]), dossier, args.source_id
                    )
                result = generate(dossier, args.output, path.parent, args.formats, input_path=path)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        message = f"Error: {exc}"
        encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
        print(message.encode(encoding, errors="backslashreplace").decode(encoding), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
