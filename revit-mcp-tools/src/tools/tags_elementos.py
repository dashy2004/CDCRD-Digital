# -*- coding: utf-8 -*-
"""tags_elementos: etiqueta columnas, losas o muros de una vista.

Complementa a tags_vigas para las otras tres categorias (columnas a 45 grados
opcional, losas por centro de caja, muros con desplazamiento). Parametros:
  category:   "columns" | "floors" | "walls" | "foundations" | "rebar" (obligatorio).
  view_name:  vista destino; vacio = vista activa.
  tag_type:   nombre del tipo de tag; vacio = el primero cargado de esa categoria.
  offset_mm:  desplazamiento del texto (default 420 columnas, 450 muros, 0 losas).
  angle_deg:  rotacion del tag (default 45 para columnas en planta, 0 el resto).
  replace:    True borra los tags previos de esa categoria en la vista.
  leader:     True dibuja linea de referencia (default: True en 3D/seccion, False en planta).
  max_por_tipo: etiqueta a lo sumo N elementos de cada tipo. Con 1 el resultado es una
              leyenda sobre el modelo en vez de una nube de tags repetidos.
  escalonar:  True (default fuera de planta) alterna la distancia del texto en tres pasos
              para que los tags no se apilen unos sobre otros.
  separacion_mm: en vistas no de planta, cuanto se aparta el texto del elemento
              en las direcciones de la pantalla (default 1200); el leader lo conecta.
Los tags de columna y losa muestran el Type Name; el de muro el Type Mark.
En vista 3D la vista debe tener la orientacion bloqueada (ver vista_3d_detalle).
"""


def run(doc, uidoc, DB, P):
    import math
    cat = P.get("category")
    CATS = {"columns": (DB.BuiltInCategory.OST_StructuralColumns, DB.BuiltInCategory.OST_StructuralColumnTags, "Structural Column Tags", 420.0, 45.0),
            "floors": (DB.BuiltInCategory.OST_Floors, DB.BuiltInCategory.OST_FloorTags, "Floor Tags", 0.0, 0.0),
            "walls": (DB.BuiltInCategory.OST_Walls, DB.BuiltInCategory.OST_WallTags, "Wall Tags", 450.0, 0.0),
            "foundations": (DB.BuiltInCategory.OST_StructuralFoundation, DB.BuiltInCategory.OST_StructuralFoundationTags, "Structural Foundation Tags", 420.0, 0.0),
            "rebar": (DB.BuiltInCategory.OST_Rebar, DB.BuiltInCategory.OST_RebarTags, "Structural Rebar Tags", 300.0, 0.0)}
    if cat not in CATS:
        raise Exception("category debe ser una de %s" % sorted(CATS.keys()))
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
    lead = bool(P.get("leader", not is_plan))
    max_tipo = P.get("max_por_tipo")
    max_tipo = int(max_tipo) if max_tipo else None
    escalonar = bool(P.get("escalonar", not is_plan))
    sep = float(P.get("separacion_mm", 0.0 if is_plan else 1200.0)) / FT
    try:
        rdir = view.RightDirection
        udir = view.UpDirection
    except Exception:
        rdir = DB.XYZ(1, 0, 0)
        udir = DB.XYZ(0, 0, 1)
    out = {"view": view.Name, "category": cat, "tag_type": element_name(tag),
           "elementos": 0, "ya_tageados": 0, "creados": 0, "errores": {}}

    def work():
        tagged = set()
        for tg in DB.FilteredElementCollector(doc, view.Id).OfCategory(tbic).WhereElementIsNotElementType():
            if not isinstance(tg, DB.IndependentTag):
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
        por_tipo = {}
        idx = 0
        for e in collector(doc, bic, view):
            out["elementos"] += 1
            if eidv(e.Id) in tagged:
                continue
            if max_tipo is not None:
                tn = type_name(doc, e) or "?"
                if por_tipo.get(tn, 0) >= max_tipo:
                    out["saltados_por_tipo"] = out.get("saltados_por_tipo", 0) + 1
                    continue
                por_tipo[tn] = por_tipo.get(tn, 0) + 1
            idx += 1
            try:
                if cat in ("columns", "foundations"):
                    loc = e.Location
                    bb = e.get_BoundingBox(view)
                    if hasattr(loc, "Point"):
                        p = loc.Point
                    elif bb is not None:
                        p = DB.XYZ((bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2, (bb.Min.Z + bb.Max.Z) / 2)
                    else:
                        raise Exception("columna sin punto ni caja")
                    if is_plan:
                        pos = DB.XYZ(p.X + off, p.Y + off * 0.9, p.Z)
                    elif bb is not None:
                        pos = DB.XYZ(p.X, p.Y, (bb.Min.Z + bb.Max.Z) / 2)
                    else:
                        pos = p
                    ori = DB.TagOrientation.Horizontal if is_plan else DB.TagOrientation.Horizontal
                elif cat in ("floors", "rebar"):
                    bb = e.get_BoundingBox(view)
                    zz = bb.Min.Z if cat == "floors" else (bb.Min.Z + bb.Max.Z) / 2
                    pos = DB.XYZ((bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2, zz)
                    ori = DB.TagOrientation.Horizontal
                else:
                    c = location_curve(e)
                    m = c.Evaluate(0.5, True)
                    d = (c.GetEndPoint(1) - c.GetEndPoint(0)).Normalize()
                    horiz = abs(d.X) >= abs(d.Y)
                    if is_plan:
                        pos = m + (DB.XYZ(0, -off, 0) if horiz else DB.XYZ(-off, 0, 0))
                    else:
                        pos = DB.XYZ(m.X, m.Y, m.Z + off)
                    ori = DB.TagOrientation.Horizontal if (horiz or not is_plan) else DB.TagOrientation.Vertical
                if not is_plan and sep:
                    k = (1.0 + 0.5 * (idx % 3)) if escalonar else 1.0
                    pos = pos + rdir.Multiply(sep * k) + udir.Multiply(sep * k)
                tg = DB.IndependentTag.Create(doc, tag.Id, view.Id, DB.Reference(e), lead, ori, pos)
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
