# -*- coding: utf-8 -*-
"""vistas_planta: crea una vista de planta por nivel (estructural, de piso o de cielo).

Los niveles creados por API no traen planta. Esta tool la crea con nombre
predecible, escala, plantilla opcional y, por defecto, SIN underlay: el
underlay dibuja el nivel de abajo encima del plano aunque el rango de vista
este bien, y es el defecto mas repetido en planos generados por agentes.

Parametros:
  levels:        nombres de nivel; vacio = todos.
  kind:          "estructural" (Structural Plan) | "piso" (Floor Plan) | "cielo" (Ceiling Plan). Default estructural.
  prefix/suffix: nombre = prefix + nivel + suffix (default "PLANTA " / "").
  scale:         escala (default 100).
  template:      nombre de plantilla de vista a aplicar (opcional).
  cut_mm:        altura del plano de corte sobre el nivel (opcional; default de Revit 1200).
  underlay_off:  True quita el underlay (default True).
  crop:          True recorta la vista a la caja de columnas/vigas/losas/muros/zapatas del modelo
                 mas crop_margen_mm (default 2500). Sin recorte, los marcadores de elevacion de la
                 plantilla quedan lejos del edificio y la vista ocupa la lamina entera.
  replace:       True borra la vista previa con el mismo nombre.
  dry_run:       True solo informa que crearia (default True).
Devuelve creadas / existian / errores y, por vista, cuantos ejes son visibles
(si es 0 y hay ejes, los ejes no cruzan la planta: ver niveles_ejes).
"""


def run(doc, uidoc, DB, P):
    kind = P.get("kind", "estructural")
    FAM = {"estructural": DB.ViewFamily.StructuralPlan, "piso": DB.ViewFamily.FloorPlan, "cielo": DB.ViewFamily.CeilingPlan}
    if kind not in FAM:
        raise Exception("kind debe ser estructural, piso o cielo")
    prefix = P.get("prefix", "PLANTA ")
    suffix = P.get("suffix", "")
    scale = int(P.get("scale", 100))
    dry = bool(P.get("dry_run", True))
    want = P.get("levels") or []
    levels = [l for l in levels_sorted(doc) if not want or l.Name in want]
    faltan = [n for n in want if n not in [l.Name for l in levels]]
    if faltan:
        raise Exception("no existen los niveles %s" % faltan)
    vft = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if v.ViewFamily == FAM[kind]:
            vft = v
            break
    if vft is None:
        raise Exception("no hay ViewFamilyType para %s en este documento" % kind)
    tv = None
    if P.get("template"):
        tv = next((v for v in DB.FilteredElementCollector(doc).OfClass(DB.View) if v.IsTemplate and v.Name == P["template"]), None)
        if tv is None:
            raise Exception("no existe la plantilla de vista '%s'" % P["template"])
    existing = {}
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        if not v.IsTemplate:
            existing.setdefault(v.Name, v)
    n_grids = DB.FilteredElementCollector(doc).OfClass(DB.Grid).GetElementCount()
    E = errs()
    crop_box = None
    if P.get("crop"):
        mg = ft(float(P.get("crop_margen_mm", 2500.0)))
        lo = [1e12, 1e12]
        hi = [-1e12, -1e12]
        n = 0
        for alias in ("columnas", "vigas", "losas", "muros", "zapatas"):
            for e in collector(doc, bic_of(alias)):
                try:
                    bb = e.get_BoundingBox(None)
                    if bb is None:
                        continue
                    n += 1
                    lo[0] = min(lo[0], bb.Min.X)
                    lo[1] = min(lo[1], bb.Min.Y)
                    hi[0] = max(hi[0], bb.Max.X)
                    hi[1] = max(hi[1], bb.Max.Y)
                except Exception as ex:
                    note(E, "crop bbox", ex)
        if n:
            crop_box = (lo[0] - mg, lo[1] - mg, hi[0] + mg, hi[1] + mg)
    out = {"kind": kind, "view_family_type": element_name(vft), "dry_run": dry, "plan": [],
           "creadas": [], "existian": [], "errores": [], "ejes_en_modelo": n_grids, "excepciones": E}
    jobs = []
    for lv in levels:
        name = prefix + lv.Name + suffix
        st = "existe" if name in existing else "crear"
        if st == "existe" and P.get("replace"):
            st = "reemplazar"
        out["plan"].append({"nivel": lv.Name, "vista": name, "accion": st})
        jobs.append((lv, name, st))
    if dry:
        return out
    out["vista_activa_cambiada_a"] = leave_view(doc, uidoc, [existing[n].Id for _, n, st in jobs if st == "reemplazar"])

    def work():
        for lv, name, st in jobs:
            try:
                if st == "existe":
                    out["existian"].append(name)
                    continue
                if st == "reemplazar":
                    doc.Delete(existing[name].Id)
                v = DB.ViewPlan.Create(doc, vft.Id, lv.Id)
                v.Name = name
                try:
                    v.Scale = scale
                except Exception as ex:
                    note(E, "scale " + name, ex)
                if P.get("underlay_off", True):
                    try:
                        v.SetUnderlayBaseLevel(DB.ElementId.InvalidElementId)
                    except Exception as ex:
                        note(E, "underlay " + name, ex)
                if P.get("cut_mm") is not None:
                    try:
                        vr = v.GetViewRange()
                        cut = ft(P["cut_mm"])
                        vr.SetOffset(DB.PlanViewPlane.CutPlane, cut)
                        # el rango es invalido si el plano superior queda por
                        # debajo del corte (pasa con plantillas cuyo Top es
                        # "nivel actual + 1219"): subirlo con el corte.
                        top_lv = vr.GetLevelId(DB.PlanViewPlane.TopClipPlane)
                        if top_lv == lv.Id or top_lv == DB.PlanViewRange.Current:
                            if vr.GetOffset(DB.PlanViewPlane.TopClipPlane) < cut + ft(300):
                                vr.SetOffset(DB.PlanViewPlane.TopClipPlane, cut + ft(300))
                        v.SetViewRange(vr)
                    except Exception as ex:
                        note(E, "cut " + name, ex)
                if tv is not None:
                    v.ViewTemplateId = tv.Id
                if crop_box is not None:
                    try:
                        cb = v.CropBox
                        cb.Min = DB.XYZ(crop_box[0], crop_box[1], cb.Min.Z)
                        cb.Max = DB.XYZ(crop_box[2], crop_box[3], cb.Max.Z)
                        v.CropBox = cb
                        v.CropBoxActive = True
                        v.CropBoxVisible = False
                    except Exception as ex:
                        note(E, "crop " + name, ex)
                doc.Regenerate()
                try:
                    vis = DB.FilteredElementCollector(doc, v.Id).OfClass(DB.Grid).GetElementCount()
                except Exception:
                    vis = None
                out["creadas"].append({"vista": name, "id": eidv(v.Id), "nivel": lv.Name, "ejes_visibles": vis})
            except Exception as ex:
                out["errores"].append([name, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: vistas de planta", work)
    out["ok"] = not out["errores"]
    return out
