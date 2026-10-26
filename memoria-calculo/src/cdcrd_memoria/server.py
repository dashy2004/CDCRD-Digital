"""Local MCP stdio interface. Does not register itself or change client configuration."""

from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .compose import prepare
from .contracts import coverage
from .pipeline import generate, inspect, parse_dossier

mcp = FastMCP("cdcrd-memoria")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
RENDER_LIMITER = anyio.CapacityLimiter(1)


@mcp.tool(annotations=READ)
async def memoria_inspeccionar_fuentes(
    expediente: dict, base_directory: str, limits: dict | None = None
) -> dict:
    """Comprueba fuentes locales por SHA-256 y límites; no ejecuta ni modifica sus contenidos."""

    def inspect_in_thread():
        return {"sources": inspect(parse_dossier(expediente), Path(base_directory), limits)}

    return await anyio.to_thread.run_sync(inspect_in_thread)


@mcp.tool(annotations=READ)
def memoria_validar_expediente(expediente: dict) -> dict:
    """Valida contrato y cobertura declarada. No lee archivos ni verifica el cálculo estructural."""
    return {
        "contract_valid": True,
        "source_files_checked": False,
        "coverage": coverage(parse_dossier(expediente)),
    }


@mcp.tool(annotations=READ)
def memoria_preparar(expediente: dict, template_id: str = "structural_concrete_frame_v1") -> dict:
    """Prepara el contenido común de la memoria sin crear archivos ni cambiar valores/ejes."""
    dossier = parse_dossier(expediente)
    if template_id != dossier.project.profile:
        raise ValueError("Plantilla no compatible con el perfil del expediente")
    return prepare(dossier)


@mcp.tool(annotations=WRITE)
async def memoria_generar(
    expediente: dict, output_directory: str, base_directory: str, formats: list[str] | None = None
) -> dict:
    """Crea un paquete NUEVO con memoria y evidencias. Rechaza salida existente o dentro de fuentes.

    HTML/DOCX incluyen índice de anexos; PDF incorpora sus páginas. Conserva INCOMPLETE si falla.
    """

    def generate_in_thread():
        return generate(parse_dossier(expediente), Path(output_directory), Path(base_directory), formats)

    # Keep protocol pings responsive; do not abandon an in-progress package on cancellation.
    return await anyio.to_thread.run_sync(generate_in_thread, limiter=RENDER_LIMITER)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
