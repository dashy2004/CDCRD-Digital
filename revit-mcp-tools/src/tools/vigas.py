# -*- coding: utf-8 -*-
"""vigas: listado de vigas con tipo, nivel, extremos, longitud, material y comentario.

Version generica del pushbutton _Vigas (que ademas contaba sets de acero por
viga; aqui rebar_sets solo si include_rebar=True). Parametros:
  view_name:     limitar a las vigas visibles en esa vista (opcional).
  include_rebar: contar barras hospedadas en cada viga (lento en modelos grandes).
  max_rows:      tope de filas devueltas (default 500); el resumen es siempre completo.
"""


def run(doc, uidoc, DB, P):
    view = find_view(doc, P["view_name"]) if P.get("view_name") else None
    if P.get("view_name") and view is None:
        raise Exception("no existe la vista '%s'" % P["view_name"])
    include_rebar = bool(P.get("include_rebar", False))
    max_rows = int(P.get("max_rows", 500))
    host_count = {}
    if include_rebar:
        for rb in collector(doc, DB.BuiltInCategory.OST_Rebar):
            try:
                h = eidv(rb.GetHostId())
                host_count[h] = host_count.get(h, 0) + 1
            except Exception:
                pass
    rows = []
    resumen = {}
    for b in collector(doc, DB.BuiltInCategory.OST_StructuralFraming, view):
        tn = type_name(doc, b) or "?"
        c = location_curve(b)
        row = {"id": eidv(b.Id), "type": tn, "level": None, "length_mm": None,
               "p0": None, "p1": None, "material": None, "comment": comment(b)}
        try:
            p = b.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            row["level"] = level_name(doc, p.AsElementId()) if p is not None else None
        except Exception:
            pass
        if c is not None:
            a = c.GetEndPoint(0)
            z = c.GetEndPoint(1)
            row["p0"] = [mm(a.X), mm(a.Y), mm(a.Z)]
            row["p1"] = [mm(z.X), mm(z.Y), mm(z.Z)]
            row["length_mm"] = mm(c.Length)
        try:
            pm = b.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
            if pm is not None:
                row["material"] = element_name(doc.GetElement(pm.AsElementId()))
        except Exception:
            pass
        if include_rebar:
            row["rebar_sets"] = host_count.get(row["id"], 0)
        r = resumen.setdefault(tn, {"n": 0, "length_mm": 0.0})
        r["n"] += 1
        r["length_mm"] += row["length_mm"] or 0.0
        if len(rows) < max_rows:
            rows.append(row)
    for k in resumen:
        resumen[k]["length_mm"] = round(resumen[k]["length_mm"], 1)
    return {"document": doc.Title, "view": view.Name if view else None,
            "total": sum(v["n"] for v in resumen.values()),
            "resumen_por_tipo": resumen, "vigas": rows,
            "truncated": len(rows) >= max_rows}
