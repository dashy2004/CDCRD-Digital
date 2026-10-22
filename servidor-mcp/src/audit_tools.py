"""Offline MCP report writer. Importing this module never connects to CSI."""

from audit_report import write_report


def write_etabs_audit_report(
    profile: str, project: dict, capture: dict, output_directory: str
) -> dict:
    """Genera proyecto/captura JSON, informe JSON/HTML y manifest en directorio NUEVO.

    Reutiliza el auditor existente. No conecta, analiza, guarda ni modifica ETABS.
    El paquete conserva rutas/datos privados: no publicarlo sin revision.
    """
    return write_report(profile, project, capture, output_directory)


def register_audit_tools(mcp):
    mcp.tool()(write_etabs_audit_report)
