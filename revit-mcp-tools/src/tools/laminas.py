# -*- coding: utf-8 -*-
"""laminas: crea laminas con cajetin y coloca vistas y tablas en ellas.

Parametros:
  sheets:      lista de {"number": "E-01", "name": "PLANTA NIVEL 1",
                          "views": ["PLANTA NIVEL 1", "TABLA DE COLUMNAS"]}.
               Los nombres pueden ser vistas o tablas (ViewSchedule).
  titleblock:  nombre del tipo de cajetin; vacio = el primero cargado.
  layout:      "principal" (default: la primera vista ocupa el area util menos una franja
               derecha donde se apilan las demas, tipico planta + tablas) |
               "fila" (reparto en una fila) | "grilla" (2 columnas).
  strip_frac:  ancho de la franja derecha como fraccion del area util (default 0.22).
  margin_mm:   margen desde el borde de la lamina (default 15).
  reserved_right_mm: ancho de la columna del cajetin, que no es area util (default 120:
               cubre los cajetines de Autodesk; medirlo si el cajetin es propio).
  auto_scale:  True ajusta la escala de la vista a su celda: la baja si desborda y la sube si
               ocupa menos de la mitad (escalas 1:50..1:500, objetivo ~85 % de la celda);
               False solo reporta (default True). No toca vistas 3D.
  replace:     True borra la lamina previa con el mismo numero.
  dry_run:     True solo informa (default True).
Cada viewport se reporta con 'desborda' (mm fuera de su celda) porque una vista
que se sale de la lamina es el defecto mas comun y la API no avisa. Aun asi:
verificar con ver_vista antes de entregar.
"""


