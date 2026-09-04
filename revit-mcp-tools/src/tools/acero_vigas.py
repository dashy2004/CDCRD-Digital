# -*- coding: utf-8 -*-
"""acero_vigas: genera el acero de vigas de hormigon a partir de una regla de armado.

Conversion de GenerarAceroVigas (revit-mcp-write) sin la regla de proyecto
embebida: la regla llega como parametro. Geometria verificada en el original
(2026-08-21/23): estribo metido su radio hacia adentro para que la cara
exterior caiga al recubrimiento, barra longitudinal por dentro del estribo,
capas de max N barras con separacion libre, adicionales de apoyo embebidos en
el nudo con gancho solo en el extremo embebido, piel continua por cara,
estribos en tres zonas (confinada - central - confinada) por MaximumSpacing.

Parametros (todo en metros salvo ids):
  beams:        lista de ElementId de vigas; o
  filtro:       {"view_name": ..., "levels": [...], "types": [...]} (alguno de los dos)
  regla: {
     "sup_corrida":        {"cant": 2, "diam": "1\\""},
     "sup_adicional":      {"cant": 2, "diam": "1\\""} | null,
     "inf_corrida":        {"cant": 3, "diam": "1\\""},
     "inf_adicional_nudo": {"cant": 2, "diam": "1\\""} | null,
     "lateral":            {"por_cara": 2, "diam": "1/2\\""} | null,
     "estribo_diam": "3/8\\"", "estribo_esp_confinado_m": 0.10,
     "estribo_esp_central_m": 0.20, "estribo_interno_nudo": false }
  reglas_por_nivel: {"nombre_nivel": regla, ...} (opcional; manda sobre 'regla')
  rec_m: 0.04            recubrimiento a cara exterior de estribo
  fraccion_confinada: 0.25  fraccion de la luz que ocupa cada zona confinada (tope 2h)
  holgura_cara_m: 0.05   primer estribo a esta distancia del extremo de la viga
  embed_nudo_m: 0.30     cuanto entran los adicionales en la columna
  sep_libre_capas_m: 0.025, max_barras_capa: 3
  gancho: "Standard - 90 deg."
  diametros_m: {"1\\"": 0.0254, ...}  (default: catalogo US en pulgadas y #)
  b_m / h_m: seccion por defecto si el tipo no expone parametros "b" y "h"
  purge: true   borra el rebar previo con marca en cada viga antes de armar
  marca: "MCP:acero-viga"
  dry_run: true  no escribe; devuelve por viga la geometria y las verificaciones
  limites: {"esp_confinado_max_m": ..., "esp_central_max_m": ...} opcional; si no
           se dan se calculan como min(d/4, 8db, 24dbe, 0.30) y d/2 (ACI 318 / R-033)
Devuelve por viga: elementos creados o previstos, y "verificaciones" con los
incumplimientos de espaciamiento y de separacion libre entre barras.
SIN VERIFICAR EN VIVO en la conversion (el modelo de referencia era de acero).
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
    FRAC = float(P.get("fraccion_confinada", 0.25))
    holg = float(P.get("holgura_cara_m", 0.05)) / M
    embed = float(P.get("embed_nudo_m", 0.30)) / M
    sep_capas = float(P.get("sep_libre_capas_m", 0.025))
    max_capa = int(P.get("max_barras_capa", 3))
    marca = P.get("marca", "MCP:acero-viga")
    dry = bool(P.get("dry_run", False))
    purge = bool(P.get("purge", True))
    regla_base = P.get("regla")
    reglas_nivel = P.get("reglas_por_nivel") or {}
    limites = P.get("limites") or {}
    if regla_base is None and not reglas_nivel:
        raise Exception("falta 'regla' o 'reglas_por_nivel'")

    # --- vigas objetivo ---------------------------------------------------
    vigas = []
    if P.get("beams"):
        for i in P["beams"]:
            e = doc.GetElement(DB.ElementId(int(i)))
            if e is not None:
                vigas.append(e)
    else:
        f = P.get("filtro") or {}
        view = find_view(doc, f["view_name"]) if f.get("view_name") else None
        lv = set(f.get("levels") or [])
        ty = set(f.get("types") or [])
        for b in collector(doc, DB.BuiltInCategory.OST_StructuralFraming, view):
            if ty and (type_name(doc, b) or "") not in ty:
                continue
            if lv:
                p = b.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                if p is None or (level_name(doc, p.AsElementId()) or "") not in lv:
                    continue
            vigas.append(b)
    if not vigas:
        raise Exception("no hay vigas objetivo (ids vacios o filtro sin resultados)")

    # --- catalogo ---------------------------------------------------------
    barras_doc = {}
    for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType):
        barras_doc[element_name(bt)] = bt

    def resolver(diam):
        for a in ALIAS.get(diam, [diam]):
            if a in barras_doc:
                return barras_doc[a]
        return None

    def dm(diam):
        return DIAM.get(diam, 0.0254)
    ganchos = dict((element_name(h), h) for h in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarHookType))
    gancho = ganchos.get(P.get("gancho", "Standard - 90 deg."))
    shape_t1 = None
    for sh in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarShape):
        if element_name(sh) == P.get("forma_estribo", "T1"):
            shape_t1 = sh
    out = {"vigas": len(vigas), "dry_run": dry, "armadas": [], "fallos": [],
           "catalogo": sorted(barras_doc.keys()), "gancho_ok": gancho is not None,
           "forma_estribo_ok": shape_t1 is not None}
    if not dry and gancho is None:
        raise Exception("no esta cargado el gancho '%s'; disponibles: %s" % (P.get("gancho", "Standard - 90 deg."), sorted(ganchos)))

    def offsets_y(n, media):
        if n <= 1:
            return [0.0]
        paso = (2.0 * media) / (n - 1)
        return [-media + i * paso for i in range(n)]

    estilo_std = DB.Structure.RebarStyle.Standard
    estilo_est = DB.Structure.RebarStyle.StirrupTie

    for v in vigas:
        vid = eidv(v.Id)
        tipo = type_name(doc, v) or "?"
        nivel = None
        try:
            p = v.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            nivel = level_name(doc, p.AsElementId()) if p is not None else None
        except Exception:
            pass
        regla = reglas_nivel.get(nivel) or regla_base
        if regla is None:
            out["fallos"].append({"id": vid, "motivo": "sin regla para el nivel '%s'" % nivel})
            continue
        faltan = []
        for campo in ("sup_corrida", "sup_adicional", "inf_corrida", "inf_adicional_nudo"):
            r = regla.get(campo)
            if r and resolver(r["diam"]) is None:
                faltan.append(r["diam"])
        if regla.get("lateral") and resolver(regla["lateral"]["diam"]) is None:
            faltan.append(regla["lateral"]["diam"])
        if resolver(regla["estribo_diam"]) is None:
            faltan.append(regla["estribo_diam"])
        if faltan and not dry:
            out["fallos"].append({"id": vid, "motivo": "tipos de barra ausentes: %s" % sorted(set(faltan))})
            continue
        c = location_curve(v)
        if c is None:
            out["fallos"].append({"id": vid, "motivo": "sin curva"})
            continue
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        if abs(p1.Z - p0.Z) > 0.01:
            out["fallos"].append({"id": vid, "motivo": "viga inclinada, no soportada"})
            continue
        luz = p0.DistanceTo(p1)
        sym = doc.GetElement(v.GetTypeId())
        pb = sym.LookupParameter("b")
        ph = sym.LookupParameter("h")
        b = pb.AsDouble() if pb is not None else float(P.get("b_m", 0.35)) / M
        h = ph.AsDouble() if ph is not None else float(P.get("h_m", 0.75)) / M
        dir_x = (p1 - p0).Normalize()
        dir_z = DB.XYZ.BasisZ
        dir_y = dir_z.CrossProduct(dir_x).Normalize()
        est_r = dm(regla["estribo_diam"]) / 2.0 / M
        long_r = max(dm(regla["sup_corrida"]["diam"]), dm(regla["inf_corrida"]["diam"])) / 2.0 / M
        inset = est_r + long_r
        media_est = b / 2.0 - rec - est_r
        media = media_est - inset
        # z real del hormigon: Reference Level + offsets de extremo (la curva corre por el tope)
        try:
            zref = doc.GetElement(v.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM).AsElementId()).Elevation
            e0 = v.get_Parameter(DB.BuiltInParameter.STRUCTURAL_BEAM_END0_ELEVATION)
            e1 = v.get_Parameter(DB.BuiltInParameter.STRUCTURAL_BEAM_END1_ELEVATION)
            z_top = zref + ((e0.AsDouble() if e0 else 0.0) + (e1.AsDouble() if e1 else 0.0)) / 2.0
        except Exception:
            bb = v.get_BoundingBox(None)
            z_top = bb.Max.Z
        z_bot = z_top - h
        z_te = z_top - rec - est_r
        z_be = z_bot + rec + est_r
        z_ta = z_te - inset
        z_ba = z_be + inset
        d_ef = (h - rec - est_r - long_r) * M   # peralte efectivo aprox [m]
        # --- verificaciones de reglamento (informativas) ------------------
        verif = []
        dbe = dm(regla["estribo_diam"])
        dbl = min(dm(regla["sup_corrida"]["diam"]), dm(regla["inf_corrida"]["diam"]))
        lim_conf = limites.get("esp_confinado_max_m") or min(d_ef / 4.0, 8 * dbl, 24 * dbe, 0.30)
        lim_cen = limites.get("esp_central_max_m") or d_ef / 2.0
        if regla["estribo_esp_confinado_m"] > lim_conf + 1e-6:
            verif.append("estribo confinado %.3f > limite %.3f m" % (regla["estribo_esp_confinado_m"], lim_conf))
        if regla["estribo_esp_central_m"] > lim_cen + 1e-6:
            verif.append("estribo central %.3f > limite %.3f m" % (regla["estribo_esp_central_m"], lim_cen))
        for campo in ("sup_corrida", "inf_corrida"):
            r = regla[campo]
            n_capa = min(r["cant"], max_capa) if r["cant"] >= 5 else r["cant"]
            if n_capa > 1:
                libre = (2.0 * media * M - n_capa * dm(r["diam"])) / (n_capa - 1)
                minimo = max(dm(r["diam"]), 0.025)
                if libre < minimo - 1e-6:
                    verif.append("%s: separacion libre %.3f < minimo %.3f m (%d barras en capa, b=%.2f)" % (campo, libre, minimo, n_capa, b * M))
        ancho_conf = min(2 * h, luz * FRAC)
        plan = {"id": vid, "tipo": tipo, "nivel": nivel, "luz_m": round(luz * M, 3),
                "b_m": round(b * M, 3), "h_m": round(h * M, 3), "d_m": round(d_ef, 3),
                "zona_confinada_m": round(ancho_conf * M, 3), "verificaciones": verif,
                "elementos": []}
        if dry:
            out["armadas"].append(plan)
            continue

        def punto(tf, z, yoff=0.0):
            base = p0 + dir_x.Multiply(luz * tf) + dir_y.Multiply(yoff)
            return DB.XYZ(base.X, base.Y, z)
        hecho = plan["elementos"]

        def crear_recta(diam, z, t0, t1, etiqueta, gan, yoff=0.0):
            bt = resolver(diam)
            curvas = List[DB.Curve]()
            curvas.Add(DB.Line.CreateBound(punto(t0, z, yoff), punto(t1, z, yoff)))
            term = DB.Structure.BarTerminationsData(doc)
            ext = {"both": ["Start", "End"], "start": ["Start"], "end": ["End"]}.get(gan, [])
            for e in ext:
                try:
                    setattr(term, "HookTypeIdAt" + e, gancho.Id)
                except Exception:
                    getattr(term, "set_HookTypeIdAt" + e)(gancho.Id)
            barra = DB.Structure.Rebar.CreateFromCurves(doc, estilo_std, bt, v, dir_y, curvas, term, True, True)
            if barra is None:
                raise Exception("CreateFromCurves devolvio None en %s" % etiqueta)
            pc = barra.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if pc is not None and not pc.IsReadOnly:
                pc.Set(marca)
            hecho.append({"e": etiqueta, "id": eidv(barra.Id), "diam": diam})

        def grupo(cant, diam, z, t0, t1, etiqueta, gan, capa_dir):
            if cant >= 5 and capa_dir != 0:
                capas = []
                resto = cant
                while resto > 0:
                    capas.append(min(max_capa, resto))
                    resto -= max_capa
            else:
                capas = [cant]
            paso_z = (dm(diam) + sep_capas) / M
            for ci, n in enumerate(capas):
                zc = z + capa_dir * ci * paso_z
                for i, yo in enumerate(offsets_y(n, media)):
                    crear_recta(diam, zc, t0, t1, "%s_%d_%d" % (etiqueta, ci + 1, i + 1), gan, yo)

        def estribos(x0, x1, esp, etiqueta, factor=1.0):
            if x1 - x0 < (esp / M) * 0.5:
                return
            bt = resolver(regla["estribo_diam"])
            ancho = (b - 2.0 * rec) * factor
            y0, y1 = -ancho / 2.0, ancho / 2.0
            alto = z_te - z_be
            base_xy = p0 + dir_x.Multiply(x0) + dir_y.Multiply(y0)
            origin = DB.XYZ(base_xy.X, base_xy.Y, z_be)
            barra = None
            metodo = None
            if shape_t1 is not None:
                try:
                    barra = DB.Structure.Rebar.CreateFromRebarShape(doc, shape_t1, bt, v, origin, dir_y, DB.XYZ.BasisZ)
                    barra.GetShapeDrivenAccessor().ScaleToBox(origin, dir_y.Multiply(ancho), DB.XYZ.BasisZ.Multiply(alto))
                    metodo = "shape"
                except Exception:
                    if barra is not None:
                        try:
                            doc.Delete(barra.Id)
                        except Exception:
                            pass
                    barra = None
            if barra is None:
                pc0 = p0 + dir_x.Multiply(x0)
                esq = [DB.XYZ((pc0 + dir_y.Multiply(y0)).X, (pc0 + dir_y.Multiply(y0)).Y, z_be),
                       DB.XYZ((pc0 + dir_y.Multiply(y1)).X, (pc0 + dir_y.Multiply(y1)).Y, z_be),
                       DB.XYZ((pc0 + dir_y.Multiply(y1)).X, (pc0 + dir_y.Multiply(y1)).Y, z_te),
                       DB.XYZ((pc0 + dir_y.Multiply(y0)).X, (pc0 + dir_y.Multiply(y0)).Y, z_te)]
                curvas = List[DB.Curve]()
                for i in range(4):
                    curvas.Add(DB.Line.CreateBound(esq[i], esq[(i + 1) % 4]))
                barra = DB.Structure.Rebar.CreateFromCurves(doc, estilo_est, bt, v, dir_x, curvas,
                                                            DB.Structure.BarTerminationsData(doc), True, True)
                metodo = "curvas"
            if barra is None:
                raise Exception("no se pudo crear el estribo %s" % etiqueta)
            barra.GetShapeDrivenAccessor().SetLayoutAsMaximumSpacing(esp / M, x1 - x0, True, True, True)
            pc = barra.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if pc is not None and not pc.IsReadOnly:
                pc.Set(marca)
            hecho.append({"e": etiqueta, "id": eidv(barra.Id), "diam": regla["estribo_diam"], "esp_m": esp, "metodo": metodo})

        t = DB.Transaction(doc, "tools: acero viga %d" % vid)
        t.Start()
        try:
            if purge:
                borrar = List[DB.ElementId]()
                for rb in collector(doc, DB.BuiltInCategory.OST_Rebar):
                    try:
                        if eidv(rb.GetHostId()) == vid and comment(rb) == marca:
                            borrar.Add(rb.Id)
                    except Exception:
                        pass
                if borrar.Count:
                    doc.Delete(borrar)
                plan["purgadas"] = borrar.Count
            t_ei = -embed / luz
            t_ef = 1.0 + embed / luz
            r = regla["sup_corrida"]
            grupo(r["cant"], r["diam"], z_ta, 0.0, 1.0, "sup_corrida", None, -1)
            r = regla.get("sup_adicional")
            if r:
                grupo(r["cant"], r["diam"], z_ta - 0.02, t_ei, FRAC, "sup_adic_ini", "start", -1)
                grupo(r["cant"], r["diam"], z_ta - 0.02, 1.0 - FRAC, t_ef, "sup_adic_fin", "end", -1)
            r = regla["inf_corrida"]
            grupo(r["cant"], r["diam"], z_ba, 0.0, 1.0, "inf_corrida", None, 1)
            r = regla.get("inf_adicional_nudo")
            if r:
                grupo(r["cant"], r["diam"], z_ba + 0.02, t_ei, FRAC, "inf_adic_ini", "start", 1)
                grupo(r["cant"], r["diam"], z_ba + 0.02, 1.0 - FRAC, t_ef, "inf_adic_fin", "end", 1)
            r = regla.get("lateral")
            if r and r.get("por_cara"):
                n = int(r["por_cara"])
                alturas = [z_ba + (k + 1.0) / (n + 1.0) * (z_ta - z_ba) for k in range(n)]
                for ci, yc in enumerate((-media, media)):
                    for hi, zp in enumerate(alturas):
                        crear_recta(r["diam"], zp, 0.0, 1.0, "piel_c%d_h%d" % (ci + 1, hi + 1), None, yc)
            xi = holg
            xf = luz - holg
            if xf - xi < ancho_conf * 2:
                estribos(xi, xf, regla["estribo_esp_confinado_m"], "estribo_unico")
            else:
                estribos(xi, xi + ancho_conf, regla["estribo_esp_confinado_m"], "estribo_ini")
                estribos(xi + ancho_conf, xf - ancho_conf, regla["estribo_esp_central_m"], "estribo_central")
                estribos(xf - ancho_conf, xf, regla["estribo_esp_confinado_m"], "estribo_fin")
            if regla.get("estribo_interno_nudo"):
                estribos(xi, xi + ancho_conf, regla["estribo_esp_confinado_m"], "estribo_int_ini", 0.5)
                estribos(xf - ancho_conf, xf, regla["estribo_esp_confinado_m"], "estribo_int_fin", 0.5)
            t.Commit()
            out["armadas"].append(plan)
        except Exception as ex:
            t.RollBack()
            out["fallos"].append({"id": vid, "tipo": tipo, "motivo": str(ex)[:200]})
    out["ok"] = not out["fallos"]
    return out
