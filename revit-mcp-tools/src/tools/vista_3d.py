# -*- coding: utf-8 -*-
"""vista_3d: crea (o reutiliza) una vista 3D isometrica con caja de seccion alrededor de lo que se quiere mirar.

Pensada para verificar con vision lo que otra tool acaba de crear: se pasa
el marker y la caja de seccion se ajusta a esos elementos. Despues, ver_vista.

Parametros:
  name:        nombre de la vista (default "MCP 3D").
  marker:      prefijo de Comments para acotar la caja (default "AGENTE:"); vacio = todo el modelo.
  categorias:  alias a considerar para la caja (default columnas, vigas, losas, muros, zapatas).
  margen_mm:   holgura de la caja (default 1000).
  orientacion: "iso_se" (default) | "iso_sw" | "iso_ne" | "iso_nw" | "planta".
  estilo:      "sombreado" (default) | "lineas" | "realista".
  detalle:     "fino" (default) | "medio" | "grueso".
  replace:     True borra la vista previa con ese nombre (default False: se reutiliza y se reajusta la caja).
"""


def run(doc, uidoc, DB, P):
    name = P.get("name", "MCP 3D")
    marker = P.get("marker", "AGENTE:")
    cats = P.get("categorias") or ["columnas", "vigas", "losas", "muros", "zapatas"]
    mg = ft(float(P.get("margen_mm", 1000.0)))
    E = errs()
    lo = [1e12, 1e12, 1e12]
    hi = [-1e12, -1e12, -1e12]
    n = 0
    for alias in cats:
        try:
            for e in collector(doc, bic_of(alias)):
                try:
                    if marker and not has_mark(e, marker):
                        continue
                    bb = e.get_BoundingBox(None)
                    if bb is None:
                        continue
                    n += 1
                    for i, (a, b) in enumerate(((bb.Min.X, bb.Max.X), (bb.Min.Y, bb.Max.Y), (bb.Min.Z, bb.Max.Z))):
                        lo[i] = min(lo[i], a)
                        hi[i] = max(hi[i], b)
                except Exception as ex:
                    note(E, "bbox", ex)
        except Exception as ex:
            note(E, "cat " + alias, ex)
    if n == 0:
        raise Exception("ningun elemento con marca '%s' en %s" % (marker, cats))
    vft = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if v.ViewFamily == DB.ViewFamily.ThreeDimensional:
            vft = v
            break
    if vft is None:
        raise Exception("no hay ViewFamilyType 3D")
    existing = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
        if not v.IsTemplate and v.Name == name:
            existing = v
            break
    ORI = {"iso_se": DB.XYZ(1, -1, -1), "iso_sw": DB.XYZ(-1, -1, -1), "iso_ne": DB.XYZ(1, 1, -1), "iso_nw": DB.XYZ(-1, 1, -1), "planta": DB.XYZ(0, 0, -1)}
    fwd = ORI.get(P.get("orientacion", "iso_se"), ORI["iso_se"])
    STY = {"sombreado": DB.DisplayStyle.Shading, "lineas": DB.DisplayStyle.Wireframe, "realista": DB.DisplayStyle.Realistic}
    DET = {"fino": DB.ViewDetailLevel.Fine, "medio": DB.ViewDetailLevel.Medium, "grueso": DB.ViewDetailLevel.Coarse}
    out = {"name": name, "elementos_en_caja": n, "caja_mm": {"min": [mm(x) for x in lo], "max": [mm(x) for x in hi]}, "excepciones": E}
    if existing is not None and P.get("replace"):
        leave_view(doc, uidoc, [existing.Id])

    def work():
        v = existing
        if v is not None and P.get("replace"):
            doc.Delete(v.Id)
            v = None
        if v is None:
            v = DB.View3D.CreateIsometric(doc, vft.Id)
            v.Name = name
            out["accion"] = "creada"
        else:
            out["accion"] = "reutilizada"
        try:
            f = fwd.Normalize()
            planta = abs(f.X) + abs(f.Y) < 1e-6
            if planta:
                up2 = DB.XYZ(0, 1, 0)
            else:
                right = f.CrossProduct(DB.XYZ(0, 0, 1)).Normalize()
                up2 = right.CrossProduct(f).Normalize()
            v.SetOrientation(DB.ViewOrientation3D(DB.XYZ(0, 0, 0), up2, f))
        except Exception as ex:
            note(E, "orientacion", ex)
        bb = DB.BoundingBoxXYZ()
        bb.Min = DB.XYZ(lo[0] - mg, lo[1] - mg, lo[2] - mg)
        bb.Max = DB.XYZ(hi[0] + mg, hi[1] + mg, hi[2] + mg)
        v.IsSectionBoxActive = True
        v.SetSectionBox(bb)
        try:
            v.DisplayStyle = STY.get(P.get("estilo", "sombreado"), DB.DisplayStyle.Shading)
            v.DetailLevel = DET.get(P.get("detalle", "fino"), DB.ViewDetailLevel.Fine)
        except Exception as ex:
            note(E, "estilo", ex)
        out["id"] = eidv(v.Id)
    tx(doc, "tools: vista 3d", work)
    out["ok"] = E["n"] == 0
    return out
