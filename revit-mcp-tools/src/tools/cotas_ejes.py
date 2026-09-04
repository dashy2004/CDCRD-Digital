# -*- coding: utf-8 -*-
"""cotas_ejes: cadenas de cotas entre ejes en una vista de planta.

Tres cadenas: ejes en X (arriba), ejes en Y (a la izquierda) y total en Y.
Parametros:
  view_name:  vista; vacio = activa.
  offset_mm:  separacion de la cadena respecto al eje extremo (default 2500).
  dim_type:   nombre del DimensionType (opcional; vacio = el default de Revit).
  replace:    True borra las cotas existentes de la vista antes de crear.
"""


def run(doc, uidoc, DB, P):
    view = active_or_named_view(doc, uidoc, P.get("view_name"))
    off = float(P.get("offset_mm", 2500.0)) / FT
    dname = P.get("dim_type") or ""
    dtype = None
    if dname:
        dtype = next((d for d in DB.FilteredElementCollector(doc).OfClass(DB.DimensionType) if element_name(d) == dname), None)
        if dtype is None:
            raise Exception("no existe el DimensionType '%s'" % dname)
    grids = list(DB.FilteredElementCollector(doc).OfClass(DB.Grid))
    gx = sorted([g for g in grids if abs(g.Curve.GetEndPoint(0).X - g.Curve.GetEndPoint(1).X) < 1e-6], key=lambda g: g.Curve.GetEndPoint(0).X)
    gy = sorted([g for g in grids if abs(g.Curve.GetEndPoint(0).Y - g.Curve.GetEndPoint(1).Y) < 1e-6], key=lambda g: g.Curve.GetEndPoint(0).Y)
    if len(gx) < 2 or len(gy) < 2:
        raise Exception("hacen falta al menos dos ejes en cada direccion")
    z = view.GenLevel.Elevation if getattr(view, "GenLevel", None) else 0.0
    out = {"view": view.Name, "creadas": 0, "borradas": 0}

    def dim(line, gs):
        ra = DB.ReferenceArray()
        for g in gs:
            ra.Append(DB.Reference(g))
        if dtype is None:
            return doc.Create.NewDimension(view, line, ra)
        return doc.Create.NewDimension(view, line, ra, dtype)

    def work():
        if P.get("replace"):
            for d in list(DB.FilteredElementCollector(doc, view.Id).OfClass(DB.Dimension)):
                doc.Delete(d.Id)
                out["borradas"] += 1
        ytop = max(g.Curve.GetEndPoint(0).Y for g in gy) + off
        dim(DB.Line.CreateBound(DB.XYZ(gx[0].Curve.GetEndPoint(0).X, ytop, z), DB.XYZ(gx[-1].Curve.GetEndPoint(0).X, ytop, z)), gx)
        out["creadas"] += 1
        xleft = min(g.Curve.GetEndPoint(0).X for g in gx) - off
        y0 = gy[0].Curve.GetEndPoint(0).Y
        y1 = gy[-1].Curve.GetEndPoint(0).Y
        dim(DB.Line.CreateBound(DB.XYZ(xleft, y0, z), DB.XYZ(xleft, y1, z)), gy)
        out["creadas"] += 1
        x2 = xleft - 1200 / FT
        dim(DB.Line.CreateBound(DB.XYZ(x2, y0, z), DB.XYZ(x2, y1, z)), [gy[0], gy[-1]])
        out["creadas"] += 1
    tx(doc, "tools: cotas a ejes", work)
    out["ok"] = True
    return out
