# FEA MCP - fix
# Servidor MCP para software de elementos finitos (ETABS / LUSAS).
#
# Correcciones respecto al original:
#   1. El logging se configura ANTES de instanciar Config, de lo contrario
#      los mensajes de arranque se pierden.
#   2. El log de archivo se escribe junto al script, no en el CWD (que en
#      Claude Desktop es un directorio arbitrario, a menudo sin permiso de
#      escritura -> el servidor moria al arrancar).
#   3. El recurso config estaba anotado -> str pero devolvia un dict.
#   4. Import explicito en lugar de "from X import *".
#   5. El directorio src/ se agrega a sys.path para que los imports funcionen
#      sin importar como se lance el proceso.
#   6. Si el software configurado no esta soportado, se falla con mensaje
#      claro en lugar de arrancar sin ninguna herramienta registrada.

import json
import logging
import os
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),   # stdout esta reservado al protocolo MCP
        logging.FileHandler(os.path.join(SRC_DIR, 'fea_mcp.log'), encoding='utf-8'),
    ])
logger = logging.getLogger('fea_mcp_server')
logger.info("Iniciando servidor FEA MCP")

from mcp.server.fastmcp import FastMCP          # noqa: E402
from config import Config                       # noqa: E402

SUPPORTED = ("ETABS", "LUSAS")

config = Config()
logger.info("Software configurado: %s %s", config.feaName, config.feaVersion)

mcp = FastMCP(config.serverName, dependencies=["comtypes", "pywin32"])


@mcp.resource("config://app")
def get_config() -> str:
    """Configuracion activa del servidor."""
    return json.dumps(config.data, indent=2, ensure_ascii=False)


if config.feaName == "ETABS":
    from Etabs import Etabs
    etabs = Etabs(auto_start=config.autoStart, exe_path=config.exePath)
    logger.info("Registrando herramientas de ETABS...")

    get_model_info = mcp.tool()(etabs.get_model_info)
    get_units = mcp.tool()(etabs.get_units)
    set_units = mcp.tool()(etabs.set_units)
    save_model = mcp.tool()(etabs.save_model)
    refresh_view = mcp.tool()(etabs.refresh_view)

    create_objects_by_coordinates = mcp.tool()(etabs.create_objects_by_coordinates)

    get_all_geometries = mcp.tool(name="get_all_geometries")(etabs.get_geometries)
    get_points = mcp.tool()(etabs.get_points)
    get_frames = mcp.tool()(etabs.get_frames)
    get_areas = mcp.tool()(etabs.get_areas)

elif config.feaName == "LUSAS":
    from Lusas import Lusas
    lusas = Lusas(config.feaVersion)
    logger.info("Registrando herramientas de LUSAS...")

    get_units = mcp.tool()(lusas.get_units)
    create_objects_by_coordinates = mcp.tool()(lusas.create_objects_by_coordinates)
    sweep_points = mcp.tool()(lusas.sweep_points)
    sweep_lines = mcp.tool()(lusas.sweep_lines)
    sweep_surfaces = mcp.tool()(lusas.sweep_surfaces)
    get_all_geometries = mcp.tool(name="get_all_geometries")(lusas.get_geometries)
    get_points = mcp.tool()(lusas.get_points)
    get_lines = mcp.tool()(lusas.get_lines)
    get_surfaces = mcp.tool()(lusas.get_surfaces)
    get_volumes = mcp.tool()(lusas.get_volumes)
    select = mcp.tool()(lusas.select)

else:
    logger.error("Software '%s' no soportado. Opciones: %s",
                 config.feaName, ", ".join(SUPPORTED))
    raise SystemExit(
        f"config.json: 'software' = '{config.feaName}' no es valido. "
        f"Use uno de: {', '.join(SUPPORTED)}"
    )


if __name__ == "__main__":
    mcp.run(transport='stdio')