def run(doc, uidoc, DB, P):
    sheets = P.get("sheets") or []
    if not sheets:
        raise Exception("falta 'sheets'")
    dry = bool(P.get("dry_run", True))
    layout = P.get("layout", "principal")
    strip = float(P.get("strip_frac", 0.22))
    margin = ft(float(P.get("margin_mm", 15.0)))
    reserved = ft(float(P.get("reserved_right_mm", 120.0)))
    auto_scale = bool(P.get("auto_scale", True))
    ESCALAS = [50, 75, 100, 125, 150, 200, 250, 300, 400, 500]
    want_tb = P.get("titleblock") or ""
    tb = None
    tbs = symbols(doc, DB.BuiltInCategory.OST_TitleBlocks)
    for s in tbs:
        if not want_tb or element_name(s) == want_tb or family_and_type(s) == want_tb:
            tb = s
            break
    if tb is None:
        raise Exception("no hay cajetin '%s'; cargados: %s" % (want_tb, [family_and_type(s) for s in tbs]))
    existing = dict((s.SheetNumber, s) for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))
    views = {}
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if not v.IsTemplate and v.ViewType != DB.ViewType.DrawingSheet:
            views.setdefault(v.Name, v)
    E = errs()
    out = {"titleblock": family_and_type(tb), "layout": layout, "dry_run": dry, "plan": [], "creadas": [],
           "existian": [], "no_colocadas": [], "errores": [], "excepciones": E}
    jobs = []
    for spec in sheets:
        num = spec.get("number")
        if not num:
            raise Exception("cada lamina necesita 'number'")
        vs = spec.get("views") or []
        faltan = [n for n in vs if n not in views]
        st = "existe" if num in existing else "crear"
        if st == "existe" and P.get("replace"):
            st = "reemplazar"
        out["plan"].append({"number": num, "name": spec.get("name", ""), "accion": st, "views": vs, "vistas_inexistentes": faltan})
        if faltan:
            raise Exception("no existen las vistas %s para la lamina %s" % (faltan, num))
        jobs.append((num, spec.get("name", ""), vs, st))
    if dry:
        return out
    out["vista_activa_cambiada_a"] = leave_view(doc, uidoc, [existing[n].Id for n, _, _, st in jobs if st == "reemplazar"])

    def cells(sheet, n):
        """Celdas (u0, v0, u1, v1) del area util, una por vista, segun layout."""
        o = sheet.Outline
        u0, v0, u1, v1 = o.Min.U + margin, o.Min.V + margin, o.Max.U - margin - reserved, o.Max.V - margin
        if n <= 1:
            return [(u0, v0, u1, v1)]
        if layout == "principal":
            us = u1 - (u1 - u0) * strip
            out_cells = [(u0, v0, us, v1)]
            h = (v1 - v0) / (n - 1)
            for i in range(n - 1):
                out_cells.append((us, v1 - h * (i + 1), u1, v1 - h * i))
            return out_cells
        cols = 2 if layout == "grilla" else n
        rows = int((n + cols - 1) / cols)
        w = (u1 - u0) / cols
        h = (v1 - v0) / rows
        res = []
        for i in range(n):
            c = i % cols
            r = int(i / cols)
            res.append((u0 + w * c, v1 - h * (r + 1), u0 + w * (c + 1), v1 - h * r))
        return res

    def center(cell):
        return DB.XYZ((cell[0] + cell[2]) / 2.0, (cell[1] + cell[3]) / 2.0, 0)

    def overflow_mm(vp, cell):
        b = vp.GetBoxOutline()
        dx = max(0.0, cell[0] - b.MinimumPoint.X, b.MaximumPoint.X - cell[2])
        dy = max(0.0, cell[1] - b.MinimumPoint.Y, b.MaximumPoint.Y - cell[3])
        return mm(max(dx, dy)), (b.MaximumPoint.X - b.MinimumPoint.X, b.MaximumPoint.Y - b.MinimumPoint.Y)

    def work():
        activate(tb)
        for num, name, vs, st in jobs:
            try:
                if st == "existe":
                    out["existian"].append(num)
                    continue
                if st == "reemplazar":
                    doc.Delete(existing[num].Id)
                sh = DB.ViewSheet.Create(doc, tb.Id)
                sh.SheetNumber = num
                if name:
                    sh.Name = name
                doc.Regenerate()
                cs = cells(sh, len(vs))
                placed = []
                for vname, cell in zip(vs, cs):
                    v = views[vname]
                    pt = center(cell)
                    try:
                        if isinstance(v, DB.ViewSchedule):
                            # las tablas se anclan por su esquina superior izquierda
                            si = DB.ScheduleSheetInstance.Create(doc, sh.Id, v.Id, DB.XYZ(cell[0], cell[3], 0))
                            doc.Regenerate()
                            rec = {"vista": vname, "tipo": "tabla", "desborda_mm": None}
                            try:
                                bb = si.get_BoundingBox(sh)
                                dy = max(0.0, cell[1] - bb.Min.Y)
                                dx = max(0.0, bb.Max.X - cell[2])
                                rec["desborda_mm"] = mm(max(dx, dy))
                                rec["alto_mm"] = mm(bb.Max.Y - bb.Min.Y)
                                if rec["desborda_mm"] > 0:
                                    rec["nota"] = "la tabla no cabe en su celda: menos filas (itemize=False), otra lamina o partirla"
                            except Exception as ex:
                                note(E, "bbox tabla " + vname, ex)
                            placed.append(rec)
                            continue
                        if not DB.Viewport.CanAddViewToSheet(doc, sh.Id, v.Id):
                            out["no_colocadas"].append([num, vname, "CanAddViewToSheet=False (ya esta en otra lamina?)"])
                            continue
                        vp = DB.Viewport.Create(doc, sh.Id, v.Id, pt)
                        doc.Regenerate()
                        ov, size = overflow_mm(vp, cell)
                        rec = {"vista": vname, "tipo": "viewport", "escala": v.Scale, "desborda_mm": ov}
                        cw, ch = cell[2] - cell[0], cell[3] - cell[1]
                        need = max(size[0] / cw, size[1] / ch)   # fraccion de la celda que ocupa
                        # auto_scale ajusta en ambos sentidos: achica si desborda y agranda si
                        # la vista ocupa menos de la mitad de su celda (objetivo ~85 %).
                        if auto_scale and hasattr(v, "Scale") and (ov > 0 or need < 0.5) and not isinstance(v, DB.View3D):
                            target = v.Scale * need / 0.85
                            for s in ESCALAS:
                                if s >= target:
                                    v.Scale = s
                                    break
                            doc.Regenerate()
                            vp.SetBoxCenter(pt)
                            doc.Regenerate()
                            ov2, _ = overflow_mm(vp, cell)
                            rec["escala_ajustada"] = v.Scale
                            rec["desborda_mm"] = ov2
                        placed.append(rec)
                    except Exception as ex:
                        out["no_colocadas"].append([num, vname, "%s: %s" % (type(ex).__name__, str(ex)[:120])])
                out["creadas"].append({"number": num, "name": name, "id": eidv(sh.Id), "colocadas": placed})
            except Exception as ex:
                out["errores"].append([num, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: laminas", work)
    out["ok"] = not out["errores"]
    return out
