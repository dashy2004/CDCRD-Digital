# -*- coding: utf-8 -*-
"""sin_hatch_material: quita o fija los patrones de un material a nivel de proyecto.

Del pushbutton SinHatchConcreto, generalizado. Parametros:
  material:        nombre exacto (obligatorio).
  cut_pattern:     "" para quitar, o nombre de patron de drafting (default "").
  surface_pattern: None para no tocar (default), "" para quitar, o nombre de patron.
  color_rgb:       [r,g,b] opcional para el patron superficial (foreground).
Idempotente: si ya esta en el estado pedido, lo reporta sin escribir.
"""


def run(doc, uidoc, DB, P):
    name = P.get("material")
    if not name:
        raise Exception("falta 'material'")
    mat = None
    for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if m.Name == name:
            mat = m
            break
    if mat is None:
        raise Exception("no existe el material '%s'" % name)
    pats = {}
    for fp in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
        pats[fp.Name] = fp
    inval = DB.ElementId.InvalidElementId

    def pid(nm):
        if nm == "":
            return inval
        if nm not in pats:
            raise Exception("no existe el patron '%s'" % nm)
        return pats[nm].Id

    def cur(eid):
        try:
            return eidv(eid) if eid is not None and eidv(eid) != eidv(inval) else None
        except Exception:
            return None
    out = {"material": name, "cut_antes": cur(mat.CutForegroundPatternId),
           "surface_antes": cur(mat.SurfaceForegroundPatternId), "cambios": []}
    cut = P.get("cut_pattern", "")
    surf = P.get("surface_pattern", None)
    rgb = P.get("color_rgb")

    def work():
        target = pid(cut)
        if cur(mat.CutForegroundPatternId) != cur(target):
            mat.CutForegroundPatternId = target
            out["cambios"].append("cut -> %s" % (cut or "<ninguno>"))
        if surf is not None:
            t2 = pid(surf)
            if cur(mat.SurfaceForegroundPatternId) != cur(t2):
                mat.SurfaceForegroundPatternId = t2
                out["cambios"].append("surface -> %s" % (surf or "<ninguno>"))
        if rgb:
            mat.SurfaceForegroundPatternColor = DB.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]))
            out["cambios"].append("surface color -> %s" % list(rgb))
    tx(doc, "tools: patrones de material", work)
    out["cut_despues"] = cur(mat.CutForegroundPatternId)
    out["surface_despues"] = cur(mat.SurfaceForegroundPatternId)
    out["ok"] = True
    return out
