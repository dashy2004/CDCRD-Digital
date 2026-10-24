"""Guarded area soil transfer. No geometry, unit, analysis or file writes.

Run only on the adapter's COM thread with an exclusive operator turn.
CSI setters are not transactional; a failure receipt must be inspected before retry.
"""
import hashlib
import json
import math
import ntpath
import re

from coordinate_snapshot import capture_points

SPRINGS = "Spring Property Definitions - Area Springs"
ASSIGNMENTS = "Area Assignments - Area Springs"
K_FACTORS = {6: 1.0, 9: 1e-6, 10: 1000.0}  # kN/m3 -> kN/m3, N/mm3, N/m3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def checked(raw, name):
    if not isinstance(raw, (tuple, list)) or not raw or type(raw[-1]) is not int or raw[-1] != 0:
        raise RuntimeError(f"{name}: respuesta API fallida: {raw!r}")
    return raw[:-1]


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Numero finito requerido")
    return float(value)


def _geometry(snapshot, areas):
    return {"model": snapshot["source"]["model"], "units_enum": snapshot["source"]["units_enum"],
            "frame": snapshot["frame"], "points": sorted(snapshot["points"], key=lambda p: p["id"]),
            "areas": sorted(areas, key=lambda a: a["id"])}


def _assignment_state(model, names):
    # SAFE 23 GetSpringAssignment returns [None, 1] for an unassigned area.
    # Only a successfully read empty table / absent row establishes absence.
    n, keys, titles, kinds, empty = checked(model.DatabaseTables.GetAllTables(), "GetAllTables")
    if (any(len(a) != n for a in (keys, titles, kinds, empty)) or len(set(keys)) != n
            or ASSIGNMENTS not in keys):
        raise RuntimeError("Inventario de tablas de asignaciones incompleto")
    flag = empty[list(keys).index(ASSIGNMENTS)]
    if type(flag) is not bool:
        raise RuntimeError("Estado vacio de tabla desconocido")
    assigned = {name: "None" for name in names}
    if flag:
        return assigned
    _, _, fields, count, flat = checked(
        model.DatabaseTables.GetTableForDisplayArray(ASSIGNMENTS, [], "", 0), ASSIGNMENTS)
    if (not {"UniqueName", "SpringProp"}.issubset(fields) or len(set(fields)) != len(fields)
            or count < 1 or len(flat) != count * len(fields)):
        raise RuntimeError("Tabla de asignaciones incompleta")
    seen = set()
    for offset in range(0, len(flat), len(fields)):
        row = dict(zip(fields, flat[offset:offset+len(fields)]))
        aid = row["UniqueName"]
        if aid not in assigned or aid in seen or not isinstance(row["SpringProp"], str):
            raise RuntimeError("Asignacion duplicada, desconocida o sin nombre")
        seen.add(aid)
        assigned[aid] = row["SpringProp"]
    return assigned


def _capture(model, path, frame):
    snapshot = capture_points(model, "SAFE", path, frame)
    n, names = checked(model.AreaObj.GetNameList(), "AreaObj.GetNameList")
    names = list(names or [])
    if type(n) is not int or not 1 <= n <= 1000 or n != len(names) or len(set(names)) != n:
        raise ValueError("Se requieren 1-1000 areas con IDs unicos")
    known_points = {p["id"] for p in snapshot["points"]}
    areas, assigned = [], _assignment_state(model, names)
    for name in sorted(names):
        count, ids = checked(model.AreaObj.GetPoints(name), "AreaObj.GetPoints")
        ids = list(ids)
        if (not 3 <= count <= 1000 or len(ids) != count or len(set(ids)) != count
                or not set(ids).issubset(known_points)):
            raise ValueError("Conectividad incompleta o repetida")
        section, = checked(model.AreaObj.GetProperty(name), "AreaObj.GetProperty")
        opening, = checked(model.AreaObj.GetOpening(name), "AreaObj.GetOpening")
        matrix, = checked(model.AreaObj.GetTransformationMatrix(name), "AreaObj.GetTransformationMatrix")
        matrix = [finite(x) for x in matrix]
        if len(matrix) != 9 or type(opening) is not bool:
            raise ValueError("Matriz/eje local o abertura no validos")
        areas.append({"id": name, "point_ids": ids, "section": section,
                      "opening": opening, "matrix": matrix})
    count, properties = checked(model.PropAreaSpring.GetNameList(), "PropAreaSpring.GetNameList")
    properties = list(properties or [])
    if count != len(properties) or len(set(properties)) != count:
        raise ValueError("Lista de resortes incompleta")
    return snapshot, _geometry(snapshot, areas), {"assignments": assigned, "properties": sorted(properties)}


