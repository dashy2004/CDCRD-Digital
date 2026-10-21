"""Explicit project procedure: deterministic plans/checks, no COM or file writes."""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import json
import math
from pathlib import Path, PureWindowsPath

PROFILE_ID = "modeling_20261015"
G_STANDARD = 9.80665  # force-unit conversion; distinct from the profile's 9.81


def number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name}: se requiere numero finito, no booleano ni texto")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name}: valor fuera de rango")
    return float(value)


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name}: se requiere true/false explicito")
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: falta texto")
    return value


def unique(items, key="id"):
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Se requiere una lista de objetos")
    seen = set()
    for item in items:
        name = text(item.get(key), key)
        if name.casefold() in seen:
            raise ValueError(f"{key} duplicado: {name}")
        seen.add(name.casefold())
    return items


def get_procedure(profile: str) -> dict:
    """Seleccionar un perfil no autoriza aplicarlo a un modelo."""
    if profile != PROFILE_ID:
        raise ValueError(f"Perfil desconocido; seleccione explicitamente {PROFILE_ID}")
    path = Path(__file__).with_name("profiles") / f"{profile}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def ceil_step(value, step=0.05):
    """Ceiling once, tolerating only <=1e-12 input arithmetic residue."""
    value = number(value, "valor")
    step = number(step, "incremento", positive=True)
    v, s = Decimal(str(value)), Decimal(str(step))
    nearest = (v / s).to_integral_value(rounding=ROUND_HALF_UP) * s
    if abs(v - nearest) <= Decimal("1e-12"):
        return float(nearest)
    return float((v / s).to_integral_value(rounding=ROUND_CEILING) * s)


def load_to_tfm2(value, unit):
    factors = {"tonf/m2": 1, "kgf/m2": 0.001,
               "kN/m2": 1 / G_STANDARD, "N/mm2": 1000 / G_STANDARD}
    if unit not in factors:
        raise ValueError("Unidad superficial explicita: tonf/m2, kgf/m2, kN/m2 o N/mm2")
    return number(value, "carga") * factors[unit]


def verify_spectrum(samples: list[dict], scale_mps2: float,
                    required_periods_s: list[float]) -> dict:
    """Compare actual function ordinates to Excel at identical periods in SI."""
    scale = number(scale_mps2, "scale_mps2", positive=True)
    if len(samples) < 3 or len(required_periods_s) < 3:
        raise ValueError("Se requieren al menos tres periodos, incluidos cambios de rama")
    periods, errors = [], []
    for row in samples:
        t = number(row.get("period_s"), "period_s")
        if periods and t <= periods[-1]:
            raise ValueError("Periodos estrictamente crecientes, sin duplicados")
        periods.append(t)
        target = number(row.get("excel_sa_mps2"), "excel_sa_mps2")
        value = number(row.get("function_ordinate"), "function_ordinate") * scale
        errors.append({"period_s": t, "actual_mps2": value, "target_mps2": target,
                       "absolute_error_mps2": abs(value - target),
                       "matches": abs(value - target) <= 1e-6 + 1e-5 * target})
    required = [number(t, "periodo requerido") for t in required_periods_s]
    if len(set(required)) != len(required):
        raise ValueError("Periodos requeridos duplicados")
    if any(not any(abs(t - p) < 1e-9 for p in periods) for t in required):
        raise ValueError("Faltan periodos requeridos; no se extrapola ni interpola")
    if not any(row["target_mps2"] > 0 for row in errors):
        raise ValueError("Espectro de referencia vacio/cero")
    return {"matches": all(row["matches"] for row in errors), "points": errors,
            "scope": "Solo periodos aportados; no verifica normativa ni parametros del sitio"}


