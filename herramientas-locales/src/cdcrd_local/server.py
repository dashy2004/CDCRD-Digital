"""Servidor MCP stdio local con rutas de entrada limitadas al repo."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .cad import generate_plan, inspect_dxf, preview_dxf
from .doctor import diagnose
from .files import inspect_pdf, preview_pdf
from .io import repository
from .normativa import search, verify

mcp = FastMCP("cdcrd-local")


def root() -> Path:
    configured = os.environ.get("CDCRD_REPO_ROOT")
    return repository(Path(configured) if configured else None)


def input_path(value: str) -> Path:
    base = root()
    path = (base / value).resolve(strict=True)
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("La entrada MCP debe ser un archivo dentro del repo.")
    return path


def output_path(value: str) -> Path:
    base = root() / "herramientas-locales" / "salidas"
    path = (base / value).resolve()
    if not path.is_relative_to(base.resolve()) or path == base.resolve():
        raise ValueError("Las salidas MCP deben quedar dentro de herramientas-locales/salidas.")
    if path.exists():
        raise FileExistsError(f"La salida ya existe: {path.name}")
    return path


@mcp.tool()
def entorno_diagnosticar() -> dict:
    """Verifica paquetes; no conecta las sesiones Revit/ETABS/SAFE."""
    return diagnose()


@mcp.tool()
def cdcrd_buscar(consulta: str, volumen: int | None = None, limite: int = 5) -> dict:
    """Busca clausulas del corpus con volumen, titulo, paginas y archivo fuente."""
    return search(consulta, root(), limite, volumen)


@mcp.tool()
def cdcrd_verificar(chequeo: str, entrada_json: str) -> dict:
    """Ejecuta deriva, masa_modal, torsion, escalado_cortante, irregularidades_verticales o zapata.

    La entrada debe respetar el esquema del verificador existente. Conserva su alcance y fuentes.
    """
    return verify(chequeo, input_path(entrada_json), root())


@mcp.tool()
def cad_generar_plano(entrada_json: str, salida_dxf: str) -> dict:
    """Genera un plano 2D DXF desde el esquema del ejemplo planta-ejemplo.json.

    No interpreta proyecto.json de Revit ni dimensiona armaduras. No sobrescribe archivos.
    La salida es un nombre/ruta relativa a herramientas-locales/salidas.
    """
    return generate_plan(input_path(entrada_json), output_path(salida_dxf))


@mcp.tool()
def cad_inspeccionar(entrada_dxf: str) -> dict:
    """Lee unidades, capas, entidades y auditoria de un DXF; no certifica normativa."""
    return inspect_dxf(input_path(entrada_dxf))


@mcp.tool()
def cad_previsualizar(entrada_dxf: str, salida: str) -> dict:
    """Renderiza DXF 2D a SVG, PNG o PDF sin PyMuPDF ni aplicaciones BIM vivas."""
    return preview_dxf(input_path(entrada_dxf), output_path(salida))


@mcp.tool()
def ifc_inspeccionar(entrada_ifc: str) -> dict:
    """Consulta clases, unidades y cantidades de elementos; no realiza diseno estructural."""
    from .bim import inspect_ifc

    return inspect_ifc(input_path(entrada_ifc))


@mcp.tool()
def ifc_validar_ids(entrada_ifc: str, entrada_ids: str, salida_html: str) -> dict:
    """Valida requisitos IDS con IfcTester y crea HTML; revisar status y alcance."""
    from .bim import validate_ids

    return validate_ids(input_path(entrada_ifc), input_path(entrada_ids), output_path(salida_html))


@mcp.tool()
def pdf_inspeccionar(entrada_pdf: str) -> dict:
    """Lee numero/tamano de paginas y texto de ejemplo de un PDF local."""
    return inspect_pdf(input_path(entrada_pdf))


@mcp.tool()
def pdf_previsualizar(entrada_pdf: str, salida_png: str, pagina: int = 1, dpi: int = 120) -> dict:
    """Renderiza una pagina PDF a PNG; no reconstruye geometria CAD ni BIM."""
    return preview_pdf(input_path(entrada_pdf), output_path(salida_png), pagina, dpi)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