def capture_context(model, expected_path, frame_id):
    """Double read rejects changed identity, units, points, areas or soil names."""
    snapshot, geometry, state = _capture(model, expected_path, frame_id)
    _, again, next_state = _capture(model, expected_path, frame_id)
    if geometry != again or state != next_state:
        raise RuntimeError("Modelo cambio durante lectura; descartar contexto")
    context = {"schema": "cdcrd.safe-soil-context/1", "snapshot": snapshot,
               "geometry": geometry, "geometry_sha256": digest(geometry), "soil_state": state,
               "model_locked": model.GetModelIsLocked(), "model_writes": 0}
    if type(context["model_locked"]) is not bool:
        raise ValueError("Estado de bloqueo desconocido")
    context["context_sha256"] = digest(context)
    return context


def validate_plan(plan, expected_sha256):
    body = dict(plan)
    checksum = body.pop("plan_sha256", None)
    if checksum != expected_sha256 or checksum != digest(body):
        raise ValueError("Plan modificado: hash no coincide")
    if plan.get("schema") != "cdcrd.safe-soil-plan/1":
        raise ValueError("Plan no reconocido")
    filename = ntpath.basename(plan["target"]["model"])
    if not filename.startswith("SYNTHETIC_") or ntpath.splitext(filename)[1].lower() != ".fdb":
        raise ValueError("Piloto limitado a modelos nuevos SYNTHETIC_*.FDB; revisar apoyos heredados antes de ampliar")
    units = plan["target"]["units_enum"]
    if type(units) is not int or units not in K_FACTORS:
        raise ValueError("Solo se admiten kN,m,C; N,mm,C; N,m,C")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,49}", plan["property_name"]):
        raise ValueError("Nombre de resorte invalido")
    if type(plan["compression_only"]) is not bool:
        raise ValueError("compression_only debe ser booleano explicito")
    soil = plan["geotechnical"]
    k = finite(soil["subgrade_modulus_kn_m3"])
    qa = finite(soil["allowable_bearing_kpa"])
    if k <= 0 or qa <= 0 or not isinstance(soil["source"], str) or not soil["source"].strip():
        raise ValueError("Geotecnia debe tener k, qa positivos y fuente")
    ids = plan["area_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100
            or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids)):
        raise ValueError("Seleccion invalida de areas")
    rows = plan["terrain_rows"]
    indexed = {r["id"]: r for r in rows}
    if len(indexed) != len(rows) or not indexed:
        raise ValueError("Muestras TIN duplicadas/vacias")
    for row in rows:
        if row["status"] != "ok":
            raise ValueError("Muestra TIN fallida")
        finite(row["terrain_z_m"])
        if len(row["site_xyz_m"]) != 3:
            raise ValueError("Coordenadas de muestra incompletas")
        for value in row["site_xyz_m"]:
            finite(value)
    converted = finite(k * K_FACTORS[units])
    if converted <= 0:
        raise ValueError("k convertido fuera de rango")
    return converted


def _validate_targets(plan, context):
    geometry = context["geometry"]
    if (geometry["model"] != plan["target"]["model"] or geometry["frame"] != plan["target"]["frame"]
            or geometry["units_enum"] != plan["target"]["units_enum"]
            or context["geometry_sha256"] != plan["geometry_sha256"]):
        raise ValueError("Modelo, unidades o geometria cambiaron desde el plan")
    if context["model_locked"]:
        raise ValueError("Modelo bloqueado; no se desbloquea ni se invalidan resultados")
    if context["soil_state"] != plan["soil_state_before"]:
        raise ValueError("Asignaciones/resortes cambiaron; inspeccionar antes de repetir")
    if plan["property_name"] in context["soil_state"]["properties"]:
        raise ValueError("No se reemplazan propiedades existentes")
    areas = {a["id"]: a for a in geometry["areas"]}
    points = {p["id"]: p["xyz"] for p in geometry["points"]}
    sampled = {r["id"] for r in plan["terrain_rows"]}
    applicable = set(plan["geotechnical"]["applicable_point_ids"])
    for aid in plan["area_ids"]:
        if aid not in areas:
            raise ValueError("Area no presente")
        area = areas[aid]
        if context["soil_state"]["assignments"][aid] not in ("", "None"):
            raise ValueError("Area ya tiene resorte; no se reemplaza")
        if (area["opening"] or area["section"] in ("", "None")
                or any(abs(a-b) > 1e-8 for a, b in zip(area["matrix"][6:9], [0., 0., 1.]))):
            raise ValueError("Se requiere area fisica horizontal con eje local 3 hacia +Z")
        ids = set(area["point_ids"])
        if not ids.issubset(sampled) or not ids.issubset(applicable):
            raise ValueError("Faltan cotas TIN o alcance geotecnico en vertices")
        zs = [points[p][2] for p in ids]
        if max(zs) - min(zs) > 1e-7:
            raise ValueError("Area no horizontal")


