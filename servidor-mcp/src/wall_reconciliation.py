"""Compare reported wall inputs, never invent bar counts, laps or cut lengths."""

import math


def length_unit(units):
    """CSI eUnits length component and millimetres per unit."""
    names = (
        "in",
        "ft",
        "in",
        "ft",
        "mm",
        "m",
        "mm",
        "m",
        "mm",
        "m",
        "mm",
        "m",
        "cm",
        "cm",
        "cm",
        "cm",
    )
    if type(units) is not int or not 1 <= units <= len(names):
        raise ValueError("Unidades CSI desconocidas")
    name = names[units - 1]
    return name, {"in": 25.4, "ft": 304.8, "mm": 1.0, "m": 1000.0, "cm": 10.0}[name]


def _number(value, *, positive=False):
    if isinstance(value, bool):
        raise TypeError("Booleano no es una medida")
    try:
        n = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Medida ausente/no numerica") from error
    if not math.isfinite(n) or n < 0 or positive and n == 0:
        raise ValueError("Medida fuera de rango")
    return n


def _equal(a, b):
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)


def reconcile_layers(area_data, summary_rows, overwrites, display_units):
    """Uniform checked sections only. Areas use DB units in verified ETABS 23.3.

    Equality means equality of compared inputs, not physical equivalence. The
    native generator can derive layers and default covers; it is not a BBS.
    Horizontal density is compared only with reported ShearAv (area/length),
    not with the vertical section spacing. CSI display precision is retained.
    """
    result = {
        "status": "not_evaluated",
        "layers": [],
        "issues": [],
        "complete_detailing": False,
        "engineering_approval": False,
        "missing_for_complete_detailing": [
            "native_bar_ids",
            "bar_counts",
            "cut_lengths",
            "shapes",
            "hooks",
            "laps",
            "anchorage",
            "verified_native_detail_export",
        ],
        "limitation": "Comparacion numerica de entradas reportadas; mas acero por "
        "longitud no demuestra equivalencia de seccion ni detalle fabricable.",
    }
    if area_data.get("units_verified") is not True:
        result["issues"].append("Unidades de capas no verificadas para esta version")
        return result
    _, native_scale = length_unit(area_data["units_enum"])
    _, display_scale = length_unit(display_units)
    expected = {(r["Story"], r["Pier"]) for r in summary_rows}
    observed = {
        (a["StoryName"], a["PierLabel"]) for a in area_data["areas"] if a["layers"]
    }
    if expected - observed:
        result["issues"].append("Faltan capas para uno o mas story/pier del resumen")
    for area in area_data["areas"]:
        pair = area["StoryName"], area["PierLabel"]
        identity = {
            "AreaObjName": area["AreaObjName"],
            "Story": pair[0],
            "Pier": pair[1],
        }
        rows = [r for r in summary_rows if (r.get("Story"), r.get("Pier")) == pair]
        settings = [r for r in overwrites if (r.get("Story"), r.get("Pier")) == pair]
        try:
            if not rows or len(settings) != 1:
                raise ValueError("Resumen/overwrite ausente o ambiguo")
            setting = settings[0]
            if setting.get("PierSecType") != "Uniform Reinforcing Section":
                raise ValueError("Solo se comparan secciones uniformes comprobadas")
            signatures = {
                (r.get("EdgeBar"), r.get("EndBar"), r.get("BarSpacing")) for r in rows
            }
            if len(signatures) != 1:
                raise ValueError("Armados distintos entre estaciones")
            bar, end_bar, raw_spacing = next(iter(signatures))
            if (
                not bar
                or bar != end_bar
                or bar != setting.get("EdgeBar")
                or bar != setting.get("EndBar")
            ):
                raise ValueError("Barras de borde/extremo distintas o no conciliables")
            spacing = _number(raw_spacing, positive=True) * display_scale
            if not _equal(
                spacing,
                _number(setting.get("EdgeBarSpc"), positive=True) * display_scale,
            ):
                raise ValueError("Overwrite difiere del resultado de diseno")
            cover = _number(setting.get("ClearCover"), positive=True) * display_scale
            for row in rows:
                _number(row.get("DCRatio"))  # Absent check results are not zero.
            shear = max(_number(r.get("ShearAv")) for r in rows) * display_scale
            if not area["layers"]:
                raise ValueError("Area sin capas")
            for layer in area["layers"]:
                kind = layer["LayerType"]
                if kind not in (1, 2):
                    raise ValueError(
                        "Capa de borde/confinamiento/diagonal fuera de esta comparacion"
                    )
                ls = _number(layer["BarSpacing"], positive=True) * native_scale
                lc = _number(layer["ClearCover"]) * native_scale
                density = (
                    2 * _number(layer["BarArea"], positive=True) * native_scale**2 / ls
                )
                item = {
                    **identity,
                    "LayerType": kind,
                    "bar_size": layer["BarSizeName"],
                    "layer_spacing_mm": ls,
                    "layer_cover_raw_mm": lc,
                    "checked_cover_mm": cover,
                    "cover_matches": _equal(lc, cover),
                    "distributed_area_mm2_per_mm_two_faces": density,
                }
                if kind == 1:
                    item.update(
                        checked_bar_size=bar,
                        checked_spacing_mm=spacing,
                        bar_size_matches=layer["BarSizeName"] == bar,
                        spacing_matches=_equal(ls, spacing),
                    )
                else:
                    item.update(
                        reported_shear_area_mm2_per_mm=shear,
                        shear_area_comparison=(
                            "below_reported_demand"
                            if density < shear
                            else "not_below_reported_demand"
                        ),
                    )
                result["layers"].append(item)
        except (ValueError, TypeError) as error:
            result["issues"].append({**identity, "reason": str(error)})
    if result["layers"] and not result["issues"]:
        different = any(
            r["cover_matches"] is False
            or r.get("bar_size_matches") is False
            or r.get("spacing_matches") is False
            or r.get("shear_area_comparison") == "below_reported_demand"
            for r in result["layers"]
        )
        result["status"] = "differences" if different else "compared_inputs_match"
    return result