def prepare_modeling(profile: str, project: dict) -> dict:
    """Produce a desired-state plan. Never execute setters or choose seismic data."""
    p = get_procedure(profile)
    if not isinstance(project, dict):
        raise ValueError("project debe ser un objeto")
    if project.get("usage") != "residential":
        raise ValueError("Factores residenciales del perfil: otro uso requiere otro criterio")
    parking = boolean(project.get("has_parking"), "has_parking")
    path = PureWindowsPath(text(project.get("model_path"), "model_path"))
    if not path.is_absolute() or path.suffix.lower() != ".edb":
        raise ValueError("Se requiere ruta absoluta .EDB; no se abre ni guarda el archivo")
    stories = unique(project.get("stories", []), "name")
    if not stories or any(s["name"].casefold() == "base" for s in stories):
        raise ValueError("stories debe contener los entrepisos sobre Base, sin incluir Base")
    elevation, planned_stories = 0.0, []
    for i, story in enumerate(stories):
        h = number(story.get("architectural_height_m"), "architectural_height_m", positive=True)
        model_h = h + (p["first_story_increment_m"] if i == 0 else 0)
        elevation += model_h
        planned_stories.append({"name": story["name"], "source_height_m": h,
                                "model_height_m": model_h, "elevation_m": elevation})
    patterns = [{"name": "Dead", "type": "Dead", "self_weight": 1.0}]
    for name in ["Live", "LiveT"] + (["LiveP"] if parking else []):
        patterns.append({"name": name, "type": "Live", "self_weight": 0.0})
    for name, direction in [("Qx", "X"), ("Qy", "Y")]:
        patterns.append({"name": name, "type": "Seismic", "self_weight": 0.0,
                         "code": p["seismic_policy"]["code"], "direction": direction,
                         "eccentricity": 0.05, "eccentricity_signs": ["+", "-"],
                         "bottom": "Base", "top": stories[-1]["name"],
                         "period_method": "Program Calculated"})
    mass, pd = deepcopy(p["mass_source"]), deepcopy(p["pdelta"])
    if parking:
        mass["factors"]["LiveP"] = 0.25
        pd["factors"]["LiveP"] = 1.6
    needed = ["Comprobar arquitectura, Excel recalculado y seleccion de este perfil",
              "Aplicacion nativa, Check Model completo y persistencia por verificar"]
    seismic = project.get("seismic")
    spectrum = None
    if seismic is None:
        needed.append("Faltan parametros sismicos del proyecto y curva nativa frente a Excel")
    else:
        if not isinstance(seismic, dict):
            raise ValueError("seismic debe ser un objeto")
        values = {k: number(seismic.get(k), k, positive=True)
                  for k in ("ss_g", "s1_g", "fa", "fv", "u", "rd")}
        boolean(seismic.get("near_fault"), "near_fault")
        text(seismic.get("source"), "fuente sismica")
        for key in ("reentrant", "nonorthogonal", "torsion"):
            if seismic.get(key) not in ("yes", "no", "pending"):
                raise ValueError(f"{key}: yes, no o pending explicito")
            if seismic[key] == "pending":
                needed.append(f"{key}: decision pendiente; espectro provisional")
        for pattern in patterns[-2:]:
            pattern["parameters"] = values.copy()
        spectrum = {
            "name": "MOPC", "type": p["seismic_policy"]["code"],
            "source": values, "function_parameters": {
                **values, "ss": values["ss_g"] * 9.81, "s1": values["s1_g"] * 9.81},
            "near_fault": seismic["near_fault"], "damping": 0.05,
            "conversion_basis": p["seismic_policy"]["function_multiplier_basis"],
            "cases": [], "curve_verification": None,
        }
        if seismic.get("samples") is None or seismic.get("scale_mps2") is None:
            needed.append("F y curva generada faltantes; no se asume otro factor g ni U/Rd")
        else:
            evidence = verify_spectrum(seismic["samples"], seismic["scale_mps2"],
                                       seismic.get("required_periods_s", []))
            spectrum["curve_verification"] = evidence
            if not evidence["matches"]:
                needed.append("Curva MOPC por F no coincide con Excel: resolver antes de aplicar")
            else:
                f = seismic["scale_mps2"]
                for name, primary, transverse in [("EX", "U1", "U2"), ("EY", "U2", "U1")]:
                    spectrum["cases"].append({
                        "name": name, "modal_case": "Modal", "modal_combination": "CQC",
                        "directional_combination": "SRSS", "damping": 0.05,
                        "eccentricity": 0, "rigid_response": False,
                        "design_type": "Program Determined",
                        "loads": [{"direction": d, "function": "MOPC", "scale_mps2": sf,
                                   "coordinate_system": "Global", "angle_deg": 0}
                                  for d, sf in [(primary, f), (transverse, 0.3 * f)]]})
    return {"profile": profile, "operation": "plan_only", "model_path": str(path),
            "units": p["units"], "base_elevation_m": 0, "stories": planned_stories,
            "patterns": patterns, "mass_source": mass, "pdelta": pd,
            "modal_max_modes": 3 * len(stories), "spectrum": spectrum,
            "library": {k: p[k] for k in ("materials", "rebar_definitions",
                                         "slab_common", "slab_definitions", "frame_preferences")},
            "pending": needed, "analysis_authorized": False, "model_modified": False}


