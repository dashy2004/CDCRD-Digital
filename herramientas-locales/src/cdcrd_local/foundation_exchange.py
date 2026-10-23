"""Explicit coordinate exchange; no analysis, model writes or soil inference."""
import hashlib
import json
import math
from pathlib import Path

LENGTH = {"m": 1.0, "mm": 0.001, "cm": 0.01, "ft": 0.3048, "in": 0.0254}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Se requiere un numero finito, sin conversion implicita")
    return float(value)


def xyz(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Coordenada requiere tres componentes")
    return [number(v) for v in value]


def label(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identificador/fuente vacio")
    return value


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def prepare(snapshot: dict, config: dict) -> dict:
    """Transform selected CSI joints to site metres with independently supplied controls.

    The transform is a rigid rotation about +Z, then translation. It is NOT a CRS
    reprojection or a fit to the controls. At least two distinct controls must pass.
    """
    if snapshot.get("schema") != "cdcrd.csi-points/1":
        raise ValueError("Snapshot CSI no reconocido")
    frame = snapshot["frame"]
    if frame["id"] != config["source_frame"] or frame["axes"] != "Global":
        raise ValueError("Sistema fuente distinto")
    if frame["length_unit"] not in LENGTH:
        raise ValueError("Unidad de longitud no soportada")
    factor = LENGTH[frame["length_unit"]]
    source_origin = xyz(config["source_origin"])
    site_origin = xyz(config["site_origin_m"])
    angle = math.radians(number(config["rotation_deg"]))
    c, s = math.cos(angle), math.sin(angle)
    site_frame = label(config["site_frame"])
    datum = label(config["vertical_datum"])
    tol = number(config["control_tolerance_m"])
    if not 0 < tol <= 0.1:
        raise ValueError("Tolerancia de controles debe estar en (0, 0.1] m")

    def transform(point):
        x, y, z = [(a-b)*factor for a, b in zip(xyz(point), source_origin)]
        return [site_origin[0]+c*x-s*y, site_origin[1]+s*x+c*y, site_origin[2]+z]

    controls = config["controls"]
    if len(controls) < 2 or len(controls) > 100:
        raise ValueError("Se requieren 2-100 controles independientes")
    control_points = [xyz(p["source_xyz"]) for p in controls]
    origin = control_points[0]
    separation = max(math.hypot(p[0]-origin[0], p[1]-origin[1])*factor for p in control_points)
    if len({label(p["id"]) for p in controls}) != len(controls):
        raise ValueError("IDs de controles duplicados")
    if separation < 1.0:
        raise ValueError("Controles sin separacion horizontal de al menos 1 m")
    errors = []
    for control in controls:
        expected = xyz(control["site_xyz_m"])
        actual = transform(control["source_xyz"])
        error = math.dist(actual, expected)
        errors.append({"id": label(control["id"]), "error_m": error})
        if error > tol:
            raise ValueError("Control %s no coincide: %.6f m" % (control["id"], error))
    points = snapshot["points"]
    by_id = {label(p["id"]): p for p in points}
    selected = config["point_ids"]
    if len(by_id) != len(points) or not selected or len(selected) != len(set(selected)):
        raise ValueError("IDs duplicados o seleccion vacia")
    if len(selected) > 1000 or not set(selected).issubset(by_id):
        raise ValueError("Seleccion fuera del snapshot o mayor a 1000 puntos")
    query = {"schema": "cdcrd.foundation-query/1", "site_frame": site_frame,
             "vertical_datum": datum, "length_unit": "m", "source": snapshot["source"],
             "source_frame": frame, "snapshot_sha256": digest(snapshot),
             "config_sha256": digest(config), "control_errors": errors,
             "points": [{"id": key, "site_xyz_m": transform(by_id[key]["xyz"])}
                        for key in selected]}
    query["query_sha256"] = digest(query)
    return query


def validate_query(query):
    if query.get("schema") != "cdcrd.foundation-query/1" or query.get("length_unit") != "m":
        raise ValueError("Consulta no reconocida o unidad distinta de m")
    body = dict(query)
    checksum = body.pop("query_sha256", None)
    if checksum != digest(body):
        raise ValueError("Consulta modificada: hash no coincide")
    label(query["site_frame"])
    label(query["vertical_datum"])
    points = query["points"]
    if not 1 <= len(points) <= 1000 or len({label(p["id"]) for p in points}) != len(points):
        raise ValueError("Lista de puntos invalida")
    for p in points:
        xyz(p["site_xyz_m"])


def review(query: dict, samples: dict, geotechnical: dict | None = None) -> dict:
    """Compare sampled terrain and nominated joint elevations; no footing/volume design."""
    validate_query(query)
    if (samples.get("schema") != "cdcrd.foundation-samples/1"
            or samples.get("query_sha256") != query["query_sha256"]
            or samples.get("site_frame") != query["site_frame"]
            or samples.get("vertical_datum") != query["vertical_datum"]
            or samples.get("length_unit") != "m"):
        raise ValueError("Muestras de otra consulta, unidad o sistema")
    label(samples["source"]["drawing"])
    label(samples["source"]["surface"])
    if samples["source"].get("is_out_of_date") is not False:
        raise ValueError("No se confirmo superficie actualizada")
    rows = samples["samples"]
    indexed = {label(r["id"]): r for r in rows}
    if len(indexed) != len(rows) or set(indexed) != {p["id"] for p in query["points"]}:
        raise ValueError("Muestras faltantes, sobrantes o duplicadas")
    result = []
    for p in query["points"]:
        row = indexed[p["id"]]
        point = p["site_xyz_m"]
        if len(row["xy_m"]) != 2 or math.dist([number(v) for v in row["xy_m"]], point[:2]) > 1e-6:
            raise ValueError("XY de muestra distinto al solicitado")
        if row.get("status") == "ok":
            terrain = number(row["terrain_z_m"])
            result.append({"id": p["id"], "site_xyz_m": point, "terrain_z_m": terrain,
                           "terrain_minus_joint_m": terrain-point[2], "status": "ok"})
        else:
            result.append({"id": p["id"], "site_xyz_m": point, "terrain_z_m": None,
                           "terrain_minus_joint_m": None, "status": "sin_cota",
                           "error": label(row.get("error"))})
    soil = None
    if geotechnical is not None:
        source = label(geotechnical["source"])
        # Both quantities are supplied independently. No qa -> k correlation.
        qa = number(geotechnical["allowable_bearing_kpa"])
        k = number(geotechnical["subgrade_modulus_kn_m3"])
        if qa <= 0 or k <= 0:
            raise ValueError("qa y k deben ser positivos")
        soil = {"source": source, "allowable_bearing_kpa": qa,
                "subgrade_modulus_kn_m3": k,
                "applicable_point_ids": geotechnical["applicable_point_ids"]}
        if (not soil["applicable_point_ids"] or
                len(set(soil["applicable_point_ids"])) != len(soil["applicable_point_ids"]) or
                not set(soil["applicable_point_ids"]).issubset(indexed)):
            raise ValueError("Alcance geotecnico sin puntos o ajeno a la consulta")
    return {"schema": "cdcrd.foundation-review/1", "ok": all(r["status"] == "ok" for r in result),
            "query_sha256": query["query_sha256"], "samples_sha256": digest(samples),
            "rows": result, "geotechnical": soil, "model_writes": 0,
            "analysis_run": False, "design_approved": False,
            "limits": ["La cota del joint no se interpreta automaticamente como fondo de zapata.",
                       "Diferencias puntuales: no son volumen de excavacion ni dimensionamiento.",
                       "La superficie no determina capacidad portante ni modulo de balasto."]}


def run_files(operation: str, source: Path, config: Path, output: Path,
              geotechnical: Path | None = None) -> dict:
    a = json.loads(source.read_text(encoding="utf-8-sig"))
    b = json.loads(config.read_text(encoding="utf-8-sig"))
    try:
        if operation == "prepare":
            result = prepare(a, b)
        elif operation == "review":
            soil = (json.loads(geotechnical.read_text(encoding="utf-8-sig"))
                    if geotechnical else None)
            result = review(a, b, soil)
        else:
            raise ValueError("Operacion desconocida")
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("Contrato incompleto o tipos invalidos: %s" % error) from error
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return result
