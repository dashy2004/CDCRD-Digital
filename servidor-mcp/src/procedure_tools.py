"""MCP entry points shared with the offline CLI. No ETABS instance is acquired."""
from beam_procedure import read_design_summary_csv, review_longitudinal, review_torsion_faces
from etabs_procedure import (calculate_loads, ceil_step, get_procedure,
                             grouped_masonry_totals, prepare_modeling)
from modeling_checks import audit_modeling


def get_etabs_procedure(profile: str) -> dict:
    """Biblioteca y 22 etapas del perfil explicito modeling_20261015; no modifica modelos."""
    return get_procedure(profile)


def prepare_etabs_modeling(profile: str, project: dict) -> dict:
    """Plan residencial: model_path .EDB, has_parking, stories con architectural_height_m;
    seismic opcional con parametros confirmados, muestras SI y F. Ver docs/PROCEDIMIENTO-ETABS.md.
    No aplica el plan ni autoriza analisis.
    """
    return prepare_modeling(profile, project)


def calculate_etabs_project_loads(profile: str, data: dict) -> dict:
    """Calcula sets/mamposteria/agua con componentes y unidades explicitos.
    data: has_parking, slabs, walls_on_beams y water. No asigna cargas.
    """
    return calculate_loads(profile, data)


def audit_etabs_modeling_snapshot(profile: str, project: dict, snapshot: dict) -> dict:
    """Compara snapshot aportado con perfil: unidades, masa, sismo, shells, malla,
    diafragmas por story, apoyos y recibos. No lee ETABS ni acredita datos ausentes.
    """
    return audit_modeling(profile, project, snapshot)


def prepare_etabs_slab_measurements(profile: str, dimensions_m: list[float],
                                   masonry_totals_by_story: dict) -> dict:
    """Redondea dimensiones hacia arriba a 0.05m; mamposteria usa maximo de totales
    completos por losa/espesor, sin redondear longitudes ni sumar pisos.
    """
    get_procedure(profile)
    return {"dimensions_original_m": dimensions_m,
            "dimensions_rounded_m": [ceil_step(v) for v in dimensions_m],
            "masonry": grouped_masonry_totals(masonry_totals_by_story),
            "files_modified": False}


def review_etabs_longitudinal(profile: str, data: dict) -> dict:
    """Compara seis demandas total_longitudinal y barras verificadas por cara/zona.
    Conserva minimos por luz, adicionales continuos, errores y diametros del perfil.
    """
    return review_longitudinal(profile, data)


def review_etabs_flexure_torsion(profile: str, data: dict) -> dict:
    """Compara flexure_only y torsion longitudinal por cara/zona; nunca transfiere
    excedentes ni admite As total o At/s como demanda de flexion/Al.
    """
    return review_torsion_faces(profile, data)


def read_etabs_design_summary_csv(path: str, area_unit: str, station_unit: str,
                                  model_source: str, export_date: str,
                                  stations_are_support_faces: bool) -> dict:
    """Lee CSV Design Summary existente con AsTopTotal/AsBotTotal y errores.
    Unidades/fecha/modelo son obligatorios. Lectura local historica, no conexion viva.
    """
    return read_design_summary_csv(path, area_unit, station_unit, model_source,
                                   export_date, stations_are_support_faces)


PROCEDURE_TOOLS = (
    get_etabs_procedure, prepare_etabs_modeling, calculate_etabs_project_loads,
    audit_etabs_modeling_snapshot, prepare_etabs_slab_measurements,
    review_etabs_longitudinal, review_etabs_flexure_torsion,
    read_etabs_design_summary_csv,
)


def register_procedure_tools(mcp):
    for fn in PROCEDURE_TOOLS:
        mcp.tool()(fn)