def calculate_loads(profile: str, data: dict) -> dict:
    """Calculate components separately; unknowns never become zero loads."""
    p = get_procedure(profile)
    if not isinstance(data, dict):
        raise ValueError("data debe ser un objeto")
    parking = boolean(data.get("has_parking"), "has_parking")
    slabs, walls, water = [], [], []
    for slab in unique(data.get("slabs", [])):
        sid = slab["id"]
        if slab.get("is_opening") is not False:
            raise ValueError(f"{sid}: confirmar que no sea un hueco")
        if slab.get("support") not in ("supported", "cantilever"):
            raise ValueError(f"{sid}: support debe distinguir supported/cantilever")
        name = slab.get("set")
        if name not in p["load_sets"]:
            raise ValueError(f"{sid}: set desconocido")
        if slab.get("architecture_set") != name:
            raise ValueError(f"{sid}: arquitectura y set no coinciden")
        if name == "Parqueos" and not parking:
            raise ValueError("Parqueos requiere has_parking=true")
        definition = deepcopy(p["load_sets"][name])
        excel_live = load_to_tfm2(slab.get("excel_live"), slab.get("unit"))
        if definition["live_tfm2"] is None:
            # Special project loads cannot be copied from the historical project.
            definition["live_tfm2"] = number(slab.get("confirmed_live_tfm2"),
                                             "confirmed_live_tfm2")
        if not math.isclose(excel_live, definition["live_tfm2"], abs_tol=1e-9):
            raise ValueError(f"{sid}: carga viva Excel y set no coinciden")
        existing = slab.get("existing_components")
        if not isinstance(existing, list):
            raise ValueError(f"{sid}: aportar existing_components; [] significa ausencia verificada")
        if any(x in existing for x in ("finishes", "live", "masonry", "structural_self_weight")):
            raise ValueError(f"{sid}: componentes ya asignados; reconciliar antes de repetir")
        if slab["support"] == "cantilever":
            raw, assigned = 0.0, 0.0
        else:
            raw = load_to_tfm2(slab.get("excel_masonry"), slab.get("unit"))
            assigned = ceil_step(max(raw, p["supported_slab_masonry_min_tfm2"]))
        slabs.append({"id": sid, "set": name, **definition, "direction": "Gravity",
                      "masonry_calculated_tfm2": raw, "masonry_assigned_tfm2": assigned,
                      "structural_self_weight_from_pattern": True})
    intervals = {}
    for wall in unique(data.get("walls_on_beams", [])):
        beam = text(wall.get("beam"), "beam")
        a, b = number(wall.get("start"), "start"), number(wall.get("end"), "end")
        if not 0 <= a < b <= 1:
            raise ValueError("Intervalo relativo de pared invalido")
        depth = number(wall.get("beam_depth_m"), "beam_depth_m", positive=True)
        thickness = number(wall.get("thickness_m"), "thickness_m", positive=True)
        heights = [number(wall.get(key), key, positive=True)
                   for key in ("space_above_start_m", "space_above_end_m")]
        if min(heights) < depth:
            raise ValueError("Altura superior menor que el peralte")
        raw = [(h - depth) * thickness * p["masonry_weight_tfm3"] for h in heights]
        assigned = [ceil_step(x) for x in raw]
        if boolean(wall.get("reverse_ij"), "reverse_ij"):
            a, b, raw, assigned = 1 - b, 1 - a, raw[::-1], assigned[::-1]
        if any(max(a, c) < min(b, d) - 1e-12 for c, d in intervals.get(beam, [])):
            raise ValueError(f"{beam}: intervalos de mamposteria solapados")
        intervals.setdefault(beam, []).append((a, b))
        walls.append({"id": wall["id"], "beam": beam, "start": a, "end": b,
                      "calculated_tfm": raw, "assigned_tfm": assigned, "pattern": "Dead"})
    for item in unique(data.get("water", [])):
        area = number(item.get("wet_horizontal_area_m2"), "wet_horizontal_area_m2", positive=True)
        depth = number(item.get("mean_depth_m"), "mean_depth_m", positive=True)
        application = number(item.get("application_horizontal_area_m2"),
                             "application_horizontal_area_m2", positive=True)
        equivalent = boolean(item.get("equivalent_over_dry_area"), "equivalent_over_dry_area")
        if application < area or (not equivalent and not math.isclose(application, area)):
            raise ValueError("Agua: area de aplicacion incompatible; equivalencia debe ser explicita")
        if item.get("existing_water_assigned") is not False:
            raise ValueError("Agua: verificar que no haya una asignacion previa")
        weight = area * depth * p["water_weight_tfm3"]
        water.append({"id": item["id"], "water_volume_m3": area * depth,
                      "weight_tf": weight, "load_tfm2": weight / application,
                      "pattern": "Dead", "equivalent_over_dry_area": equivalent})
    if not (slabs or walls or water):
        raise ValueError("No hay componentes de carga")
    return {"slabs": slabs, "walls_on_beams": walls, "water": water,
            "operation": "calculation_only", "model_modified": False}


def grouped_masonry_totals(totals_by_story: dict) -> dict:
    """Max of complete totals per slab/thickness, never a sum across floors."""
    if not totals_by_story:
        raise ValueError("Faltan plantas")
    keys = None
    for story, totals in totals_by_story.items():
        text(story, "story")
        if not isinstance(totals, dict) or not totals:
            raise ValueError("Faltan totales completos por losa/espesor")
        if keys is not None and set(totals) != keys:
            raise ValueError("Plantas agrupadas con losas/espesores faltantes")
        keys = set(totals)
        for key, value in totals.items():
            number(value, key)  # None means unmeasured, not an absent wall.
    return {key: {"length_m": max(rows[key] for rows in totals_by_story.values()),
                  "governing_stories": [story for story, rows in totals_by_story.items()
                                       if rows[key] == max(r[key] for r in totals_by_story.values())]}
            for key in sorted(keys)}
