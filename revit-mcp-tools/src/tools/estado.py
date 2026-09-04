# -*- coding: utf-8 -*-
"""estado: documento activo, unidades, niveles, conteo estructural y advertencias.

Sustituye al pushbutton _Estado (que solo comprobaba el servidor de routes:
si esta tool responde, el canal esta vivo) y da lo minimo para orientarse
antes de escribir.
"""


def run(doc, uidoc, DB, P):
    out = {"document": doc.Title, "path": None, "modified": None,
           "units_length": None, "levels": [], "counts": {}, "warnings": None}
    try:
        out["path"] = doc.PathName
    except Exception:
        pass
    try:
        out["modified"] = doc.IsModified
    except Exception:
        pass
    try:
        out["units_length"] = str(doc.GetUnits().GetFormatOptions(DB.SpecTypeId.Length).GetUnitTypeId().TypeId)
    except Exception:
        pass
    for lv in sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation):
        out["levels"].append({"name": lv.Name, "elevation_mm": mm(lv.Elevation)})
    cats = [("columns", DB.BuiltInCategory.OST_StructuralColumns),
            ("framing", DB.BuiltInCategory.OST_StructuralFraming),
            ("floors", DB.BuiltInCategory.OST_Floors),
            ("walls", DB.BuiltInCategory.OST_Walls),
            ("foundations", DB.BuiltInCategory.OST_StructuralFoundation),
            ("rebar", DB.BuiltInCategory.OST_Rebar),
            ("grids", DB.BuiltInCategory.OST_Grids),
            ("sheets", DB.BuiltInCategory.OST_Sheets)]
    for k, bic in cats:
        try:
            out["counts"][k] = collector(doc, bic).GetElementCount()
        except Exception:
            out["counts"][k] = None
    try:
        out["warnings"] = len(doc.GetWarnings())
    except Exception:
        pass
    try:
        av = uidoc.ActiveView if uidoc is not None else doc.ActiveView
        out["active_view"] = {"name": av.Name, "type": str(av.ViewType)} if av is not None else None
    except Exception:
        out["active_view"] = None
    return out
