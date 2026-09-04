# -*- coding: utf-8 -*-
"""acero_columnas: genera el acero de columnas rectangulares de hormigon desde una regla.

Nueva (no existia como pushbutton: AceroColumnasC6 copiaba el armado de una
columna de referencia). Reglas de geometria iguales a acero_vigas: estribo
metido su radio para que la cara exterior caiga al recubrimiento, barras
longitudinales por dentro del estribo, distribucion perimetral por caras,
estribos en tres zonas (confinada abajo - central - confinada arriba) por
MaximumSpacing, opcionalmente empalme (lap) que asoma por encima del tope.

Parametros (metros):
  columns:  lista de ElementId; o filtro {"view_name","levels","types"}
  regla: {
     "barras": {"diam": "1\\"", "n_b": 3, "n_h": 4}   barras por cara: n_b en cada cara
                 de ancho b, n_h en cada cara de peralte h (esquinas compartidas);
                 total = 2*n_b + 2*n_h - 4
     "estribo_diam": "3/8\\"", "esp_confinado_m": 0.10, "esp_central_m": 0.20,
     "long_confinada_m": null   (default max(h, luz/6, 0.45): ACI 318 18.7.5.1)
     "estribo_interno": false   (segundo estribo mas estrecho, 50 % de b)
     "lap_m": 0.0               (largo de empalme que sobresale por el tope) }
  reglas_por_tipo: {"C1": regla, ...} opcional; manda sobre 'regla'
  rec_m: 0.04, gancho: "Standard - 135 deg." (si no esta, se intenta 90)
  diametros_m, b_m/h_m (default si el tipo no expone b y h), purge, marca, dry_run
  limites: {"esp_confinado_max_m","esp_central_max_m"} (default min(b/4,6db,0.15) y min(16db,48dbe,b))
Ejes locales: X = b (a lo ancho del tipo), Y = h, Z = vertical; se leen de la
transformada de la instancia, asi que columnas giradas se arman bien.
SIN VERIFICAR EN VIVO en la conversion.
"""


