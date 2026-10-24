"""Sample native TIN elevations for a checked CSI coordinate query; read only."""
import importlib.util
import json
import ntpath
from datetime import datetime, timezone
from pathlib import Path


def contract():
    path = (Path(__file__).resolve().parents[2] / "herramientas-locales" / "src" /
            "cdcrd_local" / "foundation_exchange.py")
    spec = importlib.util.spec_from_file_location("foundation_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample(llamar, query, expected_drawing, surface_handle, site_frame, vertical_datum):
    core = contract()
    core.validate_query(query)
    if not ntpath.isabs(expected_drawing) or not surface_handle:
        raise ValueError("Requiere ruta DWG absoluta y handle de superficie")
    if query["site_frame"] != site_frame or query["vertical_datum"] != vertical_datum:
        raise ValueError("Sistema/datum del dibujo no coincide con la consulta")

    def guard():
        doc = llamar("doc.info", {})
        if (ntpath.normcase(ntpath.normpath(doc.get("dibujo", ""))) !=
                ntpath.normcase(ntpath.normpath(expected_drawing)) or doc.get("civil3d") is not True):
            raise ValueError("Dibujo activo distinto o Civil 3D no disponible")
        units = llamar("objects.read", {
            "ruta": "Settings.DrawingSettings.UnitZoneSettings.DrawingUnits"})
        if doc.get("insunits") != 6 or units.get("valor") != "Meters":
            raise ValueError("INSUNITS y unidades Civil deben estar en metros")
        objects = llamar("objects.query", {"handles": [surface_handle],
                         "props": ["Name", "IsOutOfDate"], "limite": 1})["objetos"]
        if (len(objects) != 1 or objects[0].get("tipo") != "Autodesk.Civil.DatabaseServices.TinSurface"
                or objects[0].get("IsOutOfDate") is not False):
            raise ValueError("Requiere TinSurface actualizada; no se reconstruye automaticamente")
        return objects[0]

    surface = guard()
    rows = []
    for point in query["points"]:
        guard()
        x, y, _z = point["site_xyz_m"]
        row = {"id": point["id"], "xy_m": [x, y]}
        try:
            value = llamar("objects.invoke", {"handle": surface_handle,
                           "metodo": "FindElevationAtXY", "args": [x, y]})["resultado"]
            row.update(status="ok", terrain_z_m=core.number(value))
        except (RuntimeError, ValueError) as error:
            # Failure is explicit and never converted to zero or nearest-point extrapolation.
            row.update(status="error", terrain_z_m=None, error=str(error))
        guard()
        rows.append(row)
    return {"schema": "cdcrd.foundation-samples/1", "length_unit": "m",
            "query_sha256": query["query_sha256"], "site_frame": site_frame,
            "vertical_datum": vertical_datum,
            "source": {"drawing": expected_drawing, "surface": surface_handle,
                       "surface_name": surface.get("Name"), "is_out_of_date": False,
                       "captured_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 (Python 3.10)
                       "method": "TinSurface.FindElevationAtXY"},
            "samples": rows, "model_writes": 0}


def registrar(mcp, llamar, ok):
    @mcp.tool()
    def muestrear_cimentaciones(consulta_json: str, dibujo_esperado: str,
                               superficie_handle: str, sistema_sitio: str,
                               datum_vertical: str) -> str:
        """Lee cotas TIN en puntos CSI transformados; no modifica ni extrapola.

        Requiere consulta cdcrd.foundation-query/1 de preparar-cimentacion,
        dibujo identificado, INSUNITS y Civil en metros, TinSurface actualizada.
        Sistema y datum son declaraciones del operador; no se ajustan ni infieren.
        """
        return ok(sample(llamar, json.loads(consulta_json), dibujo_esperado,
                         superficie_handle, sistema_sitio, datum_vertical))
