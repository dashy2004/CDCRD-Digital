"""Shared source inventory and offline ecosystem diagnostics.

Source files and configuration are evidence of their own presence, never proof
that an application is installed, connected, or that a project was validated.
"""
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .doctor import diagnose
from .io import repository

MAX_METADATA_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Module:
    id: str
    module: str
    description: str
    operations: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    units: str
    application: str | None
    entrypoints: tuple[str, ...]
    documentation: str
    evidence: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()


# Curated module-level contracts, not a claim to enumerate every API method.
MODULES = (
    Module("local", "herramientas-locales", "Archivos CAD, IFC, IDS y PDF", "read_write",
           ("JSON 2D", "DXF", "IFC", "IDS", "PDF"), ("DXF", "PNG/SVG/PDF", "JSON", "HTML"),
           "Declaradas por entrada; no inferidas", None,
           ("herramientas-locales/src/cdcrd_local/cli.py",),
           "herramientas-locales/README.md", ("herramientas-locales/VERIFICACION.md",),
           ("cdcrd-local",)),
    Module("normativa", "datos", "Consulta normativa con procedencia", "read",
           ("consulta", "clausulas JSON"), ("clausula, volumen, pagina y fuente",),
           "Las de la fuente citada", None, ("datos/INDICE.md",), "datos/INDICE.md",
           ("docs/PROTECCION-NORMATIVA.md",)),
    Module("revit", "revit-mcp-tools", "Modelado y documentacion Revit", "read_write",
           ("parametros JSON", "modelo Revit"), ("modelo", "inventario", "planos", "proyecto.json"),
           "Contrato de cada herramienta; unidades internas Revit", "Revit",
           ("revit-mcp-tools/src/server.py",), "revit-mcp-tools/README.md",
           ("revit-mcp-tools/MEP.md",), ("revit-tools",)),
    Module("revit-write", "revit-mcp-write", "Lectura y pushbuttons Revit", "read_write",
           ("parametros JSON", "modelo Revit"), ("inventario", "resultado de operacion"),
           "Contrato de cada pushbutton", "Revit", ("revit-mcp-write/src/server.py",),
           "revit-mcp-write/README.md", mcp_servers=("revit-write",)),
    Module("etabs", "servidor-mcp", "OAPI ETABS y procedimiento estructural", "read_write",
           ("parametros JSON", "modelo ETABS"), ("modelo", "resultados", "tablas"),
           "Unidades explicitas de la herramienta y modelo", "ETABS",
           ("servidor-mcp/src/server.py",), "servidor-mcp/README.md",
           ("servidor-mcp/docs/VALIDACION-ETABS.md",), ("fea",)),
    Module("safe", "servidor-mcp-safe", "OAPI SAFE para losas y cimentaciones", "read_write",
           ("parametros JSON", "modelo SAFE"), ("modelo", "tablas", "resultados"),
           "Unidades explicitas de la herramienta y modelo", "SAFE",
           ("servidor-mcp-safe/src/server.py",), "servidor-mcp-safe/README.md",
           mcp_servers=("safe",)),
    Module("civil3d", "servidor-mcp-civil3d", "Superficies, ejes y corredores", "read_write",
           ("parametros JSON", "DWG"), ("DWG", "recibos JSON", "capturas"),
           "Comprobar unidades Civil y DWG por separado", "Civil 3D",
           ("servidor-mcp-civil3d/src/server.py",), "servidor-mcp-civil3d/README.md",
           ("servidor-mcp-civil3d/docs/CALZADA-0516.md",), ("civil3d",)),
    Module("autocad", "servidor-mcp-civil3d/puente-autocad", "Operaciones base AutoCAD",
           "read_write", ("parametros JSON", "DWG"), ("DWG", "recibos JSON"),
           "Unidades declaradas del dibujo", "AutoCAD",
           ("servidor-mcp-civil3d/puente-autocad/Cdcrd.AutoCadBridge.csproj",),
           "servidor-mcp-civil3d/docs/AUTOCAD-0511.md",
           ("servidor-mcp-civil3d/docs/AUTOCAD-0511.md",)),
    Module("terrain", "civil3d-terrain-tools", "Terreno, taludes y secciones", "read_write",
           ("parametros", "superficies TIN"), ("TIN", "volumenes", "secciones"),
           "Contrato metrico y comprobaciones del modulo", "Civil 3D",
           ("civil3d-terrain-tools/plugin/TerrainTools.csproj",),
           "civil3d-terrain-tools/README.md", ("civil3d-terrain-tools/docs/VALIDACION.md",)),
    Module("points-survey", "civil3d-points-survey", "Preparacion y verificacion COGO/Survey",
           "read_write", ("puntos", "recibos"), ("paquete de importacion", "comparacion JSON"),
           "Coordenadas y unidades declaradas", "Civil 3D",
           ("civil3d-points-survey/point_tools/prepare.py",), "civil3d-points-survey/README.md",
           ("civil3d-points-survey/docs/VALIDACION.md",)),
    Module("beamng", "civil3d-beamng", "Terreno y carretera hacia BeamNG", "read_write",
           ("snapshot Civil 3D", "LandXML"),
           ("paquete BeamNG", "malla", "heightmap", "validacion JSON", "recibo JSON"),
           "Metros; origen y ejes declarados en manifest", "Civil 3D / BeamNG",
           ("civil3d-beamng/cdcrd_beamng/__main__.py",
            "civil3d-beamng/cdcrd_beamng/validation.py",
            "civil3d-beamng/cdcrd_beamng/receipts.py"), "civil3d-beamng/README.md",
           ("civil3d-beamng/docs/VALIDACION-INTERCAMBIOS.md",
            "civil3d-beamng/docs/RECIBOS.md")),
    Module("losas", "puente-losas", "Intercambio de losas Revit, FEM y ETABS", "read_write",
           ("datos de losas", "parametros de calculo"), ("informe", "Excel", "plan ETABS"),
           "Contrato explicito del puente de losas", "Revit / ETABS",
           ("puente-losas/src/puente_losas/cli.py",), "puente-losas/README.md"),
)


