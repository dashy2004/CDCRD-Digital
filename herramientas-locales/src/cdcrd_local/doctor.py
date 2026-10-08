"""Diagnostico de paquetes; nunca conecta aplicaciones BIM vivas."""

import importlib
import importlib.metadata
import platform
import sqlite3
import sys

PACKAGES = {
    "ezdxf": "ezdxf",
    "ifcopenshell": "ifcopenshell",
    "ifctester": "ifctester",
    "ifcclash": "ifcclash",
    "matplotlib": "matplotlib",
    "mcp": "mcp.server.fastmcp",
    "pdfplumber": "pdfplumber",
    "pint": "pint",
    "pydantic": "pydantic",
    "pypdfium2": "pypdfium2",
    "shapely": "shapely",
}


def diagnose() -> dict:
    packages = {}
    for name, module in PACKAGES.items():
        try:
            importlib.import_module(module)
            packages[name] = {"ok": True, "version": importlib.metadata.version(name)}
        except (ImportError, OSError, importlib.metadata.PackageNotFoundError) as exc:
            packages[name] = {"ok": False, "error": str(exc)}
    with sqlite3.connect(":memory:") as database:
        try:
            database.execute("CREATE VIRTUAL TABLE diagnostic USING fts5(text)")
            fts5 = True
        except sqlite3.OperationalError:
            fts5 = False
    return {
        "ok": fts5 and all(item["ok"] for item in packages.values()),
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.system(),
        "sqlite_fts5": fts5,
        "packages": packages,
        "live_bim_connected": False,
    }
