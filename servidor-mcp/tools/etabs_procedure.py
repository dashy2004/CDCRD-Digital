"""Offline JSON entry point for the same procedure functions registered in MCP."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from procedure_tools import PROCEDURE_TOOLS


def main():
    tools = {f.__name__: f for f in PROCEDURE_TOOLS}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=sorted(tools))
    parser.add_argument("input", type=Path, help="JSON object of named tool arguments")
    parser.add_argument("--output", type=Path, help="New receipt; existing files are preserved")
    args = parser.parse_args()
    try:
        def invalid_constant(value):
            raise ValueError(f"JSON no finito: {value}")
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"),
                             parse_constant=invalid_constant)
        if not isinstance(payload, dict):
            raise ValueError("La entrada debe ser un objeto JSON")
        result = tools[args.tool](**payload)
        receipt = json.dumps({"ok": True, "tool": args.tool, "result": result},
                             ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(receipt)
        else:
            print(receipt, end="")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
