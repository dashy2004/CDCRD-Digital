# -*- coding: utf-8 -*-
"""exportar_proyecto: escribe proyecto.json (esquema de docs/ESQUEMA-PROYECTO.md) desde el modelo de Revit.

Es el puente Revit -> ETABS del repo: la geometria estructural sale en metros
con los bloques del esquema (entrepisos, ejes, columnas, vigas, losas, muros,
zapatas, materiales) y ademas un bloque 'etabs' ya traducido a los argumentos
de las tools del servidor fea (set_stories, define_concrete_material,
define_rect_section, create_objects_by_coordinates). Solo lee el modelo.

Parametros:
  path:      ruta del .json de salida (obligatoria).
  marker:    prefijo de Comments para exportar solo lo creado por un agente (default "": todo).
  origen:    "auto" (default: el minimo X,Y de lo exportado pasa a 0,0) | [x_mm, y_mm] | "modelo" (sin trasladar).
  proyecto:  nombre para meta.proyecto (default "Proyecto Ejemplo"; no se usa el titulo del documento
             para no filtrar nombres de cliente en un archivo que viaja).
  incluir:   bloques a exportar (default todos: columnas, vigas, losas, muros, zapatas).
Secciones: b/h de tipos de hormigon de Autodesk; si la familia no los tiene, se
mide la caja del elemento y se marca seccion.origen = "bbox". Las losas usan el
perfil del sketch; si no se puede leer, su caja (contorno.origen = "bbox").
"""