def _verify_property(read_table, name, k, compression):
    _, fields, rows = read_table(SPRINGS)
    required = {"Name", "StiffU1", "StiffU2", "StiffU3", "NonlinOpt3"}
    if not required.issubset(fields):
        raise RuntimeError("Esquema de resortes distinto")
    matches = [dict(zip(fields, row)) for row in rows if row[fields.index("Name")] == name]
    if len(matches) != 1:
        raise RuntimeError("Propiedad no encontrada de forma unica")
    row = matches[0]
    for field, expected in (("StiffU1", 0.), ("StiffU2", 0.), ("StiffU3", k)):
        actual = float(row[field])
        if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-12):
            raise RuntimeError(f"Rigidez no confirmada en {field}: {actual} != {expected}")
    if row["NonlinOpt3"] != ("Compression Only" if compression else "None"):
        raise RuntimeError("Comportamiento no confirmado por tabla")
    return row


def apply_plan(model, read_table, plan, expected_sha256, confirmed_copy=False):
    """Validate all targets before any setter, then verify each effect; never retry."""
    if confirmed_copy is not True:
        raise ValueError("Se requiere confirmacion explicita de copia de trabajo")
    k = validate_plan(plan, expected_sha256)
    target = plan["target"]
    before = capture_context(model, target["model"], target["frame"]["id"])
    _validate_targets(plan, before)
    receipt = {"schema": "cdcrd.safe-soil-receipt/1", "ok": False, "plan_sha256": expected_sha256,
               "model": target["model"], "units_enum": target["units_enum"], "k_native": k,
               "attempted": [], "confirmed": [], "analysis_run": False, "design_run": False,
               "saved": False, "geometry_unchanged": False}
    name = plan["property_name"]
    try:
        receipt["attempted"].append({"property": name})
        ret = model.PropAreaSpring.SetAreaSpringProp(name, 0., 0., k, 1 if plan["compression_only"] else 0)
        if type(ret) is not int or ret != 0:
            raise RuntimeError(f"SetAreaSpringProp: ret={ret}")
        receipt["property_table"] = _verify_property(read_table, name, k, plan["compression_only"])
        receipt["confirmed"].append({"property": name})
        for aid in plan["area_ids"]:
            now = capture_context(model, target["model"], target["frame"]["id"])
            if now["geometry_sha256"] != before["geometry_sha256"] or now["model_locked"]:
                raise RuntimeError("Modelo cambio despues de crear propiedad; detener")
            if now["soil_state"]["assignments"][aid] not in ("", "None"):
                raise RuntimeError("Asignacion concurrente; detener")
            receipt["attempted"].append({"area": aid})
            ret = model.AreaObj.SetSpringAssignment(aid, name, 0)
            if type(ret) is not int or ret != 0:
                raise RuntimeError(f"SetSpringAssignment: ret={ret}")
            assigned, = checked(model.AreaObj.GetSpringAssignment(aid), "GetSpringAssignment")
            if assigned != name:
                raise RuntimeError("Asignacion no confirmada por API")
            receipt["confirmed"].append({"area": aid})
        after = capture_context(model, target["model"], target["frame"]["id"])
        wanted = dict(before["soil_state"]["assignments"])
        wanted.update({aid: name for aid in plan["area_ids"]})
        receipt["geometry_unchanged"] = after["geometry_sha256"] == before["geometry_sha256"]
        if (not receipt["geometry_unchanged"] or after["soil_state"]["assignments"] != wanted
                or after["soil_state"]["properties"] != sorted(before["soil_state"]["properties"] + [name])):
            raise RuntimeError("Estado final distinto del cambio solicitado")
        _verify_property(read_table, name, k, plan["compression_only"])
        receipt.update(ok=True, context_after=after)
    except Exception as error:  # noqa: BLE001 -- retain receipt after any partial native write
        receipt.update(error=str(error), partial_write_possible=True,
                       next_action="Inspeccionar propiedad/asignaciones y recibo; no repetir automaticamente.")
    return receipt
