"""Area comparisons under a selected user procedure, never structural approval."""
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from etabs_procedure import get_procedure, number, text, unique

ZONES = ("i", "center", "j")
FACES = ("top", "bottom")
AREA_FACTORS = {"cm2": 1.0, "mm2": 0.01, "m2": 10000.0}
# Adopted totals from the supplied review procedure; distinct from ETABS #6 library.
BAR_AREAS = {"3/4": {n: n * 2.85 for n in range(1, 7)},
             "1": dict(enumerate([5.07, 10.13, 15.20, 20.27, 25.34, 30.40], 1)),
             "1/2": {n: n * 1.27 for n in range(1, 7)}}
SPAN_ROWS = [
    (4, 6, .50, .25, 5.70, 3.80), (6, 7.5, .60, .25, 8.55, 5.70),
    (7.5, 8.5, .65, .30, 11.40, 5.70), (8.5, 10, .70, .30, 15.20, 10.13),
    (10, 11, .80, .40, 20.27, 15.20), (11, 12, .90, .40, 30.40, 20.27),
]


def area(value, unit):
    if unit not in AREA_FACTORS:
        raise ValueError("Unidad de area explicita: cm2, mm2 o m2")
    return number(value, "area") * AREA_FACTORS[unit]


def bar_area(diameter, count):
    if diameter not in BAR_AREAS or type(count) is not int or not 1 <= count <= 100:
        raise ValueError("Diametro o numero de barras invalido")
    if count in BAR_AREAS[diameter]:
        return BAR_AREAS[diameter][count]
    # Untabulated 1-inch counts: exact nominal diameter, rounded total area.
    if diameter == "1":
        a = Decimal("3.14159265358979323846") * Decimal("2.54") ** 2 / 4 * count
        return float(a.quantize(Decimal(".01"), rounding=ROUND_HALF_UP))
    return count * BAR_AREAS[diameter][1]


def proposal(required, face, *, additional):
    if required <= 1e-9:
        return []
    if face == "top" and not additional:
        diameters = ["3/4", "1"]  # no top-continuous threshold was specified
    else:
        threshold = 14.25 if face == "top" else 11.40
        diameters = ["3/4" if required <= threshold + 1e-9 else "1"]
    result = []
    for diameter in diameters:
        count = next((n for n in range(1, 101) if bar_area(diameter, n) + 1e-9 >= required), None)
        if count is None:
            raise ValueError("Demanda fuera del rango de propuesta; revisar manualmente")
        result.append({"diameter_in": diameter, "count": count,
                       "area_cm2": bar_area(diameter, count)})
    return result


def span_minimum(span):
    span = number(span, "clear_span_m", positive=True)
    if span < 4:
        return {"h_m": 0, "b_m": 0, "bottom_cm2": 0, "top_cm2": 0}
    if span in (6, 8.5, 10, 11):
        raise ValueError("Limite compartido de luz sin criterio confirmado")
    if span > 12:
        raise ValueError("Luz fuera de la tabla del procedimiento")
    row = next(r for r in SPAN_ROWS if r[0] <= span < r[1] or (span == 12 and r[1] == 12))
    return dict(zip(("h_m", "b_m", "bottom_cm2", "top_cm2"), row[2:]))