def _file(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    return candidate if candidate.is_relative_to(root) and candidate.is_file() else None


def _version(root: Path, module: Module) -> tuple[str | None, str]:
    path = _file(root, f"{module.module}/pyproject.toml")
    if path is None:
        return None, "not_declared"
    try:
        if path.stat().st_size > MAX_METADATA_BYTES:
            return None, "invalid"
        metadata = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        value = metadata.get("project", {}).get("version")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, AttributeError):
        return None, "invalid"
    if value is None:
        return None, "not_declared"
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        return None, "invalid"
    return value, "source_metadata"


def catalog(repo: Path | None = None, module: str | None = None) -> dict:
    """Return module contracts and source presence; never import connector code."""
    root = repository(repo)
    selected = [entry for entry in MODULES if module is None or entry.id == module]
    if not selected:
        raise ValueError(f"Modulo desconocido: {module}")
    result = []
    for entry in selected:
        files = [{"path": p, "present": _file(root, p) is not None} for p in entry.entrypoints]
        version, version_status = _version(root, entry)
        result.append({
            "id": entry.id, "module": entry.module, "description": entry.description,
            "operations": entry.operations, "inputs": list(entry.inputs),
            "outputs": list(entry.outputs), "units": entry.units,
            "requires_application": entry.application, "entrypoints": files,
            "documentation": entry.documentation,
            "documentation_present": _file(root, entry.documentation) is not None,
            "evidence": [{"path": p, "present": _file(root, p) is not None}
                         for p in entry.evidence],
            "mcp_servers": list(entry.mcp_servers), "version": version,
            "version_status": version_status,
            "source_available": all(item["present"] for item in files),
        })
    return {"schema": "cdcrd.capabilities/1", "modules": result}


def _configuration(path: Path) -> dict:
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("La configuracion excede 1 MiB.")
    if path.suffix.lower() not in {".json", ".toml"}:
        raise ValueError("La configuracion debe ser JSON o TOML.")
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text) if path.suffix.lower() == ".json" else tomllib.loads(text)
    except (UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("La configuracion JSON/TOML no es valida.") from exc
    if not isinstance(data, dict):
        raise ValueError("La configuracion debe ser un objeto.")
    keys = [key for key in ("mcpServers", "mcp_servers") if key in data]
    if len(keys) != 1 or not isinstance(data[keys[0]], dict):
        raise ValueError("Indique un unico objeto mcpServers o mcp_servers.")
    return data[keys[0]]


def _server_state(servers: dict, names: list[str]) -> tuple[bool, bool]:
    invalid = False
    for name in names:
        if name not in servers:
            continue
        entry = servers[name]
        if not isinstance(entry, dict):
            invalid = True
            continue
        if entry.get("disabled") is True or entry.get("enabled") is False:
            continue
        command = entry.get("command")
        url = entry.get("url")
        command_ok = isinstance(command, str) and bool(command.strip())
        url_ok = isinstance(url, str) and bool(url.strip())
        args = entry.get("args", [])
        args_ok = isinstance(args, list) and all(isinstance(arg, str) for arg in args)
        if (command_ok and args_ok) or url_ok:
            return True, invalid
        invalid = True
    return False, invalid


def diagnose_ecosystem(repo: Path | None = None, module: str | None = None,
                       config: Path | None = None) -> dict:
    """Reuse package diagnostics; inspect only an explicitly supplied configuration.

    No subprocess, network, application activation, or global config discovery.
    Commands, arguments, URLs, environment values and config paths are not emitted.
    """
    inventory = catalog(repo, module)
    servers = _configuration(Path(config)) if config is not None else None
    environment = diagnose()
    for item in inventory["modules"]:
        configured, invalid = None, False
        if servers is not None and item["mcp_servers"]:
            configured, invalid = _server_state(servers, item["mcp_servers"])
        item.update(installed=None, configured=configured, configuration_invalid=invalid,
                    live_connection="not_checked")
    return {
        "schema": "cdcrd.ecosystem-state/1",
        "ok": environment["ok"] and all(
            m["source_available"] and m["configured"] is not False
            and not m["configuration_invalid"] for m in inventory["modules"]
        ),
        "scope": "offline; source presence and declared configuration are not live validation",
        "configuration_checked": config is not None, "environment": environment,
        "environment_scope": "herramientas-locales Python environment only",
        "modules": inventory["modules"], "live_bim_connected": False,
    }