def run(doc, uidoc, DB, P):
    import io
    import json
    import datetime
    path = P.get("path")
    if not path:
        raise Exception("falta 'path'")
    marker = P.get("marker") or ""
    incluir = set(P.get("incluir") or ["columnas", "vigas", "losas", "muros", "zapatas"])
    E = errs()

    def sel(alias):
        return [e for e in collector(doc, bic_of(alias)) if not marker or has_mark(e, marker)]

    def lvl_of(e):
        try:
            for bip in (DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
                        DB.BuiltInParameter.LEVEL_PARAM, DB.BuiltInParameter.WALL_BASE_CONSTRAINT):
                p = e.get_Parameter(bip)
                if p is not None and p.AsElementId() != DB.ElementId.InvalidElementId:
                    return doc.GetElement(p.AsElementId())
            if e.LevelId != DB.ElementId.InvalidElementId:
                return doc.GetElement(e.LevelId)
        except Exception as ex:
            note(E, "nivel", ex)
        return None

    def mat_of(e):
        try:
            for host in (e, doc.GetElement(e.GetTypeId())):
                p = host.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                if p is not None and p.AsElementId() != DB.ElementId.InvalidElementId:
                    return element_name(doc.GetElement(p.AsElementId()))
        except Exception as ex:
            note(E, "material", ex)
        return None

    def bh_of(e):
        """(b_m, h_m, origen) de la seccion del tipo; bbox como respaldo."""
        t = doc.GetElement(e.GetTypeId())
        for pb, ph in (("b", "h"), ("Width", "Depth"), ("Ancho", "Alto"), ("Width", "Height")):
            b = param_mm(t, pb)
            h = param_mm(t, ph)
            if b and h:
                return round(b / 1000.0, 3), round(h / 1000.0, 3), "tipo"
        try:
            bb = e.get_BoundingBox(None)
            dx, dy, dz = bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y, bb.Max.Z - bb.Min.Z
            c = location_curve(e)
            if c is None:
                return m(min(dx, dy)), m(max(dx, dy)), "bbox"
            d = c.GetEndPoint(1) - c.GetEndPoint(0)
            horiz = dy if abs(d.X) >= abs(d.Y) else dx
            return m(horiz), m(dz), "bbox"
        except Exception as ex:
            note(E, "bbox seccion", ex)
            return None, None, "desconocida"

    cols = sel("columnas") if "columnas" in incluir else []
    beams = sel("vigas") if "vigas" in incluir else []
    floors = sel("losas") if "losas" in incluir else []
    walls = sel("muros") if "muros" in incluir else []
    foots = sel("zapatas") if "zapatas" in incluir else []
    if not (cols or beams or floors or walls or foots):
        raise Exception("nada que exportar (marker='%s')" % marker)

    # origen: minimo de los puntos de insercion / extremos (no de las cajas,
    # que suman medio ancho de columna o de zapata y corren el 0,0).
    xs, ys = [], []
    bxs, bys = [], []
    for e in cols + beams + floors + walls + foots:
        try:
            loc = e.Location
            if loc is not None and hasattr(loc, "Point"):
                xs.append(loc.Point.X)
                ys.append(loc.Point.Y)
            elif loc is not None and hasattr(loc, "Curve"):
                for k in (0, 1):
                    q = loc.Curve.GetEndPoint(k)
                    xs.append(q.X)
                    ys.append(q.Y)
            bb = e.get_BoundingBox(None)
            bxs.extend([bb.Min.X, bb.Max.X])
            bys.extend([bb.Min.Y, bb.Max.Y])
        except Exception:
            pass
    if not xs:
        xs, ys = bxs, bys
    orig = P.get("origen", "auto")
    if orig == "auto":
        ox, oy = (min(xs) if xs else 0.0), (min(ys) if ys else 0.0)
    elif orig == "modelo":
        ox, oy = 0.0, 0.0
    else:
        ox, oy = ft(orig[0]), ft(orig[1])

    def X(v):
        return m(v - ox)

    def Y(v):
        return m(v - oy)

    # niveles involucrados
    lv_used = {}
    for e in cols + beams + floors + walls + foots:
        lv = lvl_of(e)
        if lv is not None:
            lv_used[lv.Name] = lv
    for c in cols:
        try:
            p = c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
            if p is not None and p.AsElementId() != DB.ElementId.InvalidElementId:
                t = doc.GetElement(p.AsElementId())
                lv_used[t.Name] = t
        except Exception as ex:
            note(E, "tope", ex)
    levels = sorted(lv_used.values(), key=lambda l: l.Elevation)
    ent = []
    lv_id = {}
    for i, lv in enumerate(levels):
        eid = "E%d" % i if i > 0 else "BASE"
        lv_id[lv.Name] = eid
        nxt = levels[i + 1].Elevation - lv.Elevation if i + 1 < len(levels) else None
        ent.append({"id": eid, "nombre": lv.Name, "elevacion": m(lv.Elevation),
                    "altura_est": m(nxt) if nxt is not None else None, "altura_arq": None,
                    "uso_predominante": None, "h_muro": None})

    # ejes: con marker solo los que cruzan la caja de lo exportado (+1 m); un
    # modelo con varios edificios tiene ejes que no son de este.
    ejes = []
    pad = ft(1000)
    bx0, bx1 = (min(bxs) - pad, max(bxs) + pad) if bxs else (None, None)
    by0, by1 = (min(bys) - pad, max(bys) + pad) if bys else (None, None)
    for name, g in sorted(grids_info(doc).items()):
        if marker and bx0 is not None:
            a, b = g["p0"], g["p1"]
            if g["dir"] == "X" and not (bx0 <= a.X <= bx1 and max(a.Y, b.Y) >= by0 and min(a.Y, b.Y) <= by1):
                continue
            if g["dir"] == "Y" and not (by0 <= a.Y <= by1 and max(a.X, b.X) >= bx0 and min(a.X, b.X) <= bx1):
                continue
        ejes.append({"id": name, "direccion": {"X": "Y", "Y": "X"}.get(g["dir"], "inclinado"),
                     "p1": [X(g["p0"].X), Y(g["p0"].Y)], "p2": [X(g["p1"].X), Y(g["p1"].Y)]})

    materiales = {}
    for e in cols + beams + floors + walls + foots:
        mn = mat_of(e)
        if mn and mn not in materiales:
            rec = {"nombre": mn, "fc": None, "unidad_fc": "kg/cm2", "E": None}
            try:
                mt = None
                for x in DB.FilteredElementCollector(doc).OfClass(DB.Material):
                    if element_name(x) == mn:
                        mt = x
                        break
                if mt is not None and mt.StructuralAssetId != DB.ElementId.InvalidElementId:
                    sa = doc.GetElement(mt.StructuralAssetId).GetStructuralAsset()
                    rec["clase"] = str(sa.StructuralAssetClass)
                    # UnitTypeId no tiene kgf/cm2 (verificado): se lee en MPa y se convierte (1 MPa = 10.197 kgf/cm2).
                    try:
                        rec["fc_MPa"] = round(DB.UnitUtils.ConvertFromInternalUnits(sa.ConcreteCompression, DB.UnitTypeId.Megapascals), 2)
                        rec["fc"] = round(rec["fc_MPa"] * 10.19716, 1)
                    except Exception as ex:
                        note(E, "fc " + mn, ex)
                    try:
                        rec["E_MPa"] = round(DB.UnitUtils.ConvertFromInternalUnits(sa.YoungModulus.X, DB.UnitTypeId.Megapascals), 0)
                        rec["E"] = round(rec["E_MPa"] * 10.19716, 0)
                    except Exception as ex:
                        note(E, "E " + mn, ex)
            except Exception as ex:
                note(E, "asset " + mn, ex)
            materiales[mn] = rec

    columnas = []
    secciones = {}
    for i, c in enumerate(cols):
        try:
            loc = c.Location
            b, h, org = bh_of(c)
            lb = lvl_of(c)
            lt = None
            p = c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
            if p is not None and p.AsElementId() != DB.ElementId.InvalidElementId:
                lt = doc.GetElement(p.AsElementId())
            bb = c.get_BoundingBox(None)
            tn = type_name(doc, c)
            rec = {"id": "C%d" % (i + 1), "revit_id": eidv(c.Id), "tipo": tn,
                   "seccion": {"depth": max(b, h) if b and h else h, "width": min(b, h) if b and h else b, "material": mat_of(c), "origen": org},
                   "nivel_base": lb.Name if lb else None, "nivel_tope": lt.Name if lt else None,
                   "z_base": m(bb.Min.Z), "z_tope": m(bb.Max.Z)}
            if loc is not None and hasattr(loc, "Point"):
                rec["insercion"] = [X(loc.Point.X), Y(loc.Point.Y)]
                rec["rotacion_deg"] = round(loc.Rotation * 57.29577951, 2)
            elif loc is not None and hasattr(loc, "Curve"):
                a, z = loc.Curve.GetEndPoint(0), loc.Curve.GetEndPoint(1)
                rec["insercion"] = [X(a.X), Y(a.Y)]
                rec["inclinada_hasta"] = [X(z.X), Y(z.Y), m(z.Z)]
            rec["entrepisos"] = [lv_id[l.Name] for l in levels if lb and lt and lb.Elevation <= l.Elevation < lt.Elevation]
            columnas.append(rec)
            if tn and tn not in secciones and b and h:
                secciones[tn] = {"name": tn, "depth": max(b, h), "width": min(b, h), "material": mat_of(c), "uso": "columna"}
        except Exception as ex:
            note(E, "columna %d" % eidv(c.Id), ex)

    vigas = []
    for i, v in enumerate(beams):
        try:
            c = location_curve(v)
            if c is None:
                continue
            a, z = c.GetEndPoint(0), c.GetEndPoint(1)
            b, h, org = bh_of(v)
            lv = lvl_of(v)
            tn = type_name(doc, v)
            vigas.append({"id": "V%d" % (i + 1), "revit_id": eidv(v.Id), "tipo": tn,
                          "seccion": {"depth": h, "width": b, "material": mat_of(v), "origen": org},
                          "p1": [X(a.X), Y(a.Y), m(a.Z)], "p2": [X(z.X), Y(z.Y), m(z.Z)],
                          "nivel": lv.Name if lv else None, "entrepiso": lv_id.get(lv.Name) if lv else None,
                          "longitud": m(c.Length)})
            if tn and tn not in secciones and b and h:
                secciones[tn] = {"name": tn, "depth": h, "width": b, "material": mat_of(v), "uso": "viga"}
        except Exception as ex:
            note(E, "viga %d" % eidv(v.Id), ex)

    losas = []
    for i, f in enumerate(floors):
        try:
            lv = lvl_of(f)
            contorno = None
            org = "sketch"
            try:
                sk = doc.GetElement(f.SketchId)
                loops = []
                for arr in sk.Profile:
                    pts = []
                    for cv in arr:
                        p0 = cv.GetEndPoint(0)
                        pts.append([X(p0.X), Y(p0.Y)])
                    loops.append(pts)
                loops.sort(key=lambda l: -len(l))
                contorno = loops[0] if loops else None
                huecos = loops[1:] if len(loops) > 1 else []
            except Exception as ex:
                note(E, "sketch losa %d" % eidv(f.Id), ex)
                huecos = []
            if contorno is None:
                bb = f.get_BoundingBox(None)
                contorno = [[X(bb.Min.X), Y(bb.Min.Y)], [X(bb.Max.X), Y(bb.Min.Y)], [X(bb.Max.X), Y(bb.Max.Y)], [X(bb.Min.X), Y(bb.Max.Y)]]
                org = "bbox"
            xs_ = [p[0] for p in contorno]
            ys_ = [p[1] for p in contorno]
            ap = f.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
            bb = f.get_BoundingBox(None)
            losas.append({"id": "L%d" % (i + 1), "revit_id": eidv(f.Id), "tipo_revit": type_name(doc, f),
                          "entrepiso": lv_id.get(lv.Name) if lv else None, "nivel": lv.Name if lv else None,
                          "contorno": contorno, "contorno_origen": org, "huecos": huecos,
                          "lx": round(max(xs_) - min(xs_), 3), "ly": round(max(ys_) - min(ys_), 3),
                          "z_tope": m(bb.Max.Z), "area_m2": round(ap.AsDouble() * 0.09290304, 2) if ap is not None else None,
                          "espesor": {"h_usado": round((param_mm(f, DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM) or 0) / 1000.0, 3)},
                          "tipo": "maciza", "condicion_apoyo": None, "cargas": None, "armado": None,
                          "material": mat_of(f)})
        except Exception as ex:
            note(E, "losa %d" % eidv(f.Id), ex)

    muros = []
    for i, w in enumerate(walls):
        try:
            c = location_curve(w)
            if c is None:
                continue
            a, z = c.GetEndPoint(0), c.GetEndPoint(1)
            lv = lvl_of(w)
            bb = w.get_BoundingBox(None)
            muros.append({"id": "M%d" % (i + 1), "revit_id": eidv(w.Id), "tipo_revit": type_name(doc, w),
                          "espesor": round(mm(w.Width) / 1000.0, 3), "p1": [X(a.X), Y(a.Y)], "p2": [X(z.X), Y(z.Y)],
                          "z_base": m(bb.Min.Z), "z_tope": m(bb.Max.Z), "nivel_base": lv.Name if lv else None,
                          "entrepiso": lv_id.get(lv.Name) if lv else None, "estructural": bool(w.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT).AsInteger()) if w.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT) is not None else None,
                          "material": mat_of(w)})
        except Exception as ex:
            note(E, "muro %d" % eidv(w.Id), ex)

    zapatas = []
    for i, z in enumerate(foots):
        try:
            loc = z.Location
            t = doc.GetElement(z.GetTypeId())
            wd = param_mm(t, "Width")
            ln = param_mm(t, "Length")
            th = param_mm(t, "Foundation Thickness") or param_mm(t, "Thickness")
            bb = z.get_BoundingBox(None)
            if not (wd and ln):
                wd, ln = mm(bb.Max.X - bb.Min.X), mm(bb.Max.Y - bb.Min.Y)
            if not th:
                th = mm(bb.Max.Z - bb.Min.Z)
            rec = {"id": "Z%d" % (i + 1), "revit_id": eidv(z.Id), "seccion": type_name(doc, z),
                   "dimensiones": [round(wd / 1000.0, 3), round(ln / 1000.0, 3)], "espesor": round(th / 1000.0, 3),
                   "z_tope": m(bb.Max.Z), "columna": None}
            if loc is not None and hasattr(loc, "Point"):
                rec["insercion"] = [X(loc.Point.X), Y(loc.Point.Y)]
                best = None
                for cr in columnas:
                    if "insercion" in cr:
                        d = ((cr["insercion"][0] - rec["insercion"][0]) ** 2 + (cr["insercion"][1] - rec["insercion"][1]) ** 2) ** 0.5
                        if d < 0.05 and (best is None or cr["z_base"] < best[1]):
                            best = (cr["id"], cr["z_base"])
                rec["columna"] = best[0] if best else None
            zapatas.append(rec)
        except Exception as ex:
            note(E, "zapata %d" % eidv(z.Id), ex)

    # bloque etabs: argumentos listos para el servidor fea
    base_lv = levels[0] if levels else None
    et = {"unidades": "kN, m (set_units antes de crear)",
          "set_stories": {"story_names": [l.Name for l in levels[1:]],
                          "story_heights": [m(levels[i + 1].Elevation - levels[i].Elevation) for i in range(len(levels) - 1)],
                          "base_elevation": m(base_lv.Elevation) if base_lv else 0.0},
          "define_concrete_material": [{"name": k, "fc": round(v["fc"] * 98.0665, 0) if v.get("fc") else None, "unit_weight": 23.536,
                                        "nota": "fc en kN/m2 (kg/cm2 x 98.0665); None = definir a mano"} for k, v in materiales.items()],
          "define_rect_section": [dict((kk, vv) for kk, vv in s.items() if kk != "uso") for s in secciones.values()],
          "assign_sections": {"nota": "assign_sections asigna UNA seccion a todas las columnas y UNA a todas las vigas; con varios tipos, asignar por elemento con call_oapi (FrameObj.SetSection) usando 'seccion' de cada columna/viga",
                              "column_section": next((s["name"] for s in secciones.values() if s["uso"] == "columna"), None),
                              "beam_section": next((s["name"] for s in secciones.values() if s["uso"] == "viga"), None)},
          "create_objects_by_coordinates": {"objects": []}}
    objs = et["create_objects_by_coordinates"]["objects"]
    for cr in columnas:
        if "insercion" in cr and "inclinada_hasta" not in cr:
            objs.append({"type": "line", "xs": [cr["insercion"][0], cr["insercion"][0]], "ys": [cr["insercion"][1], cr["insercion"][1]],
                         "zs": [cr["z_base"], cr["z_tope"]], "ref": cr["id"], "seccion": cr["tipo"]})
    for vr in vigas:
        objs.append({"type": "line", "xs": [vr["p1"][0], vr["p2"][0]], "ys": [vr["p1"][1], vr["p2"][1]],
                     "zs": [vr["p1"][2], vr["p2"][2]], "ref": vr["id"], "seccion": vr["tipo"]})
    for lr in losas:
        objs.append({"type": "surface", "xs": [p[0] for p in lr["contorno"]], "ys": [p[1] for p in lr["contorno"]],
                     "zs": [lr["z_tope"]] * len(lr["contorno"]), "ref": lr["id"]})
    for mr in muros:
        objs.append({"type": "surface", "xs": [mr["p1"][0], mr["p2"][0], mr["p2"][0], mr["p1"][0]],
                     "ys": [mr["p1"][1], mr["p2"][1], mr["p2"][1], mr["p1"][1]],
                     "zs": [mr["z_base"], mr["z_base"], mr["z_tope"], mr["z_tope"]], "ref": mr["id"]})

    data = {"meta": {"proyecto": P.get("proyecto") or "Proyecto Ejemplo", "fecha": datetime.date.today().isoformat(),
                     "version_codigo": "CDCRD 2026-07", "unidades": {"fuerza": "Ton", "longitud": "m"},
                     "origen_datos": "revit-mcp-tools/exportar_proyecto", "revit": doc.Application.VersionNumber,
                     "marker": marker or None, "traslacion_origen_mm": [mm(ox), mm(oy)]},
            "materiales": {"hormigon": [v for v in materiales.values()]},
            "entrepisos": ent, "ejes": ejes, "columnas": columnas, "vigas": vigas, "losas": losas, "muros": muros,
            "zapatas": zapatas, "sismo": None, "combinaciones": [], "etabs": et}
    import os
    ensure_dir(os.path.dirname(path))
    fh = io.open(path, "w", encoding="utf-8")
    fh.write(json.dumps(data, indent=1, ensure_ascii=False))
    fh.close()
    return {"ok": E["n"] == 0, "path": path, "kb": int(os.path.getsize(path) / 1024),
            "conteos": {"entrepisos": len(ent), "ejes": len(ejes), "columnas": len(columnas), "vigas": len(vigas),
                        "losas": len(losas), "muros": len(muros), "zapatas": len(zapatas), "materiales": len(materiales),
                        "secciones": len(secciones), "objetos_etabs": len(objs)},
            "origen_mm": [mm(ox), mm(oy)], "excepciones": E}
