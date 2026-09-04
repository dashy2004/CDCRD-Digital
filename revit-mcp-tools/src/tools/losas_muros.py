# -*- coding: utf-8 -*-
"""losas_muros: inventario de losas y muros con tipo, espesor, nivel, area y extremos.

Version generica del pushbutton _LosasMuros. Parametros:
  max_rows: tope por categoria (default 300).
"""


def run(doc, uidoc, DB, P):
    max_rows = int(P.get("max_rows", 300))
    out = {"document": doc.Title, "losas": [], "muros": [],
           "resumen_losas": {}, "resumen_muros": {}}
    for f in collector(doc, DB.BuiltInCategory.OST_Floors):
        tn = type_name(doc, f) or "?"
        ft = doc.GetElement(f.GetTypeId())
        row = {"id": eidv(f.Id), "type": tn, "level": level_name(doc, f.LevelId),
               "thickness_mm": None, "area_m2": None, "structural": None, "comment": comment(f)}
        try:
            row["thickness_mm"] = mm(ft.GetCompoundStructure().GetWidth())
        except Exception:
            pass
        try:
            pa = f.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
            row["area_m2"] = round(pa.AsDouble() * 0.09290304, 3) if pa is not None else None
        except Exception:
            pass
        try:
            ps = f.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
            row["structural"] = bool(ps.AsInteger()) if ps is not None else None
        except Exception:
            pass
        r = out["resumen_losas"].setdefault(tn, {"n": 0, "area_m2": 0.0})
        r["n"] += 1
        r["area_m2"] += row["area_m2"] or 0.0
        if len(out["losas"]) < max_rows:
            out["losas"].append(row)
    for w in DB.FilteredElementCollector(doc).OfClass(DB.Wall):
        tn = type_name(doc, w) or "?"
        wt = doc.GetElement(w.GetTypeId())
        row = {"id": eidv(w.Id), "type": tn, "base_level": level_name(doc, w.LevelId),
               "top_level": None, "width_mm": None, "length_mm": None, "p0": None, "p1": None,
               "structural_usage": None, "comment": comment(w)}
        try:
            row["width_mm"] = mm(wt.Width)
        except Exception:
            pass
        try:
            pt = w.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE)
            row["top_level"] = level_name(doc, pt.AsElementId()) if pt is not None else None
        except Exception:
            pass
        c = location_curve(w)
        if c is not None:
            a = c.GetEndPoint(0)
            z = c.GetEndPoint(1)
            row["p0"] = [mm(a.X), mm(a.Y)]
            row["p1"] = [mm(z.X), mm(z.Y)]
            row["length_mm"] = mm(c.Length)
        try:
            row["structural_usage"] = str(w.StructuralUsage)
        except Exception:
            pass
        r = out["resumen_muros"].setdefault(tn, {"n": 0, "length_mm": 0.0})
        r["n"] += 1
        r["length_mm"] += row["length_mm"] or 0.0
        if len(out["muros"]) < max_rows:
            out["muros"].append(row)
    for d in (out["resumen_losas"], out["resumen_muros"]):
        for k in d:
            for kk in d[k]:
                if isinstance(d[k][kk], float):
                    d[k][kk] = round(d[k][kk], 2)
    return out
