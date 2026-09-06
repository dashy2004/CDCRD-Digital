# -*- coding: utf-8 -*-
"""muros_crear: crea muros por lineas o a lo largo de ejes, entre dos niveles, idempotente.

Parametros:
  tipo:        nombre del WallType (muro basico). Obligatorio.
  nivel_base:  nombre del nivel base. Obligatorio.
  nivel_tope:  nombre del nivel tope (restriccion superior) o, en su lugar, altura_mm.
  lineas_mm:   lista de [[x0,y0],[x1,y1]].
  tramos:      como en vigas_crear: [[ejeA, eje1], [ejeB, eje1]] o "por_ejes" (+ "ejes").
  estructural: True (default) marca el muro como portante.
  linea_ubicacion: 0 eje del muro (default) | 1 eje del nucleo | 2 cara exterior | 3 cara interior.
  offset_base_mm: desfase de base (default 0).
  marker:      Comments (default "AGENTE:MURO").
  tolerancia_mm: para detectar un muro existente con los mismos extremos (default 50).
  dry_run:     True solo informa (default True).
Cada muro creado devuelve su ancho leido del modelo (E-045) y la restriccion superior aplicada.
"""


def run(doc, uidoc, DB, P):
    dry = bool(P.get("dry_run", True))
    marker = P.get("marker", "AGENTE:MURO")
    tol = ft(float(P.get("tolerancia_mm", 50.0)))
    lb = need_level(doc, P.get("nivel_base"))
    lt = find_level(doc, P.get("nivel_tope")) if P.get("nivel_tope") else None
    if P.get("nivel_tope") and lt is None:
        raise Exception("no existe el nivel tope '%s'" % P["nivel_tope"])
    if lt is None and P.get("altura_mm") is None:
        raise Exception("pase nivel_tope o altura_mm")
    height = (lt.Elevation - lb.Elevation) if lt is not None else ft(float(P["altura_mm"]))
    if height <= 0:
        raise Exception("altura no positiva")
    tname = P.get("tipo")
    wt = None
    for t in DB.FilteredElementCollector(doc).OfClass(DB.WallType):
        if element_name(t) == tname:
            wt = t
            break
    if wt is None:
        raise Exception("no existe el WallType '%s'; hay: %s" % (tname, sorted(element_name(t) for t in DB.FilteredElementCollector(doc).OfClass(DB.WallType) if t.Kind == DB.WallKind.Basic)[:40]))
    segs = []
    for ln in (P.get("lineas_mm") or []):
        segs.append(((ft(ln[0][0]), ft(ln[0][1])), (ft(ln[1][0]), ft(ln[1][1])), "l(%.0f,%.0f-%.0f,%.0f)" % (ln[0][0], ln[0][1], ln[1][0], ln[1][1])))
    tramos = P.get("tramos")
    if tramos:
        gi = grids_info(doc)
        if tramos == "por_ejes":
            sel = set(P.get("ejes") or [])
            segs.extend(grid_segments(gi, [k for k in gi if not sel or k in sel], tol))
        else:
            for (a, b), (c, d) in tramos:
                segs.append((grid_point(gi, a, b), grid_point(gi, c, d), "%s%s-%s%s" % (a, b, c, d)))
    if not segs:
        raise Exception("sin lineas: pase lineas_mm o tramos")
    z = lb.Elevation
    existing = []
    for w in collector(doc, DB.BuiltInCategory.OST_Walls):
        try:
            if w.LevelId != lb.Id:
                continue
            c = location_curve(w)
            if c is not None:
                existing.append((c, w))
        except Exception:
            pass
    E = errs()
    out = {"dry_run": dry, "tipo": element_name(wt), "nivel_base": lb.Name, "nivel_tope": lt.Name if lt else None,
           "altura_mm": mm(height), "plan": [], "creadas": [], "existian": [], "errores": [], "excepciones": E}
    jobs = []
    for pa, pb, tag in segs:
        a = DB.XYZ(pa[0], pa[1], z)
        b = DB.XYZ(pb[0], pb[1], z)
        if a.DistanceTo(b) < ft(100):
            out["errores"].append([tag, "tramo menor a 100 mm"])
            continue
        dup = None
        for c, w in existing:
            if same_segment(c, a, b, tol):
                dup = w
                break
        out["plan"].append({"muro": tag, "p0_mm": [mm(a.X), mm(a.Y)], "p1_mm": [mm(b.X), mm(b.Y)],
                            "accion": "existe id %d" % eidv(dup.Id) if dup else "crear"})
        if dup is None:
            jobs.append((a, b, tag))
        else:
            out["existian"].append(tag)
    if dry:
        return out
    structural = bool(P.get("estructural", True))
    off = ft(float(P.get("offset_base_mm", 0.0)))
    loc_line = int(P.get("linea_ubicacion", 0))

    def work():
        for a, b, tag in jobs:
            try:
                line = DB.Line.CreateBound(a, b)
                w = DB.Wall.Create(doc, line, wt.Id, lb.Id, height, off, False, structural)
                if lt is not None:
                    set_param(w, DB.BuiltInParameter.WALL_HEIGHT_TYPE, lt.Id)
                if loc_line:
                    set_param(w, DB.BuiltInParameter.WALL_KEY_REF_PARAM, loc_line)
                mark(w, marker + ":" + tag)
                doc.Regenerate()
                rec = {"muro": tag, "id": eidv(w.Id), "ancho_mm": mm(w.Width), "longitud_mm": param_mm(w, DB.BuiltInParameter.CURVE_ELEM_LENGTH),
                       "tope": level_name(doc, w.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()) if lt is not None else "altura %.0f" % mm(height)}
                out["creadas"].append(rec)
            except Exception as ex:
                out["errores"].append([tag, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: muros", work)
    out["ok"] = not out["errores"]
    return out
