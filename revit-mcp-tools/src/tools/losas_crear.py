# -*- coding: utf-8 -*-
"""losas_crear: crea losas (Floor) por contorno, por envolvente de ejes o por celda de ejes, en un nivel.

Parametros:
  tipo:        nombre del FloorType. Obligatorio.
  nivel:       nombre del nivel. Obligatorio.
  modo:        "contornos" (default) | "envolvente_ejes" (un rectangulo que cubre todos los ejes,
               o los de "ejes") | "celdas_ejes" (una losa por celda entre ejes consecutivos).
  contornos_mm: lista de poligonos [[x,y], [x,y], ...] (modo contornos).
  ejes:        acotar los ejes usados (modos por ejes).
  estructural: True (default) marca la losa como estructural.
  offset_mm:   desfase "Height Offset From Level" (default 0).
  marker:      Comments (default "AGENTE:LOSA").
  tolerancia_mm: para detectar una losa existente con el mismo centro y area (default 50).
  dry_run:     True solo informa (default True).
Cada losa creada devuelve su espesor leido del modelo (E-045: el espesor no
se hereda del nombre del tipo; se verifica) y su area en m2.
"""


def run(doc, uidoc, DB, P):
    from System.Collections.Generic import List
    dry = bool(P.get("dry_run", True))
    marker = P.get("marker", "AGENTE:LOSA")
    tol = ft(float(P.get("tolerancia_mm", 50.0)))
    lv = need_level(doc, P.get("nivel"))
    tname = P.get("tipo")
    ftype = None
    for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType):
        if element_name(t) == tname:
            ftype = t
            break
    if ftype is None:
        raise Exception("no existe el FloorType '%s'; hay: %s" % (tname, sorted(element_name(t) for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType))[:40]))
    modo = P.get("modo", "contornos")
    polys = []
    if modo == "contornos":
        for i, poly in enumerate(P.get("contornos_mm") or []):
            polys.append(([(ft(p[0]), ft(p[1])) for p in poly], "contorno%d" % (i + 1)))
    else:
        gi = grids_info(doc)
        sel = set(P.get("ejes") or [])
        xs = sorted((gi[k]["p0"].X, k) for k in gi if gi[k]["dir"] == "X" and (not sel or k in sel))
        ys = sorted((gi[k]["p0"].Y, k) for k in gi if gi[k]["dir"] == "Y" and (not sel or k in sel))
        if len(xs) < 2 or len(ys) < 2:
            raise Exception("se necesitan al menos 2 ejes de X constante y 2 de Y constante")
        if modo == "envolvente_ejes":
            x0, x1, y0, y1 = xs[0][0], xs[-1][0], ys[0][0], ys[-1][0]
            polys.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "%s%s-%s%s" % (xs[0][1], ys[0][1], xs[-1][1], ys[-1][1])))
        elif modo == "celdas_ejes":
            for i in range(len(xs) - 1):
                for j in range(len(ys) - 1):
                    x0, x1, y0, y1 = xs[i][0], xs[i + 1][0], ys[j][0], ys[j + 1][0]
                    polys.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "%s%s-%s%s" % (xs[i][1], ys[j][1], xs[i + 1][1], ys[j + 1][1])))
        else:
            raise Exception("modo debe ser contornos, envolvente_ejes o celdas_ejes")
    if not polys:
        raise Exception("sin contornos")

    def centroid_area(poly):
        a = 0.0
        cx = cy = 0.0
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            cr = x0 * y1 - x1 * y0
            a += cr
            cx += (x0 + x1) * cr
            cy += (y0 + y1) * cr
        a *= 0.5
        if abs(a) < 1e-9:
            return None, 0.0
        return (cx / (6.0 * a), cy / (6.0 * a)), abs(a)

    existing = []
    for f in collector(doc, DB.BuiltInCategory.OST_Floors):
        try:
            if f.LevelId != lv.Id:
                continue
            bb = f.get_BoundingBox(None)
            if bb is None:
                continue
            c = DB.XYZ((bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0, 0)
            ap = f.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
            existing.append((c, ap.AsDouble() if ap is not None else None, f))
        except Exception:
            pass
    E = errs()
    out = {"dry_run": dry, "tipo": element_name(ftype), "nivel": lv.Name, "plan": [], "creadas": [],
           "existian": [], "errores": [], "excepciones": E}
    jobs = []
    for poly, tag in polys:
        if len(poly) < 3:
            out["errores"].append([tag, "menos de 3 vertices"])
            continue
        c, a = centroid_area(poly)
        if c is None:
            out["errores"].append([tag, "area nula"])
            continue
        cp = DB.XYZ(c[0], c[1], 0)
        dup = None
        for ec, ea, f in existing:
            if close_xy(ec, cp, tol) and (ea is None or abs(ea - a) <= 0.02 * a):
                dup = f
                break
        out["plan"].append({"losa": tag, "vertices": len(poly), "area_m2": round(a * 0.09290304, 2),
                            "accion": "existe id %d" % eidv(dup.Id) if dup else "crear"})
        if dup is None:
            jobs.append((poly, tag))
        else:
            out["existian"].append(tag)
    if dry:
        return out
    structural = bool(P.get("estructural", True))
    off = ft(float(P.get("offset_mm", 0.0)))

    def work():
        for poly, tag in jobs:
            try:
                curves = List[DB.Curve]()
                n = len(poly)
                for i in range(n):
                    a = DB.XYZ(poly[i][0], poly[i][1], lv.Elevation)
                    b = DB.XYZ(poly[(i + 1) % n][0], poly[(i + 1) % n][1], lv.Elevation)
                    curves.Add(DB.Line.CreateBound(a, b))
                loop = DB.CurveLoop.Create(curves)
                loops = List[DB.CurveLoop]()
                loops.Add(loop)
                fl = DB.Floor.Create(doc, loops, ftype.Id, lv.Id, structural, None, 0.0)
                if off:
                    set_param(fl, DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM, mm(off))
                mark(fl, marker + ":" + tag)
                doc.Regenerate()
                rec = {"losa": tag, "id": eidv(fl.Id), "espesor_mm": param_mm(fl, DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)}
                ap = fl.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
                rec["area_m2"] = round(ap.AsDouble() * 0.09290304, 2) if ap is not None else None
                out["creadas"].append(rec)
            except Exception as ex:
                out["errores"].append([tag, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: losas", work)
    out["ok"] = not out["errores"]
    return out