def review_longitudinal(profile: str, data: dict) -> dict:
    """Compare six supplied total-longitudinal demands and physically identified bars."""
    get_procedure(profile)
    if data.get("demand_kind") != "total_longitudinal":
        raise ValueError("Esta revision exige total_longitudinal (incluye torsion); no sumar Al otra vez")
    unit = data.get("area_unit")
    text(data.get("model_source"), "model_source")
    beams = unique(data.get("beams", []))
    if not beams:
        raise ValueError("Faltan vigas")
    results, axes = [], {}
    axis_demands, pending_axes = {}, set()
    for beam in beams:
        axis = text(beam.get("axis"), "axis")
        try:
            minimum = span_minimum(beam.get("clear_span_m"))
        except ValueError:
            pending_axes.add(axis)
            continue
        targets = axis_demands.setdefault(axis, {"top": 0, "bottom": 0})
        for face in FACES:
            central = area(beam.get("demands", {}).get(face, {}).get("center"), unit)
            targets[face] = max(targets[face], central, minimum[face + "_cm2"])
    for beam in beams:
        axis = text(beam.get("axis"), "axis")
        story = text(beam.get("story"), "story")
        warnings = []
        if beam.get("support_mapping_verified") is not True:
            warnings.append("Correspondencia caras I/J y apoyos sin verificar")
        if beam.get("single_span_object_verified") is not True:
            warnings.append("Vano unico entre apoyos sin verificar")
        errors = beam.get("design_errors")
        if not isinstance(errors, list):
            warnings.append("Estado de errores de diseno desconocido")
        elif errors:
            warnings.extend(str(e) for e in errors)
        warnings.extend(str(w) for w in beam.get("design_warnings", []))
        if axis in pending_axes:
            warnings.append("Eje con luz pendiente; no proponer corridos globales")
        try:
            minimum = span_minimum(beam.get("clear_span_m"))
        except ValueError as exc:
            results.append({"id": beam["id"], "status": "pending", "reasons": [str(exc)],
                            "structural_approval": False})
            continue
        axis_section = axes.setdefault(axis, {"h_m": 0, "b_m": 0})
        axis_section["h_m"] = max(axis_section["h_m"], minimum["h_m"])
        axis_section["b_m"] = max(axis_section["b_m"], minimum["b_m"])
        groups = unique(beam.get("bars", []))
        provided = {(face, zone): 0.0 for face in FACES for zone in ZONES}
        continuous_count = {face: 0 for face in FACES}
        continuous_area = {face: 0.0 for face in FACES}
        long_addition = {face: 0.0 for face in FACES}
        group_areas = {}
        for group in groups:
            face, role, zones = group.get("face"), group.get("role"), group.get("zones")
            if face not in FACES or role not in ("continuous", "additional"):
                raise ValueError("Cara/rol de barra invalido")
            if not isinstance(zones, list) or not zones or len(set(zones)) != len(zones) or not set(zones) <= set(ZONES):
                raise ValueError("Zonas de barra invalidas")
            if group.get("drawing_verified") is not True:
                warnings.append(f"{group['id']}: recorrido del plano no verificado")
            if role == "continuous" and set(zones) != set(ZONES):
                raise ValueError("Corrido debe cubrir las tres zonas")
            diameter = group.get("diameter_in")
            a = bar_area(diameter, group.get("count"))
            group_areas[group["id"]] = a
            if diameter == "1/2":
                warnings.append(f"{group['id']}: 1/2 fuera de diametros de flexion del perfil")
            if role == "continuous":
                continuous_count[face] += group["count"]
                continuous_area[face] += a
            elif set(zones) == set(ZONES):
                long_addition[face] += a
            for zone in zones:
                provided[face, zone] += a
        count = max(continuous_count.values())
        base_by_count = .25 if count <= 3 else .30 if count <= 5 else None
        if base_by_count is None:
            warnings.append("Base para seis o mas corridas sin definir")
        demand = beam.get("demands", {})
        checks = []
        for face in FACES:
            for zone in ZONES:
                required_etabs = area(demand.get(face, {}).get(zone), unit)
                required = max(required_etabs, minimum[face + "_cm2"] if zone == "center" else 0)
                installed = provided[face, zone]
                deficit = max(0.0, required - installed)
                excess = max(0.0, installed - required)
                sizes = [bar_area(g["diameter_in"], 1) for g in groups
                         if g["face"] == face and zone in g["zones"]]
                # Total additional demand with the current continuous bars; not
                # a recommendation to remove or add several groups independently.
                extra_total = max(0.0, required - continuous_area[face])
                extra_options = proposal(extra_total, face, additional=True)
                actual_extra = [g for g in groups if g["face"] == face and
                                g["role"] == "additional" and zone in g["zones"]]
                diameter_issues = [
                    g["id"] for g in actual_extra if extra_options and
                    g["diameter_in"] != extra_options[0]["diameter_in"]]
                central_target = axis_demands[axis][face]
                if beam.get("drawing_continuous_override_confirmed") is True:
                    central_target = max(area(demand.get(face, {}).get("center"), unit),
                                         minimum[face + "_cm2"])
                continuous_options = proposal(central_target, face, additional=False)
                if face == "bottom" and not beam.get("fixed_section"):
                    diameter_issues.extend(
                        g["id"] for g in groups if g["face"] == face and g["role"] == "continuous"
                        and continuous_options and g["diameter_in"] != continuous_options[0]["diameter_in"])
                checks.append({
                    "face": face, "zone": zone, "required_etabs_cm2": required_etabs,
                    "required_with_span_min_cm2": required, "provided_cm2": installed,
                    "deficit_cm2": deficit, "covers_area": deficit <= 1e-9,
                    "excess_one_bar_or_more": bool(sizes and excess + 1e-9 >= min(sizes)),
                    "continuous_cm2": continuous_area[face],
                    "full_span_additional_cm2": long_addition[face],
                    "total_additional_required_cm2": extra_total,
                    "additional_options": extra_options,
                    "diameter_rule_issues": diameter_issues,
                    "axis_continuous_target_cm2": central_target,
                    "continuous_area_options": [] if beam.get("fixed_section") or axis in pending_axes
                    else continuous_options,
                })
        results.append({"id": beam["id"], "axis": axis, "story": story,
                        "status": "conditional" if warnings else "area_comparison",
                        "warnings": warnings, "span_minimum": minimum,
                        "base_from_continuous_bar_count_m": base_by_count,
                        "physical_bar_areas_cm2": group_areas, "checks": checks,
                        "structural_approval": False})
    return {"beams": results, "axis_min_sections_m": axes,
            "axis_sections_pending": sorted(pending_axes),
            "model_modified": False, "structural_approval": False,
            "scope": "Areas y reglas del perfil; no verifica desarrollo, anclaje, estribos ni elimina errores de diseno"}


