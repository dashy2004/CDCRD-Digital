"""CLI: capture a pinned ETABS instance, or report on an existing JSON offline."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audit_report import validate_reference, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "report"))
    parser.add_argument("--project", required=True, help="JSON con profile y project")
    parser.add_argument("--output", required=True, help="Directorio absoluto nuevo")
    parser.add_argument("--snapshot", help="JSON capturado; requerido para report")
    parser.add_argument(
        "--pid", type=int, help="PID ETABS existente; requerido para capture"
    )
    parser.add_argument("--modal-case", default="")
    parser.add_argument("--max-objects", type=int, default=10000)
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.project).read_text(encoding="utf-8-sig"))
        if args.action == "capture":
            if not args.pid or args.pid <= 0 or args.snapshot:
                parser.error("capture requiere --pid positivo y no admite --snapshot")
            if Path(args.output).exists() or not Path(args.output).is_absolute():
                raise ValueError("--output debe ser directorio absoluto nuevo")
            # Validate the reference BEFORE connecting to the application.
            validate_reference(payload["profile"], payload["project"])
            from Etabs import Etabs

            capture = Etabs(
                process_id=args.pid, auto_start=False
            ).capture_etabs_audit_snapshot(
                payload["project"]["model_path"], args.modal_case, args.max_objects
            )
        else:
            if not args.snapshot or args.pid:
                parser.error("report requiere --snapshot y no admite --pid")
            capture = json.loads(Path(args.snapshot).read_text(encoding="utf-8-sig"))
        result = write_report(
            payload["profile"], payload["project"], capture, args.output
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
