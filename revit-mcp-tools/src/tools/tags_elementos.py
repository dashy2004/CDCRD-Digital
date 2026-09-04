# -*- coding: utf-8 -*-
"""tags_elementos: etiqueta columnas, losas o muros de una vista.

Complementa a tags_vigas para las otras tres categorias (columnas a 45 grados
opcional, losas por centro de caja, muros con desplazamiento). Parametros:
  category:   "columns" | "floors" | "walls" (obligatorio).
  view_name:  vista destino; vacio = vista activa.
  tag_type:   nombre del tipo de tag; vacio = el primero cargado de esa categoria.
  offset_mm:  desplazamiento del texto (default 420 columnas, 450 muros, 0 losas).
  angle_deg:  rotacion del tag (default 45 para columnas en planta, 0 el resto).
  replace:    True borra los tags previos de esa categoria en la vista.
Los tags de columna y losa muestran el Type Name; el de muro el Type Mark.
"""


def run(doc, uidoc, DB, P):
    import math
    cat = P.get("category")
    CATS = {"columns": (DB.BuiltInCategory.OST_StructuralColumns, DB.BuiltInCategory.OST_StructuralColumnTags, "Structural Column Tags", 420.0, 45.0),
            "floors": (DB.BuiltInCategory.OST_Floors, DB.BuiltInCategory.OST_FloorTags, "Floor Tags", 0.0, 0.0),
            "walls": (DB.BuiltInCategory.OST_Walls, DB.BuiltInCategory.OST_WallTags, "Wall Tags", 450.0, 0.0)}
    if cat not in CATS:
        raise Exception("category debe ser columns, floors o walls")
    bic, tbic, tcatname, def_off, def_ang = CATS[cat]
    view = active_or_named_view(doc, uidoc, P.get("view_name"))
    is_plan = str(view.ViewType) in ("FloorPlan", "EngineeringPlan", "CeilingPlan")
    want = P.get("tag_type") or ""
    tag = None
    for s in DB.FilteredElementCollector(doc).OfCategory(tbic).WhereElementIsElementType():
        if not want or element_name(s) == want:
            tag = s
            break
    if tag is None:
        raise Exception("no hay tipo de tag cargado para %s" % cat)
    off = float(P.get("offset_mm", def_off)) / FT
    ang = float(P.get("angle_deg", def_ang if is_plan else 0.0))
    out = {"view": view.Name, "category": cat, "tag_type": element_name(tag),
           "elementos": 0, "ya_tageados": 0, "creados": 0, "errores": {}}

    def work():
        tagged = set()
        for tg in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
            if str(tg.Category.Name) != tcatname:
                continue
            if P.get("replace"):
                doc.Delete(tg.Id)
                continue
            try:
                for rid in tg.GetTaggedLocalElementIds():
                    tagged.add(eidv(rid))
            except Exception:
                pass
        out["ya_tageados"] = len(tagged)
        for e in collector(doc, bic, view):
            out["elementos"] += 1
            if eidv(e.Id) in tagged:
                continue
            try:
                if cat == "columns":
                    loc = e.Location
                    if hasattr(loc, "Point"):
                        p = loc.Point
                    else:
                        bb = e.get_BoundingBox(view)
                        p = DB.XYZ((bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2, (bb.Min.Z + bb.Max.Z) / 2)
                    pos = DB.XYZ(p.X + off, p.Y + off * 0.9, p.Z) if is_plan else p
                    ori = DB.TagOrientation.Horizontal if is_plan else DB.TagOrientation.Vertical
                elif cat == "floors":
                    bb = e.get_BoundingBox(view)
                    pos = DB.XYZ((bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2, bb.Min.Z)
                    ori = DB.TagOrientation.Horizontal
                else:
                    c = location_curve(e)
                    m = c.Evaluate(0.5, True)
                    d = (c.GetEndPoint(1) - c.GetEndPoint(0)).Normalize()
                    horiz = abs(d.X) >= abs(d.Y)
                    pos = m + (DB.XYZ(0, -off, 0) if horiz else DB.XYZ(-off, 0, 0))
                    ori = DB.TagOrientation.Horizontal if horiz else DB.TagOrientation.Vertical
                tg = DB.IndependentTag.Create(doc, tag.Id, view.Id, DB.Reference(e), False, ori, pos)
                if ang and is_plan:
                    h = tg.TagHeadPosition
                    axis = DB.Line.CreateBound(h, DB.XYZ(h.X, h.Y, h.Z + 1))
                    DB.ElementTransformUtils.RotateElement(doc, tg.Id, axis, math.radians(ang))
                out["creados"] += 1
            except Exception as ex:
                k = "%s: %s" % (type(ex).__name__, str(ex)[:120])
                out["errores"][k] = out["errores"].get(k, 0) + 1
    tx(doc, "tools: tags de %s" % cat, work)
    out["ok"] = True
    return out
