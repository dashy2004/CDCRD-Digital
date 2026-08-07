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

    # Introspeccion: consultar firmas reales antes de suponerlas.
    describe_oapi = mcp.tool()(etabs.describe_oapi)

    # Edicion: borrar, mover, liberar extremos
    delete_object = mcp.tool()(etabs.delete_object)
    move_objects = mcp.tool()(etabs.move_objects)
    set_frame_releases = mcp.tool()(etabs.set_frame_releases)

    # Resortes
    set_point_spring = mcp.tool()(etabs.set_point_spring)
    set_base_springs = mcp.tool()(etabs.set_base_springs)

    # Resultados dedicados
    get_joint_reactions = mcp.tool()(etabs.get_joint_reactions)
    get_frame_forces = mcp.tool()(etabs.get_frame_forces)

    # Acero
    define_steel_material = mcp.tool()(etabs.define_steel_material)
    define_i_section = mcp.tool()(etabs.define_i_section)
    define_pipe_section = mcp.tool()(etabs.define_pipe_section)
    run_steel_design = mcp.tool()(etabs.run_steel_design)

    # No lineal, P-Delta, time-history
    add_pdelta_case = mcp.tool()(etabs.add_pdelta_case)
    add_nonlinear_static_case = mcp.tool()(etabs.add_nonlinear_static_case)
    add_time_history_case = mcp.tool()(etabs.add_time_history_case)

    # Niveles
    get_stories = mcp.tool()(etabs.get_stories)
    set_stories = mcp.tool()(etabs.set_stories)

    # Materiales y secciones
    define_concrete_material = mcp.tool()(etabs.define_concrete_material)
    define_rect_section = mcp.tool()(etabs.define_rect_section)
    assign_sections = mcp.tool()(etabs.assign_sections)

    # Apoyos
    set_base_restraints = mcp.tool()(etabs.set_base_restraints)

    # Cargas y combinaciones
    add_load_pattern = mcp.tool()(etabs.add_load_pattern)
    add_load_combo = mcp.tool()(etabs.add_load_combo)
    assign_frame_distributed_load = mcp.tool()(etabs.assign_frame_distributed_load)

    # Analisis y resultados
    run_analysis = mcp.tool()(etabs.run_analysis)
    get_story_drifts = mcp.tool()(etabs.get_story_drifts)

    # Tablas interactivas: acceso generico a lo que no tiene metodo dedicado
    # (grids en "Grid Definitions - Grid Lines", masa sismica, etc.)
    list_tables = mcp.tool()(etabs.list_tables)
    get_table_data = mcp.tool()(etabs.get_table_data)
    set_table_data = mcp.tool()(etabs.set_table_data)

    # Lectores de definiciones (PLAN-MEJORAS 1.4). Existen porque las tablas
    # de definicion de casos/combos/funciones no devuelven filas por
    # GetTableForDisplayArray y porque el eco de una herramienta de escritura
    # no dice lo que YA habia en el modelo (Dead/Live de plantilla, Slab1).
    get_load_patterns = mcp.tool()(etabs.get_load_patterns)
    get_load_combos = mcp.tool()(etabs.get_load_combos)
    get_spectrum = mcp.tool()(etabs.get_spectrum)
    get_materials = mcp.tool()(etabs.get_materials)
    get_frame_sections = mcp.tool()(etabs.get_frame_sections)
    get_area_sections = mcp.tool()(etabs.get_area_sections)
    get_diaphragms = mcp.tool()(etabs.get_diaphragms)
    get_restraints = mcp.tool()(etabs.get_restraints)
    get_modal_results = mcp.tool()(etabs.get_modal_results)

    # Borrado de definiciones (PLAN-MEJORAS 1.2): complementa a delete_object,
    # que solo cubre geometria.
    delete_definition = mcp.tool()(etabs.delete_definition)

    # Diafragmas y cargas en areas
    set_rigid_diaphragm = mcp.tool()(etabs.set_rigid_diaphragm)
    assign_area_uniform_load = mcp.tool()(etabs.assign_area_uniform_load)

    # Sismo: espectro CDCRD y caso de espectro de respuesta
    define_cdcrd_spectrum = mcp.tool()(etabs.define_cdcrd_spectrum)
    add_response_spectrum_case = mcp.tool()(etabs.add_response_spectrum_case)

    # Diseño
    run_concrete_design = mcp.tool()(etabs.run_concrete_design)

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
