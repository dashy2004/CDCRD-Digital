"""Read-only source-contract preflight, sharing the converter's actual readers."""
from xml.etree.ElementTree import ParseError

import numpy as np
from defusedxml.common import DefusedXmlException

from .sources import load_sources


def validate_interchange(**sources):
    report = {"schema": "cdcrd.interchange-validation/1", "module": "beamng",
              "ok": False, "scope": "source_contract_only", "errors": [], "warnings": [],
              "consumer_validation": "not_checked", "crs": "not_verified"}
    try:
        bundle = load_sources(**sources)
    except (ValueError, OSError, ParseError, DefusedXmlException) as error:
        message = (f"Cannot read source ({type(error).__name__})"
                   if isinstance(error, OSError) else str(error))
        report["errors"].append({"code": "invalid_source", "message": message})
        return report
    terrain, road = bundle.terrain, bundle.road
    report.update(ok=True, source_schema=bundle.schema, units="m", coordinate_order="E,N,Z",
                  source_identity_checked=bundle.source_identity_checked,
                  bounds_abs_m={"min": np.minimum(terrain.vertices.min(axis=0),
                                                  road.vertices.min(axis=0)).tolist(),
                                "max": np.maximum(terrain.vertices.max(axis=0),
                                                  road.vertices.max(axis=0)).tolist()},
                  counts={"terrain_vertices": len(terrain.vertices),
                          "terrain_triangles": len(terrain.triangles),
                          "road_vertices": len(road.vertices), "road_triangles": len(road.triangles),
                          "guide_nodes": 0 if bundle.guide is None else len(bundle.guide)})
    report["warnings"].append("CRS, shared survey origin and real-world scale require external verification; no reprojection is performed.")
    if not bundle.source_identity_checked:
        report["warnings"].append("Distinct Civil 3D surface handles were not declared; source object identity is not verified.")
    return report
