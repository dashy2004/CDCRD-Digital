# -*- coding: utf-8 -*-
"""niveles_ejes: crea niveles y ejes de rejilla desde una especificacion, idempotente.

Parametros:
  levels:  lista de {"name": "N1", "elevation_mm": 0}. Los que ya existen (por nombre) se saltan.
  grids:   lista explicita de {"name": "A", "p0_mm": [x, y], "p1_mm": [x, y]}  y/o
  rejilla: forma corta ortogonal:
           {"verticales":   {"nombres": ["A","B","C"], "x_mm": [0, 6000, 12000]},
            "horizontales": {"nombres": ["1","2","3"], "y_mm": [0, 5000, 10000]},
            "margen_mm": 1500}
           'verticales' son ejes de X constante (se extienden en Y); 'horizontales' de Y constante.
           En vez de x_mm/y_mm se puede dar "separaciones_mm": [6000, 6000] y "origen_mm": 0.
  marker:  texto para Comments de lo creado (default "AGENTE:DATUM"). Niveles y ejes no
           tienen Comments en Revit (verificado: 'marca': false); se borran por nombre con
           borrar_por_marca(ejes_nombres=..., niveles_nombres=...).
  dry_run: True solo informa (default True).
Aplica la regla E-099: tras Grid.Create / Level.Create el datum nace sin
extension vertical y no aparece en ninguna planta; se maximiza y se fijan
los extremos al rango de niveles. Devuelve creados / existian / errores y,
de control, cuantos ejes ve la planta mas baja.
"""


def run(doc, uidoc, DB, P):
    dry = bool(P.get("dry_run", True))
    marker = P.get("marker", "AGENTE:DATUM")
    E = errs()
    lv_specs = P.get("levels") or []
    g_specs = list(P.get("grids") or [])
    rej = P.get("rejilla") or {}

    def positions(spec, key):
        if not spec:
            return []
        if spec.get(key):
            return [float(v) for v in spec[key]]
        seps = spec.get("separaciones_mm") or []
        o = float(spec.get("origen_mm", 0.0))
        pos = [o]
        for s in seps:
            pos.append(pos[-1] + float(s))
        return pos

    if rej:
        vx = positions(rej.get("verticales"), "x_mm")
        hy = positions(rej.get("horizontales"), "y_mm")
        vn = (rej.get("verticales") or {}).get("nombres") or []
        hn = (rej.get("horizontales") or {}).get("nombres") or []
        if len(vn) != len(vx) or len(hn) != len(hy):
            raise Exception("rejilla: nombres y posiciones no coinciden (%d/%d verticales, %d/%d horizontales)" % (len(vn), len(vx), len(hn), len(hy)))
        mg = float(rej.get("margen_mm", 1500.0))
        y0, y1 = (min(hy) - mg, max(hy) + mg) if hy else (-mg, mg)
        x0, x1 = (min(vx) - mg, max(vx) + mg) if vx else (-mg, mg)
        for n, x in zip(vn, vx):
            g_specs.append({"name": n, "p0_mm": [x, y0], "p1_mm": [x, y1]})
        for n, y in zip(hn, hy):
            g_specs.append({"name": n, "p0_mm": [x0, y], "p1_mm": [x1, y]})

    existing_lv = dict((l.Name, l) for l in DB.FilteredElementCollector(doc).OfClass(DB.Level))
    existing_g = dict((g.Name, g) for g in DB.FilteredElementCollector(doc).OfClass(DB.Grid))
    out = {"dry_run": dry, "marker": marker, "plan": {"levels": [], "grids": []},
           "creados": {"levels": [], "grids": []}, "existian": {"levels": [], "grids": []},
           "errores": [], "excepciones": E}
    for s in lv_specs:
        out["plan"]["levels"].append([s["name"], float(s["elevation_mm"]), "existe" if s["name"] in existing_lv else "crear"])
    for s in g_specs:
        out["plan"]["grids"].append([s["name"], s["p0_mm"], s["p1_mm"], "existe" if s["name"] in existing_g else "crear"])
    if dry:
        return out

    def work():
        for s in lv_specs:
            name = s["name"]
            if name in existing_lv:
                out["existian"]["levels"].append(name)
                continue
            try:
                lv = DB.Level.Create(doc, ft(s["elevation_mm"]))
                lv.Name = name
                mk = mark(lv, marker)
                existing_lv[name] = lv
                out["creados"]["levels"].append({"name": name, "id": eidv(lv.Id), "elevation_mm": mm(lv.Elevation), "marca": mk})
            except Exception as ex:
                out["errores"].append(["level " + name, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
        doc.Regenerate()
        elevs = [l.Elevation for l in existing_lv.values()]
        bottom = (min(elevs) if elevs else 0.0) - ft(1000)
        top = (max(elevs) if elevs else 0.0) + ft(1500)
        for s in g_specs:
            name = s["name"]
            if name in existing_g:
                out["existian"]["grids"].append(name)
                continue
            try:
                a = xyz_mm(s["p0_mm"][0], s["p0_mm"][1], 0)
                b = xyz_mm(s["p1_mm"][0], s["p1_mm"][1], 0)
                g = DB.Grid.Create(doc, DB.Line.CreateBound(a, b))
                g.Name = name
                mk = mark(g, marker)
                fixes = fix_datum(doc, g, bottom, top)
                existing_g[name] = g
                out["creados"]["grids"].append({"name": name, "id": eidv(g.Id), "extents": fixes, "marca": mk})
            except Exception as ex:
                out["errores"].append(["grid " + name, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
        for lv in out["creados"]["levels"]:
            try:
                fix_datum(doc, doc.GetElement(DB.ElementId(lv["id"])))
            except Exception as ex:
                note(E, "extents level " + lv["name"], ex)
        doc.Regenerate()
    tx(doc, "tools: niveles y ejes", work)
    # control: la planta mas baja ve todos los ejes?
    try:
        plans = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan) if not v.IsTemplate and v.GenLevel is not None]
        if plans:
            low = sorted(plans, key=lambda v: v.GenLevel.Elevation)[0]
            n = DB.FilteredElementCollector(doc, low.Id).OfClass(DB.Grid).GetElementCount()
            out["control"] = {"planta": low.Name, "ejes_visibles": n, "ejes_totales": len(existing_g)}
    except Exception as ex:
        note(E, "control", ex)
    out["ok"] = not out["errores"]
    return out
