# -*- coding: utf-8 -*-
"""zapatas: coloca una zapata aislada bajo cada columna seleccionada, idempotente.

Parametros:
  tipo:       nombre del tipo de zapata (familia de Structural Foundation). Obligatorio.
  nivel:      nombre del nivel donde se colocan (tipicamente el de cimentacion). Obligatorio.
  columnas:   "nivel:<nombre>" (columnas cuyo nivel base es ese), "marker:<prefijo>" (columnas con
              esa marca en Comments), o lista de ids. Obligatorio.
  offset_mm:  desfase vertical de la zapata respecto al nivel (default 0).
  rotar_con_columna: True gira la zapata como la columna (default True).
  marker:     Comments (default "AGENTE:ZAP"); se agrega ":<id columna>".
  tolerancia_mm: para detectar una zapata existente en el mismo punto (default 50).
  dry_run:    True solo informa (default True).
Devuelve por zapata creada el hueco entre su cara superior y la base de la
columna (gap_mm): si no es ~0, la columna no apoya en la zapata.
"""


def run(doc, uidoc, DB, P):
    dry = bool(P.get("dry_run", True))
    marker = P.get("marker", "AGENTE:ZAP")
    tol = ft(float(P.get("tolerancia_mm", 50.0)))
    sym = need_symbol(doc, DB.BuiltInCategory.OST_StructuralFoundation, P.get("tipo"), "zapata")
    lv = need_level(doc, P.get("nivel"))
    sel = P.get("columnas")
    if not sel:
        raise Exception("falta 'columnas'")
    cols = []
    allc = list(collector(doc, DB.BuiltInCategory.OST_StructuralColumns))
    if isinstance(sel, str) and sel.startswith("nivel:"):
        want = need_level(doc, sel[6:])
        for c in allc:
            try:
                p = c.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
                if (p is not None and p.AsElementId() == want.Id) or c.LevelId == want.Id:
                    cols.append(c)
            except Exception:
                pass
    elif isinstance(sel, str) and sel.startswith("marker:"):
        cols = [c for c in allc if has_mark(c, sel[7:])]
    elif isinstance(sel, list):
        ids = set(int(i) for i in sel)
        cols = [c for c in allc if eidv(c.Id) in ids]
    else:
        raise Exception("columnas debe ser 'nivel:<n>', 'marker:<m>' o lista de ids")
    if not cols:
        raise Exception("ninguna columna seleccionada")
    # solo las columnas del nivel base mas bajo del conjunto: una zapata por
    # apoyo, no una por cada tramo de columna apilado (verificado: sin este
    # filtro, 4 niveles de columnas dieron 80 zapatas en 20 puntos).
    def base_elev(c):
        try:
            p = c.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
            lid = p.AsElementId() if p is not None else c.LevelId
            return doc.GetElement(lid).Elevation
        except Exception:
            return None
    elevs = [e for e in (base_elev(c) for c in cols) if e is not None]
    descartadas = 0
    if elevs and bool(P.get("solo_nivel_mas_bajo", True)):
        lo = min(elevs)
        keep = []
        for c in cols:
            e = base_elev(c)
            if e is not None and abs(e - lo) < ft(10):
                keep.append(c)
            else:
                descartadas += 1
        cols = keep
    existing = []
    for f in collector(doc, DB.BuiltInCategory.OST_StructuralFoundation):
        try:
            loc = f.Location
            if loc is not None and hasattr(loc, "Point"):
                existing.append((loc.Point, f))
        except Exception:
            pass
    E = errs()
    out = {"dry_run": dry, "tipo": family_and_type(sym), "nivel": lv.Name, "columnas": len(cols),
           "columnas_descartadas_por_nivel": descartadas, "plan": [],
           "creadas": [], "existian": [], "errores": [], "excepciones": E}
    jobs = []
    scheduled = []
    for c in cols:
        try:
            loc = c.Location
            if loc is None or not hasattr(loc, "Point"):
                out["errores"].append([eidv(c.Id), "columna sin punto de ubicacion (inclinada?)"])
                continue
            p = loc.Point
            # Z = 0: para Footing, NewFamilyInstance suma la Z del punto a la
            # elevacion del nivel (verificado: con Z = nivel quedo al doble).
            pt = DB.XYZ(p.X, p.Y, 0.0)
            dup = None
            for ep, f in existing:
                if close_xy(ep, pt, tol) and abs(ep.Z - lv.Elevation) < ft(500):
                    dup = f
                    break
            same_run = any(close_xy(sp, pt, tol) for sp in scheduled)
            accion = "existe id %d" % eidv(dup.Id) if dup else ("repetida en esta corrida" if same_run else "crear")
            out["plan"].append({"columna": eidv(c.Id), "xy_mm": [mm(p.X), mm(p.Y)], "accion": accion})
            if dup is None and not same_run:
                jobs.append((c, pt, loc.Rotation if hasattr(loc, "Rotation") else 0.0))
                scheduled.append(pt)
            else:
                out["existian"].append(eidv(c.Id))
        except Exception as ex:
            note(E, "columna %d" % eidv(c.Id), ex)
    if dry:
        return out
    off = ft(float(P.get("offset_mm", 0.0)))
    rotate = bool(P.get("rotar_con_columna", True))

    def work():
        activate(sym)
        for c, pt, rot in jobs:
            try:
                z = doc.Create.NewFamilyInstance(pt, sym, lv, DB.Structure.StructuralType.Footing)
                if off:
                    try:
                        set_param(z, DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM, mm(off))
                    except Exception as ex:
                        note(E, "offset", ex)
                if rotate and abs(rot) > 1e-6:
                    axis = DB.Line.CreateBound(pt, DB.XYZ(pt.X, pt.Y, pt.Z + 1.0))
                    DB.ElementTransformUtils.RotateElement(doc, z.Id, axis, rot)
                mark(z, marker + ":%d" % eidv(c.Id))
                doc.Regenerate()
                rec = {"columna": eidv(c.Id), "id": eidv(z.Id)}
                try:
                    bz = z.get_BoundingBox(None)
                    bc = c.get_BoundingBox(None)
                    rec["tope_zapata_mm"] = mm(bz.Max.Z)
                    rec["base_columna_mm"] = mm(bc.Min.Z)
                    rec["gap_mm"] = mm(bc.Min.Z - bz.Max.Z)
                except Exception as ex:
                    note(E, "gap", ex)
                out["creadas"].append(rec)
            except Exception as ex:
                out["errores"].append([eidv(c.Id), "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: zapatas", work)
    out["ok"] = not out["errores"]
    return out
