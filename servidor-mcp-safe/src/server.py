# SAFE MCP - v0.1.0
# Servidor MCP para SAFE (CSI), estructurado identico a
# servidor-mcp/src/server.py (mismo patron: logging antes de Config, log
# junto al script, sys.path explicito, registro de herramientas por bloque).

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
        logging.FileHandler(os.path.join(SRC_DIR, 'safe_mcp.log'), encoding='utf-8'),
    ])
logger = logging.getLogger('safe_mcp_server')
logger.info("Iniciando servidor SAFE MCP")

from mcp.server.fastmcp import FastMCP          # noqa: E402
from config import Config                       # noqa: E402
from Safe import Safe                            # noqa: E402

config = Config()
logger.info("SAFE MCP v%s. ProgID configurado: %s",
           config.serverVersion, config.progId or "(sondeo automatico)")

mcp = FastMCP(config.serverName, dependencies=["comtypes", "pywin32"])


@mcp.resource("config://app")
def get_config() -> str:
    """Configuracion activa del servidor."""
    return json.dumps(config.data, indent=2, ensure_ascii=False)


safe = Safe(auto_start=config.autoStart, exe_path=config.exePath,
           prog_id=config.progId, helper_prog_id=config.helperProgId)
logger.info("Registrando herramientas de SAFE...")

# Conexion / introspeccion
get_model_info = mcp.tool()(safe.get_model_info)
get_units = mcp.tool()(safe.get_units)
set_units = mcp.tool()(safe.set_units)
save_model = mcp.tool()(safe.save_model)
refresh_view = mcp.tool()(safe.refresh_view)
describe_oapi = mcp.tool()(safe.describe_oapi)

# Geometria
get_points = mcp.tool()(safe.get_points)
get_areas = mcp.tool()(safe.get_areas)
create_area_by_coordinates = mcp.tool()(safe.create_area_by_coordinates)

# Materiales
define_concrete_material = mcp.tool()(safe.define_concrete_material)
define_rebar_material = mcp.tool()(safe.define_rebar_material)

# Secciones de losa/zapata
define_slab_section = mcp.tool()(safe.define_slab_section)

# Resorte de suelo
define_soil_spring = mcp.tool()(safe.define_soil_spring)
assign_area_spring = mcp.tool()(safe.assign_area_spring)

# Cargas y combinaciones
add_load_pattern = mcp.tool()(safe.add_load_pattern)
add_load_combo = mcp.tool()(safe.add_load_combo)

# Analisis y diseño
run_analysis = mcp.tool()(safe.run_analysis)
get_analysis_status = mcp.tool()(safe.get_analysis_status)
run_slab_design = mcp.tool()(safe.run_slab_design)
get_slab_design_summary = mcp.tool()(safe.get_slab_design_summary)
get_slab_design_detail = mcp.tool()(safe.get_slab_design_detail)
get_design_strips = mcp.tool()(safe.get_design_strips)
get_span_definitions = mcp.tool()(safe.get_span_definitions)

# Verificaciones del SOP (3.12 presion, 3.13 punzonamiento) via tablas
get_punching_check = mcp.tool()(safe.get_punching_check)
get_soil_pressure = mcp.tool()(safe.get_soil_pressure)

# Sonda de eFileType (HUECOS S-1): descubre los codigos de F2K/DXF
probe_file_types = mcp.tool()(safe.probe_file_types)

# Tablas interactivas (presion de suelo, punzonamiento, combos pegados)
list_tables = mcp.tool()(safe.list_tables)
get_table_data = mcp.tool()(safe.get_table_data)
set_table_data = mcp.tool()(safe.set_table_data)

# Import/export de archivo (F2K desde ETABS, DXF para detallar)
import_file = mcp.tool()(safe.import_file)
export_file = mcp.tool()(safe.export_file)


if __name__ == "__main__":
    mcp.run(transport='stdio')
