# -*- coding: utf-8 -*-
"""inventario: conteo de elementos estructurales por categoria, tipo y nivel.

Version generica del pushbutton _Inventario (que ademas indexaba acero por
anfitrion). Parametros:
  categories: lista de nombres cortos ("columns","framing","floors","walls",
              "foundations","rebar"); por defecto los cinco primeros.
  by_level:   True para desglosar por nivel de referencia.
"""


def run(doc, uidoc, DB, P):
    CATS = {"columns": DB.BuiltInCategory.OST_StructuralColumns,
            "framing": DB.BuiltInCategory.OST_StructuralFraming,
            "floors": DB.BuiltInCategory.OST_Floors,
            "walls": DB.BuiltInCategory.OST_Walls,
            "foundations": DB.BuiltInCategory.OST_StructuralFoundation,
            "rebar": DB.BuiltInCategory.OST_Rebar}
    wanted = P.get("categories") or ["columns", "framing", "floors", "walls", "foundations"]
    by_level = bool(P.get("by_level", False))
    out = {"document": doc.Title, "categories": {}}
    for k in wanted:
        bic = CATS.get(k)
        if bic is None:
            out["categories"][k] = {"error": "categoria desconocida"}
            continue
        by_type = {}
        by_lvl = {}
        total = 0
        for e in collector(doc, bic):
            total += 1
            tn = type_name(doc, e) or "?"
            by_type[tn] = by_type.get(tn, 0) + 1
            if by_level:
                ln = None
                try:
                    ln = level_name(doc, e.LevelId)
                except Exception:
                    pass
                if ln is None:
                    for bip in (DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
                                DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                                DB.BuiltInParameter.LEVEL_PARAM):
                        try:
                            p = e.get_Parameter(bip)
                            if p is not None:
                                ln = level_name(doc, p.AsElementId())
                                if ln:
                                    break
                        except Exception:
                            pass
                ln = ln or "?"
                by_lvl.setdefault(ln, {})
                by_lvl[ln][tn] = by_lvl[ln].get(tn, 0) + 1
        entry = {"total": total, "by_type": by_type}
        if by_level:
            entry["by_level"] = by_lvl
        out["categories"][k] = entry
    return out
