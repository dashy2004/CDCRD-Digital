# -*- coding: utf-8 -*-
"""columnas: coloca columnas estructurales en intersecciones de ejes o en puntos, idempotente.

Parametros:
  tipo:          nombre del tipo de columna ('Tipo' o 'Familia: Tipo'). Obligatorio.
  nivel_base:    nombre del nivel base. Obligatorio.
  nivel_tope:    nombre del nivel tope. Obligatorio.
  posiciones:    lista de pares de ejes [["A","1"], ["B","1"], ...] o "todas" (todas las
                 intersecciones entre ejes de X constante y de Y constante); se puede acotar
                 con "ejes": ["A","B","1","2"] para usar solo esos.
  puntos_mm:     lista de [x, y] adicionales (opcional).
  offset_base_mm / offset_tope_mm: desfases (default 0).
  rotacion_deg:  giro en planta (default 0).
  marker:        Comments de lo creado (default "AGENTE:COL"); se agrega ":<eje-eje>".
  tolerancia_mm: distancia bajo la cual una columna existente en el mismo nivel cuenta
                 como "ya esta" y no se duplica (default 50).
  dry_run:       True solo informa (default True).
Devuelve creadas / existian / errores y la relectura del modelo: cuantas
columnas con esa marca hay ahora en el nivel base (lo que hay, no lo que se
pidio; E-041/E-044).
"""


def run(doc, uidoc, DB, P):
    import math
    dry = bool(P.get("dry_run", True))
    marker = P.get("marker", "AGENTE:COL")
    tol = ft(float(P.get("tolerancia_mm", 50.0)))
    sym = need_symbol(doc, DB.BuiltInCategory.OST_StructuralColumns, P.get("tipo"), "columna")
    lb = need_level(doc, P.get("nivel_base"))
    lt = need_level(doc, P.get("nivel_tope"))
    if lt.Elevation <= lb.Elevation:
        raise Exception("nivel_tope debe estar por encima de nivel_base")
    gi = grids_info(doc)
    pts = []
    pos = P.get("posiciones")
    if pos == "todas":
        sel = set(P.get("ejes") or [])
        gx = [k for k, v in gi.items() if v["dir"] == "X" and (not sel or k in sel)]
        gy = [k for k, v in gi.items() if v["dir"] == "Y" and (not sel or k in sel)]
        for a in gx:
            for b in gy:
                x, y = grid_point(gi, a, b)
                pts.append((x, y, "%s-%s" % (a, b)))
    elif pos:
        for a, b in pos:
            x, y = grid_point(gi, a, b)
            pts.append((x, y, "%s-%s" % (a, b)))
    for p in (P.get("puntos_mm") or []):
        pts.append((ft(p[0]), ft(p[1]), "pt(%.0f,%.0f)" % (p[0], p[1])))
    if not pts:
        raise Exception("sin posiciones: pase posiciones, 'todas' o puntos_mm")
    # existentes en el nivel base
    existing = []
    for c in collector(doc, DB.BuiltInCategory.OST_StructuralColumns):
        try:
            if c.LevelId == lb.Id or (c.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM) is not None and
                                      c.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId() == lb.Id):
                loc = c.Location
                if loc is not None and hasattr(loc, "Point"):
                    existing.append((loc.Point, c))
        except Exception:
            pass
    E = errs()
    out = {"dry_run": dry, "tipo": family_and_type(sym), "nivel_base": lb.Name, "nivel_tope": lt.Name,
           "plan": [], "creadas": [], "existian": [], "errores": [], "excepciones": E}
    jobs = []
    for x, y, tag in pts:
        # Z = 0: la base la fija el nivel; la Z del punto se ignora en columnas
        # (verificado) pero en zapatas se suma al nivel, asi que se unifica en 0.
        pt = DB.XYZ(x, y, 0.0)
        dup = None
        for ep, c in existing:
            if close_xy(ep, pt, tol):
                dup = c
                break
        out["plan"].append({"pos": tag, "xy_mm": [mm(x), mm(y)], "accion": "existe id %d" % eidv(dup.Id) if dup else "crear"})
        if dup is None:
            jobs.append((pt, tag))
        else:
            out["existian"].append(tag)
    if dry:
        return out
    rot = math.radians(float(P.get("rotacion_deg", 0.0)))
    ob = ft(float(P.get("offset_base_mm", 0.0)))
    ot = ft(float(P.get("offset_tope_mm", 0.0)))

    def work():
        activate(sym)
        for pt, tag in jobs:
            try:
                col = doc.Create.NewFamilyInstance(pt, sym, lb, DB.Structure.StructuralType.Column)
                set_param(col, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, lt.Id)
                # los desfases se escriben SIEMPRE, aunque sean 0: al cambiar
                # el nivel tope Revit puede dejar un Top Offset residual
                # (verificado: columnas al ultimo nivel quedaron 2.74 m mas altas).
                set_param(col, DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM, mm(ob))
                set_param(col, DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM, mm(ot))
                if rot:
                    axis = DB.Line.CreateBound(pt, DB.XYZ(pt.X, pt.Y, pt.Z + 1.0))
                    DB.ElementTransformUtils.RotateElement(doc, col.Id, axis, rot)
                mark(col, marker + ":" + tag)
                doc.Regenerate()
                rec = {"pos": tag, "id": eidv(col.Id)}
                try:
                    bb = col.get_BoundingBox(None)
                    rec["base_mm"] = mm(bb.Min.Z)
                    rec["tope_mm"] = mm(bb.Max.Z)
                    esperado = mm(lt.Elevation + ot)
                    if abs(rec["tope_mm"] - esperado) > 10:
                        rec["aviso"] = "tope %.0f != esperado %.0f" % (rec["tope_mm"], esperado)
                except Exception as ex:
                    note(E, "bbox " + tag, ex)
                out["creadas"].append(rec)
            except Exception as ex:
                out["errores"].append([tag, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: columnas", work)
    # relectura
    n = 0
    for c in collector(doc, DB.BuiltInCategory.OST_StructuralColumns):
        try:
            if has_mark(c, marker):
                n += 1
        except Exception as ex:
            note(E, "releer", ex)
    out["relectura"] = {"columnas_con_marca": n, "marker": marker}
    out["ok"] = not out["errores"]
    return out
