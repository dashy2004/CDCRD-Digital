"""CLI explicita de CAD, IFC, PDF y corpus normativo."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .doctor import diagnose
from .files import inspect_pdf, preview_pdf
from .normativa import CHECKS, search, verify


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Herramientas locales AI+BIM+CDCRD")
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Verificar dependencias sin conectar BIM vivo")
    sub.add_parser("mcp", help="Iniciar servidor MCP stdio")
    find = sub.add_parser("buscar", help="Consultar clausulas con pagina y procedencia")
    find.add_argument("query")
    find.add_argument("--repo", type=Path)
    find.add_argument("--volumen", type=int)
    find.add_argument("--limite", type=int, default=5)
    checks = sub.add_parser("verificar", help="Ejecutar verificadores existentes sin COM")
    checks.add_argument("check", choices=list(CHECKS))
    checks.add_argument("source", type=Path)
    checks.add_argument("--repo", type=Path)
    for command in ("generar-dxf", "preview-dxf", "preview-pdf", "validar-ids"):
        operation = sub.add_parser(command)
        operation.add_argument("source", type=Path)
        operation.add_argument("output", type=Path)
        if command == "validar-ids":
            operation.add_argument("--ids", type=Path, required=True)
        if command == "preview-pdf":
            operation.add_argument("--pagina", type=int, default=1)
            operation.add_argument("--dpi", type=int, default=120)
    for command in ("inspeccionar-dxf", "inspeccionar-ifc", "inspeccionar-pdf"):
        operation = sub.add_parser(command)
        operation.add_argument("source", type=Path)
    return cli


def execute(args: argparse.Namespace) -> dict:
    if args.command == "doctor":
        return diagnose()
    if args.command == "buscar":
        return search(args.query, args.repo, args.limite, args.volumen)
    if args.command == "verificar":
        return verify(args.check, args.source, args.repo)
    if args.command == "inspeccionar-pdf":
        return inspect_pdf(args.source)
    if args.command == "preview-pdf":
        return preview_pdf(args.source, args.output, args.pagina, args.dpi)
    if args.command in ("generar-dxf", "preview-dxf", "inspeccionar-dxf"):
        from .cad import generate_plan, inspect_dxf, preview_dxf

        if args.command == "inspeccionar-dxf":
            return inspect_dxf(args.source)
        function = generate_plan if args.command == "generar-dxf" else preview_dxf
        return function(args.source, args.output)
    from .bim import inspect_ifc, validate_ids

    if args.command == "inspeccionar-ifc":
        return inspect_ifc(args.source)
    return validate_ids(args.source, args.ids, args.output)


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows puede usar cp1252; el corpus contiene símbolos Unicode.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    if args.command == "mcp":
        from .server import main as serve

        serve()
        return 0
    try:
        result = execute(args)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "doctor":
        return 0 if result["ok"] else 1
    if args.command == "verificar":
        return result["exit_code"]
    if args.command == "validar-ids":
        return 0 if result["status"] == "passed" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
