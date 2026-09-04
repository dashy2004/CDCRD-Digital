# -*- coding: utf-8 -*-
"""tags_vigas: etiqueta las vigas de una vista con un Structural Framing Tag.

Del pushbutton TagsVigas. Parametros:
  view_name:  vista destino; vacio = vista activa.
  tag_type:   nombre del tipo de tag ("Standard", "Boxed"...); vacio = el primero cargado.
  offset_mm:  desplazamiento perpendicular a la viga (default 250) para no tapar la linea.
  skip_edge:  en secciones/elevaciones, saltar las vigas vistas de canto (default True).
  replace:    True borra los tags de viga existentes en la vista antes de crear (default False).
Idempotente sin replace: no duplica vigas ya etiquetadas.
"""


def run(doc, uidoc, DB, P):
    view = active_or_named_view(doc, uidoc, P.get("view_name"))
    want = P.get("tag_type") or ""
    tag = None
    for s in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralFramingTags).WhereElementIsElementType():
        if not want or element_name(s) == want:
            tag = s
            break
    if tag is None:
        raise Exception("no hay tipo de tag de viga%s cargado" % ((" '%s'" % want) if want else ""))
    off = float(P.get("offset_mm", 250.0)) / FT
    skip_edge = bool(P.get("skip_edge", True))
    is_plan = str(view.ViewType) in ("FloorPlan", "EngineeringPlan", "CeilingPlan")
    vd = view.ViewDirection
    out = {"view": view.Name, "tag_type": element_name(tag), "vigas_en_vista": 0,
           "ya_tageadas": 0, "creados": 0, "saltadas_canto": 0, "sin_curva": 0, "errores": {}}

    def work():
        tagged = set()
        for tg in DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_StructuralFramingTags).WhereElementIsNotElementType():
            if P.get("replace"):
                doc.Delete(tg.Id)
                continue
            try:
                for rid in tg.GetTaggedLocalElementIds():
                    tagged.add(eidv(rid))
            except Exception:
                pass
        out["ya_tageadas"] = len(tagged)
        for b in collector(doc, DB.BuiltInCategory.OST_StructuralFraming, view):
            out["vigas_en_vista"] += 1
            if eidv(b.Id) in tagged:
                continue
            c = location_curve(b)
            if c is None:
                out["sin_curva"] += 1
                continue
            d = (c.GetEndPoint(1) - c.GetEndPoint(0)).Normalize()
            if skip_edge and not is_plan and abs(d.DotProduct(vd)) > 0.7:
                out["saltadas_canto"] += 1
                continue
            m = c.Evaluate(0.5, True)
            if is_plan:
                horiz = abs(d.X) >= abs(d.Y)
                pos = m + (DB.XYZ(0, off, 0) if horiz else DB.XYZ(off, 0, 0))
                ori = DB.TagOrientation.Horizontal if horiz else DB.TagOrientation.Vertical
            else:
                pos = DB.XYZ(m.X, m.Y, m.Z + off)
                ori = DB.TagOrientation.Horizontal
            try:
                DB.IndependentTag.Create(doc, tag.Id, view.Id, DB.Reference(b), False, ori, pos)
                out["creados"] += 1
            except Exception as ex:
                k = "%s: %s" % (type(ex).__name__, ex)
                out["errores"][k] = out["errores"].get(k, 0) + 1
    tx(doc, "tools: tags de vigas", work)
    out["ok"] = True
    return out
