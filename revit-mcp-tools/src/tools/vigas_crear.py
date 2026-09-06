# -*- coding: utf-8 -*-
"""vigas_crear: crea vigas entre intersecciones de ejes o entre puntos, en un nivel, idempotente.

Parametros:
  tipo:       nombre del tipo de viga ('Tipo' o 'Familia: Tipo'). Obligatorio.
  nivel:      nombre del nivel de referencia. Obligatorio.
  tramos:     lista de [[ejeA, eje1], [ejeB, eje1]] (cada tramo une dos intersecciones), o
              "por_ejes": un tramo entre intersecciones consecutivas a lo largo de cada eje
              (se puede acotar con "ejes": [...]).
  lineas_mm:  lista de [[x0,y0],[x1,y1]] adicionales (opcional).
  z_offset_mm: desfase vertical respecto al nivel (default 0: cara superior al nivel segun la familia).
  sin_union_extremos: True aplica DisallowJoinAtEnd en ambos extremos. Por defecto Revit hace
              autojoin y EXTIENDE la LocationCurve hasta el eje del elemento con el que se une
              (E-055): los extremos que devuelve la API no son los que se pidieron.
  marker:     Comments (default "AGENTE:VIGA"); se agrega ":<tramo>".
  tolerancia_mm: para detectar una viga existente con los mismos extremos (default 50).
  dry_run:    True solo informa (default True).
Devuelve por viga creada los extremos pedidos y los reales (delta_mm) para
que el desplazamiento por autojoin sea visible.
"""


def run(doc, uidoc, DB, P):
    dry = bool(P.get("dry_run", True))
    marker = P.get("marker", "AGENTE:VIGA")
    tol = ft(float(P.get("tolerancia_mm", 50.0)))
    sym = need_symbol(doc, DB.BuiltInCategory.OST_StructuralFraming, P.get("tipo"), "viga")
    lv = need_level(doc, P.get("nivel"))
    z = lv.Elevation + ft(float(P.get("z_offset_mm", 0.0)))
    gi = grids_info(doc)
    segs = []
    tramos = P.get("tramos")
    if tramos == "por_ejes":
        sel = set(P.get("ejes") or [])
        names = [k for k in gi if not sel or k in sel]
        segs.extend(grid_segments(gi, names, tol))
    elif tramos:
        for (a, b), (c, d) in tramos:
            segs.append((grid_point(gi, a, b), grid_point(gi, c, d), "%s%s-%s%s" % (a, b, c, d)))
    for ln in (P.get("lineas_mm") or []):
        segs.append(((ft(ln[0][0]), ft(ln[0][1])), (ft(ln[1][0]), ft(ln[1][1])), "l(%.0f,%.0f-%.0f,%.0f)" % (ln[0][0], ln[0][1], ln[1][0], ln[1][1])))
    if not segs:
        raise Exception("sin tramos: pase tramos, 'por_ejes' o lineas_mm")
    existing = []
    for b in collector(doc, DB.BuiltInCategory.OST_StructuralFraming):
        try:
            c = location_curve(b)
            if c is not None and abs(c.GetEndPoint(0).Z - z) < ft(300):
                existing.append((c, b))
        except Exception:
            pass
    E = errs()
    out = {"dry_run": dry, "tipo": family_and_type(sym), "nivel": lv.Name, "plan": [], "creadas": [],
           "existian": [], "errores": [], "excepciones": E}
    jobs = []
    for pa, pb, tag in segs:
        a = DB.XYZ(pa[0], pa[1], z)
        b = DB.XYZ(pb[0], pb[1], z)
        if a.DistanceTo(b) < ft(100):
            out["errores"].append([tag, "tramo menor a 100 mm"])
            continue
        dup = None
        for c, el in existing:
            if same_segment(c, a, b, tol):
                dup = el
                break
        out["plan"].append({"tramo": tag, "p0_mm": [mm(a.X), mm(a.Y)], "p1_mm": [mm(b.X), mm(b.Y)],
                            "accion": "existe id %d" % eidv(dup.Id) if dup else "crear"})
        if dup is None:
            jobs.append((a, b, tag))
        else:
            out["existian"].append(tag)
    if dry:
        return out
    nojoin = bool(P.get("sin_union_extremos", False))

    def work():
        activate(sym)
        for a, b, tag in jobs:
            try:
                line = DB.Line.CreateBound(a, b)
                bm = doc.Create.NewFamilyInstance(line, sym, lv, DB.Structure.StructuralType.Beam)
                if nojoin:
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(bm, 0)
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(bm, 1)
                mark(bm, marker + ":" + tag)
                doc.Regenerate()
                c = location_curve(bm)
                rec = {"tramo": tag, "id": eidv(bm.Id), "pedido_mm": [pt_mm(a), pt_mm(b)]}
                if c is not None:
                    r0, r1 = c.GetEndPoint(0), c.GetEndPoint(1)
                    rec["real_mm"] = [pt_mm(r0), pt_mm(r1)]
                    rec["delta_mm"] = [mm(min(r0.DistanceTo(a), r0.DistanceTo(b))), mm(min(r1.DistanceTo(a), r1.DistanceTo(b)))]
                out["creadas"].append(rec)
            except Exception as ex:
                out["errores"].append([tag, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: vigas", work)
    n = 0
    for b in collector(doc, DB.BuiltInCategory.OST_StructuralFraming):
        try:
            if has_mark(b, marker):
                n += 1
        except Exception as ex:
            note(E, "releer", ex)
    out["relectura"] = {"vigas_con_marca": n, "marker": marker}
    out["ok"] = not out["errores"]
    return out