def review_torsion_faces(profile: str, data: dict) -> dict:
    """Each record is one face/zone. Never transfer surplus or accept total As."""
    get_procedure(profile)
    if data.get("demand_kind") != "flexure_only":
        raise ValueError("Usar flexure_only; el As total ya incluye torsion y duplicaria la demanda")
    if data.get("torsion_kind") != "longitudinal_area_per_face":
        raise ValueError("torsion_kind debe ser longitudinal_area_per_face; no At/s ni Al total sin reparto")
    if data.get("area_unit") not in AREA_FACTORS:
        raise ValueError("Unidad de area explicita requerida")
    text(data.get("model_source"), "model_source")
    rows = unique(data.get("faces", []))
    if not rows:
        raise ValueError("Faltan caras/zonas")
    results = []
    identities = set()
    for row in rows:
        key = tuple(text(row.get(k), k) for k in ("beam", "story", "zone", "face"))
        if key in identities:
            raise ValueError("Cara/zona duplicada")
        identities.add(key)
        if row["face"] not in FACES or row["zone"] not in ZONES:
            raise ValueError("Cara/zona invalida")
        names = ("flexure_demand", "flexure_provided", "torsion_demand", "torsion_provided")
        if any(row.get(k) is None for k in names):
            results.append({"id": row["id"], "status": "FALTAN DATOS", "structural_approval": False})
            continue
        values = {k: area(row[k], data.get("area_unit")) for k in names}
        surplus = values["flexure_provided"] - values["flexure_demand"]
        lack = max(0.0, values["torsion_demand"] - values["torsion_provided"])
        status = ("FLEXION INSUFICIENTE" if surplus < -1e-9 else
                  "TORSION CUBIERTA" if lack <= 1e-9 else
                  "CUBRE POR AREA" if surplus + 1e-9 >= lack else "NO CUBRE")
        errors = row.get("design_errors")
        detail_verified = row.get("disjoint_bar_allocation_verified") is True
        results.append({"id": row["id"], **values, "status": status,
                        "flexure_surplus_cm2": surplus, "torsion_shortfall_cm2": lack,
                        "design_errors": errors, "bar_allocation_verified": detail_verified,
                        "eligible_for_area_explanation": status == "CUBRE POR AREA" and
                        errors == [] and detail_verified,
                        "structural_approval": False})
    return {"faces": results, "model_modified": False, "structural_approval": False,
            "scope": "Asignacion Al por cara explicita; no se acepta At/s ni se cuenta una barra dos veces"}