def run(doc, uidoc, DB, P):
    from System.Collections.Generic import List
    M = 0.3048
    DIAM = P.get("diametros_m") or {
        "1\"": 0.0254, "#8": 0.0254, "3/4\"": 0.01905, "#6": 0.01905,
        "5/8\"": 0.01588, "#5": 0.01588, "1/2\"": 0.0127, "#4": 0.0127,
        "3/8\"": 0.00953, "#3": 0.00953}
    ALIAS = {"1\"": ["1\"", "#8", "N8", "25M"], "3/4\"": ["3/4\"", "#6", "N6", "20M"],
             "5/8\"": ["5/8\"", "#5", "N5", "16M"], "1/2\"": ["1/2\"", "#4", "N4", "13M"],
             "3/8\"": ["3/8\"", "#3", "N3", "10M"]}
    rec = float(P.get("rec_m", 0.04)) / M
    marca = P.get("marca", "MCP:acero-col")
    dry = bool(P.get("dry_run", False))
    purge = bool(P.get("purge", True))
    regla_base = P.get("regla")
    reglas_tipo = P.get("reglas_por_tipo") or {}
    limites = P.get("limites") or {}
    if regla_base is None and not reglas_tipo:
        raise Exception("falta 'regla' o 'reglas_por_tipo'")
    cols = []
    if P.get("columns"):
        for i in P["columns"]:
            e = doc.GetElement(DB.ElementId(int(i)))
            if e is not None:
                cols.append(e)
    else:
        f = P.get("filtro") or {}
        view = find_view(doc, f["view_name"]) if f.get("view_name") else None
        lv = set(f.get("levels") or [])
        ty = set(f.get("types") or [])
        for c in collector(doc, DB.BuiltInCategory.OST_StructuralColumns, view):
            if ty and (type_name(doc, c) or "") not in ty:
                continue
            if lv:
                p = c.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
                if p is None or (level_name(doc, p.AsElementId()) or "") not in lv:
                    continue
            cols.append(c)
    if not cols:
        raise Exception("no hay columnas objetivo")
    barras_doc = dict((element_name(bt), bt) for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType))

    def resolver(diam):
        for a in ALIAS.get(diam, [diam]):
            if a in barras_doc:
                return barras_doc[a]
        return None

    def dm(diam):
        return DIAM.get(diam, 0.0254)
    ganchos = dict((element_name(h), h) for h in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarHookType))
    gancho = ganchos.get(P.get("gancho", "Standard - 135 deg.")) or ganchos.get("Standard - 90 deg.")
    out = {"columnas": len(cols), "dry_run": dry, "armadas": [], "fallos": [],
           "catalogo": sorted(barras_doc.keys()), "gancho": element_name(gancho) if gancho else None}
    estilo_std = DB.Structure.RebarStyle.Standard
    estilo_est = DB.Structure.RebarStyle.StirrupTie

    def lin(n, half):
        if n <= 1:
            return [0.0]
        paso = 2.0 * half / (n - 1)
        return [-half + i * paso for i in range(n)]

    for col in cols:
        cid = eidv(col.Id)
        tipo = type_name(doc, col) or "?"
        regla = reglas_tipo.get(tipo) or regla_base
        if regla is None:
            out["fallos"].append({"id": cid, "motivo": "sin regla para el tipo '%s'" % tipo})
            continue
        rb = regla["barras"]
        if not dry and (resolver(rb["diam"]) is None or resolver(regla["estribo_diam"]) is None):
            out["fallos"].append({"id": cid, "motivo": "tipos de barra ausentes: %s / %s" % (rb["diam"], regla["estribo_diam"])})
            continue
        sym = doc.GetElement(col.GetTypeId())
        pb = sym.LookupParameter("b")
        ph = sym.LookupParameter("h")
        b = pb.AsDouble() if pb is not None else float(P.get("b_m", 0.40)) / M
        h = ph.AsDouble() if ph is not None else float(P.get("h_m", 0.40)) / M
        # ejes locales desde la transformada de la instancia
        try:
            T = col.GetTransform()
            ex = T.BasisX
            ey = T.BasisY
            org = T.Origin
        except Exception:
            ex = DB.XYZ.BasisX
            ey = DB.XYZ.BasisY
            org = col.Location.Point
        ex = DB.XYZ(ex.X, ex.Y, 0).Normalize()
        ey = DB.XYZ(ey.X, ey.Y, 0).Normalize()
        bb = col.get_BoundingBox(None)
        z0 = bb.Min.Z
        z1 = bb.Max.Z
        try:
            bl = doc.GetElement(col.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId())
            tl = doc.GetElement(col.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).AsElementId())
            z0 = bl.Elevation + (col.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).AsDouble() or 0.0)
            z1 = tl.Elevation + (col.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).AsDouble() or 0.0)
        except Exception:
            pass
        luz = z1 - z0
        est_r = dm(regla["estribo_diam"]) / 2.0 / M
        long_r = dm(rb["diam"]) / 2.0 / M
        inset = est_r + long_r
        half_b_est = b / 2.0 - rec - est_r
        half_h_est = h / 2.0 - rec - est_r
        half_b = half_b_est - inset
        half_h = half_h_est - inset
        lconf = regla.get("long_confinada_m")
        lconf = (float(lconf) / M) if lconf else max(h, b, luz / 6.0, 0.45 / M)
        lap = float(regla.get("lap_m", 0.0)) / M
        n_b, n_h = int(rb["n_b"]), int(rb["n_h"])
        total = 2 * n_b + 2 * n_h - 4
        # verificaciones (ACI 318-19 18.7.5.3 / 25.7.2.1 aproximadas)
        verif = []
        dbl, dbe = dm(rb["diam"]), dm(regla["estribo_diam"])
        lim_conf = limites.get("esp_confinado_max_m") or min(min(b, h) * M / 4.0, 6 * dbl, 0.15)
        lim_cen = limites.get("esp_central_max_m") or min(16 * dbl, 48 * dbe, min(b, h) * M)
        if regla["esp_confinado_m"] > lim_conf + 1e-6:
            verif.append("estribo confinado %.3f > limite %.3f" % (regla["esp_confinado_m"], lim_conf))
        if regla["esp_central_m"] > lim_cen + 1e-6:
            verif.append("estribo central %.3f > limite %.3f" % (regla["esp_central_m"], lim_cen))
        for n, half, cara in ((n_b, half_b, "b"), (n_h, half_h, "h")):
            if n > 1:
                libre = (2.0 * half * M - n * dbl) / (n - 1)
                if libre < max(1.5 * dbl, 0.04) - 1e-6:
                    verif.append("cara %s: separacion libre %.3f < minimo %.3f (%d barras)" % (cara, libre, max(1.5 * dbl, 0.04), n))
        plan = {"id": cid, "tipo": tipo, "b_m": round(b * M, 3), "h_m": round(h * M, 3),
                "altura_m": round(luz * M, 3), "barras_total": total,
                "long_confinada_m": round(lconf * M, 3), "verificaciones": verif, "elementos": []}
        if dry:
            out["armadas"].append(plan)
            continue
        hecho = plan["elementos"]
        # posiciones perimetrales (sin duplicar esquinas)
        pos = set()
        for x in lin(n_b, half_b):
            pos.add((round(x, 6), round(-half_h, 6)))
            pos.add((round(x, 6), round(half_h, 6)))
        for y in lin(n_h, half_h):
            pos.add((round(-half_b, 6), round(y, 6)))
            pos.add((round(half_b, 6), round(y, 6)))
        bt_l = resolver(rb["diam"])
        bt_e = resolver(regla["estribo_diam"])
        t = DB.Transaction(doc, "tools: acero columna %d" % cid)
        t.Start()
        try:
            if purge:
                borrar = List[DB.ElementId]()
                for r_ in collector(doc, DB.BuiltInCategory.OST_Rebar):
                    try:
                        if eidv(r_.GetHostId()) == cid and comment(r_) == marca:
                            borrar.Add(r_.Id)
                    except Exception:
                        pass
                if borrar.Count:
                    doc.Delete(borrar)
                plan["purgadas"] = borrar.Count
            for i, (x, y) in enumerate(sorted(pos)):
                base = org + ex.Multiply(x) + ey.Multiply(y)
                pa = DB.XYZ(base.X, base.Y, z0 + rec)
                pz = DB.XYZ(base.X, base.Y, z1 + lap)
                curvas = List[DB.Curve]()
                curvas.Add(DB.Line.CreateBound(pa, pz))
                barra = DB.Structure.Rebar.CreateFromCurves(doc, estilo_std, bt_l, col, ex, curvas,
                                                            DB.Structure.BarTerminationsData(doc), True, True)
                if barra is None:
                    raise Exception("CreateFromCurves devolvio None en barra %d" % i)
                pc = barra.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if pc is not None and not pc.IsReadOnly:
                    pc.Set(marca)
                hecho.append({"e": "long_%d" % (i + 1), "id": eidv(barra.Id)})

            def estribo_zona(za, zb, esp, etiqueta, factor=1.0):
                if zb - za < (esp / M) * 0.5:
                    return
                hb = half_b_est * factor
                hh = half_h_est
                esq = []
                for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    q = org + ex.Multiply(sx * hb) + ey.Multiply(sy * hh)
                    esq.append(DB.XYZ(q.X, q.Y, za))
                curvas = List[DB.Curve]()
                for i in range(4):
                    curvas.Add(DB.Line.CreateBound(esq[i], esq[(i + 1) % 4]))
                term = DB.Structure.BarTerminationsData(doc)
                if gancho is not None:
                    for e in ("Start", "End"):
                        try:
                            setattr(term, "HookTypeIdAt" + e, gancho.Id)
                        except Exception:
                            pass
                barra = DB.Structure.Rebar.CreateFromCurves(doc, estilo_est, bt_e, col, DB.XYZ.BasisZ, curvas, term, True, True)
                if barra is None:
                    raise Exception("estribo %s: CreateFromCurves devolvio None" % etiqueta)
                barra.GetShapeDrivenAccessor().SetLayoutAsMaximumSpacing(esp / M, zb - za, True, True, True)
                pc = barra.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if pc is not None and not pc.IsReadOnly:
                    pc.Set(marca)
                hecho.append({"e": etiqueta, "id": eidv(barra.Id), "esp_m": esp})
            za = z0 + rec + est_r
            zb = z1 - rec - est_r
            if zb - za < 2 * lconf:
                estribo_zona(za, zb, regla["esp_confinado_m"], "estribo_unico")
            else:
                estribo_zona(za, za + lconf, regla["esp_confinado_m"], "estribo_base")
                estribo_zona(za + lconf, zb - lconf, regla["esp_central_m"], "estribo_central")
                estribo_zona(zb - lconf, zb, regla["esp_confinado_m"], "estribo_tope")
            if regla.get("estribo_interno"):
                estribo_zona(za, za + lconf, regla["esp_confinado_m"], "estribo_int_base", 0.5)
                estribo_zona(zb - lconf, zb, regla["esp_confinado_m"], "estribo_int_tope", 0.5)
            t.Commit()
            out["armadas"].append(plan)
        except Exception as ex_:
            t.RollBack()
            out["fallos"].append({"id": cid, "tipo": tipo, "motivo": str(ex_)[:200]})
    out["ok"] = not out["fallos"]
    return out
