# -*- coding: utf-8 -*-
"""porticos_por_eje: crea una Framing Elevation por eje de la rejilla.

Reemplaza a CrearVistaPorticoD y VistasPorticoVC (que dependian de nombres
de un proyecto). Lee los ejes del modelo; para cada uno crea un
ElevationMarker + elevation con tipo de vista "Framing Elevation" (se crea
duplicando "Building Elevation" si no existe), mirando perpendicular al eje,
y recorta la caja al rango del edificio con la profundidad pedida. Los ejes
en X (letras) se pueden partir por bloques dando rangos en Y. Parametros:
  grids:        lista de nombres de eje; vacio = todos.
  prefix:       prefijo del nombre de vista (default "PORTICO EJE ").
  depth_mm:     media profundidad del corte (default 900).
  z_min_mm / z_max_mm: rango vertical (default -800 / nivel mas alto + 1500).
  blocks:       para ejes en X: {"nombre": [y0_mm, y1_mm], ...}; crea una vista por bloque.
  template:     nombre de plantilla de vista a aplicar (opcional).
  scale:        escala (default 100).
  replace:      True borra vistas previas con el mismo nombre.
Direccion de mirada: ejes Y (numericos) miran hacia -Y; ejes X (letras) hacia +X.
"""


def run(doc, uidoc, DB, P):
    prefix = P.get("prefix", "PORTICO EJE ")
    depth = float(P.get("depth_mm", 900.0))
    scale = int(P.get("scale", 100))
    want = set(P.get("grids") or [])
    blocks = P.get("blocks") or {}
    tmpl = P.get("template")
    zmin = float(P.get("z_min_mm", -800.0))
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))
    zmax = float(P.get("z_max_mm", max(l.Elevation for l in levels) * FT + 1500.0))
    grids = list(DB.FilteredElementCollector(doc).OfClass(DB.Grid))
    gx = []
    gy = []
    for g in grids:
        c = g.Curve
        a = c.GetEndPoint(0)
        b = c.GetEndPoint(1)
        if abs(a.X - b.X) < 1e-6:
            gx.append(g)
        elif abs(a.Y - b.Y) < 1e-6:
            gy.append(g)
    if not gx or not gy:
        raise Exception("se necesitan ejes en X y en Y")
    XA = min(g.Curve.GetEndPoint(0).X for g in gx) * FT
    XB = max(g.Curve.GetEndPoint(0).X for g in gx) * FT
    YA = min(g.Curve.GetEndPoint(0).Y for g in gy) * FT
    YB = max(g.Curve.GetEndPoint(0).Y for g in gy) * FT
    plan = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        if not v.IsTemplate and str(v.ViewType) in ("EngineeringPlan", "FloorPlan"):
            plan = v
            break
    if plan is None:
        raise Exception("no hay vista de planta donde colocar los marcadores")
    vft_e = None
    vft_f = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if str(v.ViewFamily) == "Elevation":
            n = element_name(v)
            if n == "Framing Elevation":
                vft_f = v
            elif n == "Building Elevation":
                vft_e = v
    tv = None
    if tmpl:
        tv = next((v for v in DB.FilteredElementCollector(doc).OfClass(DB.View) if v.IsTemplate and v.Name == tmpl), None)
        if tv is None:
            raise Exception("no existe la plantilla de vista '%s'" % tmpl)
    existing = dict((v.Name, v) for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSection))
    jobs = []
    for g in gy:
        if want and g.Name not in want:
            continue
        y = g.Curve.GetEndPoint(0).Y * FT
        jobs.append((prefix + g.Name, "Y", y, (XA - 1200, XB + 1200, y - depth, y + depth)))
    for g in gx:
        if want and g.Name not in want:
            continue
        x = g.Curve.GetEndPoint(0).X * FT
        if blocks:
            for bname, (y0, y1) in blocks.items():
                jobs.append((prefix + g.Name + " - BLOQUE " + bname, "X", x, (x - depth, x + depth, min(y0, y1) - 800, max(y0, y1) + 800)))
        else:
            jobs.append((prefix + g.Name, "X", x, (x - depth, x + depth, YA - 800, YB + 800)))
    out = {"creadas": [], "existian": [], "errores": [], "framing_elevation_type": None}

    def f(v):
        return v / FT

    def work():
        vf = vft_f
        if vf is None:
            if vft_e is None:
                raise Exception("no existe el tipo de vista 'Building Elevation' para duplicar")
            nid = vft_e.Duplicate("Framing Elevation")
            vf = doc.GetElement(nid) if isinstance(nid, DB.ElementId) else nid
        out["framing_elevation_type"] = element_name(vf)
        for name, axis, coord, box in jobs:
            if name in existing:
                if P.get("replace"):
                    doc.Delete(existing[name].Id)
                else:
                    out["existian"].append(name)
                    continue
            try:
                x0, x1, y0, y1 = box
                if axis == "Y":
                    mk = DB.ElevationMarker.CreateElevationMarker(doc, vf.Id, DB.XYZ(f((x0 + x1) / 2.0), f(coord + 3000), 0), scale)
                    v = mk.CreateElevation(doc, plan.Id, 1)     # mira -Y
                else:
                    mk = DB.ElevationMarker.CreateElevationMarker(doc, vf.Id, DB.XYZ(f(coord - 3000), f((y0 + y1) / 2.0), 0), scale)
                    v = mk.CreateElevation(doc, plan.Id, 0)     # mira +X
                v.Name = name
                v.Scale = scale
                doc.Regenerate()
                cb = v.CropBox
                T = cb.Transform
                o = T.Origin
                B = (T.BasisX, T.BasisY, T.BasisZ)
                lo = [1e9] * 3
                hi = [-1e9] * 3
                for X in (f(x0), f(x1)):
                    for Yy in (f(y0), f(y1)):
                        for Z in (f(zmin), f(zmax)):
                            d = DB.XYZ(X, Yy, Z) - o
                            for i in range(3):
                                val = d.DotProduct(B[i])
                                lo[i] = min(lo[i], val)
                                hi[i] = max(hi[i], val)
                nb = DB.BoundingBoxXYZ()
                nb.Transform = T
                nb.Min = DB.XYZ(lo[0], lo[1], lo[2])
                nb.Max = DB.XYZ(hi[0], hi[1], hi[2])
                v.CropBox = nb
                v.CropBoxActive = True
                if tv is not None:
                    v.ViewTemplateId = tv.Id
                out["creadas"].append(name)
            except Exception as ex:
                out["errores"].append([name, "%s: %s" % (type(ex).__name__, str(ex)[:120])])
    tx(doc, "tools: porticos por eje", work)
    out["ok"] = not out["errores"]
    return out