def read_design_summary_csv(path: str, area_unit: str, station_unit: str,
                            model_source: str, export_date: str,
                            stations_are_support_faces: bool) -> dict:
    """Read existing CSI summary exports, preserving errors and source age."""
    text(model_source, "model_source")
    text(export_date, "export_date")
    if stations_are_support_faces is not True:
        raise ValueError("Confirmar primera/ultima estacion en caras de apoyo")
    if area_unit not in AREA_FACTORS or station_unit not in ("m", "mm", "cm"):
        raise ValueError("Unidades explicitas de area y estacion requeridas")
    source = Path(path)
    if source.suffix.lower() != ".csv" or source.stat().st_size > 32_000_000:
        raise ValueError("CSV esperado, hasta 32 MB")
    groups = {}
    fields = {"Story", "UniqueName", "DesignSect", "Station", "AsTopTotal",
              "AsBotTotal", "WarnMsg", "ErrMsg"}
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not fields <= set(reader.fieldnames or []):
            raise ValueError("CSV no es Design Summary con AsTopTotal/AsBotTotal; flexenv no equivale")
        for row in reader:
            identity = (text(row["Story"], "Story"), text(row["UniqueName"], "UniqueName"))
            group = groups.setdefault(identity, {"rows": [], "errors": set(),
                                                 "warnings": set(), "section": row["DesignSect"]})
            if row["DesignSect"] != group["section"]:
                raise ValueError("Seccion inconsistente dentro de la misma viga")
            factor = {"m": 1, "mm": .001, "cm": .01}[station_unit]
            group["rows"].append((number(float(row["Station"]), "Station") * factor,
                                  area(float(row["AsTopTotal"]), area_unit),
                                  area(float(row["AsBotTotal"]), area_unit)))
            for column, key in (("ErrMsg", "errors"), ("WarnMsg", "warnings")):
                msg = row[column].strip()
                if not msg:
                    group[key].add("Estado no informado")
                elif msg.casefold() not in ("no message", "none"):
                    group[key].add(msg)
    output = []
    for (story, name), group in groups.items():
        rows = group["rows"]
        lo, hi = min(r[0] for r in rows), max(r[0] for r in rows)
        if hi <= lo:
            raise ValueError(f"{name}: no hay luz entre caras")
        selections = {"i": [r for r in rows if r[0] == lo],
                      "j": [r for r in rows if r[0] == hi],
                      "center": [r for r in rows if lo + (hi-lo)/4 <= r[0] <= lo + 3*(hi-lo)/4]}
        if not selections["center"]:
            raise ValueError(f"{name}: faltan estaciones centrales")
        output.append({"id": f"{story}/{name}", "story": story, "source_object": name,
                       "section": group["section"], "clear_span_m": hi-lo,
                       "demands": {face: {zone: max(r[i] for r in selected)
                                          for zone, selected in selections.items()}
                                   for i, face in ((1, "top"), (2, "bottom"))},
                       "design_errors": sorted(group["errors"]),
                       "design_warnings": sorted(group["warnings"]),
                       "support_mapping_verified": False, "single_span_object_verified": False})
    if not output:
        raise ValueError("CSV sin filas")
    return {"model_source": model_source, "export_date": export_date,
            "source_area_unit": area_unit, "area_unit": "cm2",
            "demand_kind": "total_longitudinal", "beams": output,
            "live_read": False, "requires_drawing_mapping_and_bars": True}
