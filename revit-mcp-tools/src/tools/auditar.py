# -*- coding: utf-8 -*-
"""auditar: radiografia del modelo antes o despues de que un agente escriba en el.

Solo lectura. Devuelve lo que un revisor mira primero y una API no muestra
sin pedirlo: advertencias agrupadas, niveles sin planta, ejes que no cruzan
ninguna planta (E-099), elementos sin nivel, rooms sin colocar / sin cerrar /
que se fugan (area > umbral), vistas que no estan en ninguna lamina, y el
inventario de lo que dejo marcado un agente (Comments con prefijo).

Parametros:
  marker:        prefijo de Comments a inventariar (default "AGENTE:").
  umbral_m2:     area a partir de la cual un room se considera fuga (default 150).
  top_warnings:  cuantos grupos de advertencia listar (default 12).
  categorias:    alias a contar (default columnas, vigas, losas, muros, zapatas, acero, ejes, niveles, rooms, puertas, ventanas).
"""


def run(doc, uidoc, DB, P):
    marker = P.get("marker", "AGENTE:")
    umbral = float(P.get("umbral_m2", 150.0))
    topn = int(P.get("top_warnings", 12))
    cats = P.get("categorias") or ["columnas", "vigas", "losas", "muros", "zapatas", "acero", "ejes", "niveles", "rooms", "puertas", "ventanas"]
    E = errs()
    out = {"document": doc.Title, "modified": None, "warnings": {}, "niveles": [], "ejes": {},
           "conteos": {}, "sin_nivel": {}, "rooms": {}, "vistas": {}, "marcados": {}, "excepciones": E}
    try:
        out["modified"] = doc.IsModified
    except Exception as ex:
        note(E, "modified", ex)

    # --- advertencias agrupadas ---
    try:
        ws = doc.GetWarnings()
        groups = {}
        for w in ws:
            try:
                d = w.GetDescriptionText()
                g = groups.setdefault(d, {"n": 0, "ids": []})
                g["n"] += 1
                if len(g["ids"]) < 5:
                    g["ids"].extend([eidv(i) for i in w.GetFailingElements()][:2])
            except Exception as ex:
                note(E, "warning", ex)
        top = sorted(groups.items(), key=lambda kv: -kv[1]["n"])[:topn]
        out["warnings"] = {"total": len(ws), "grupos": len(groups),
                           "top": [{"texto": k[:160], "n": v["n"], "ids": v["ids"]} for k, v in top]}
    except Exception as ex:
        note(E, "warnings", ex)

    # --- niveles y plantas ---
    plans = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan) if not v.IsTemplate]
    by_level = {}
    for v in plans:
        try:
            lid = eidv(v.GenLevel.Id) if v.GenLevel is not None else None
            by_level.setdefault(lid, []).append([v.Name, str(v.ViewType)])
        except Exception as ex:
            note(E, "plan " + v.Name, ex)
    levels = levels_sorted(doc)
    for lv in levels:
        out["niveles"].append({"name": lv.Name, "elevation_mm": mm(lv.Elevation),
                               "plantas": by_level.get(eidv(lv.Id), [])})

    # --- ejes: cuantos son visibles en cada planta (E-099) ---
    try:
        gi = grids_info(doc)
        out["ejes"] = {"total": len(gi), "por_direccion": {}, "visibles_por_planta": {}}
        for k, v in gi.items():
            out["ejes"]["por_direccion"][v["dir"]] = out["ejes"]["por_direccion"].get(v["dir"], 0) + 1
        for v in plans[:12]:
            try:
                n = DB.FilteredElementCollector(doc, v.Id).OfClass(DB.Grid).GetElementCount()
                out["ejes"]["visibles_por_planta"][v.Name] = n
            except Exception as ex:
                note(E, "grids en " + v.Name, ex)
        invisibles = [k for k, n in out["ejes"]["visibles_por_planta"].items() if n < len(gi)]
        out["ejes"]["plantas_con_ejes_faltantes"] = invisibles
    except Exception as ex:
        note(E, "ejes", ex)

    # --- conteos y elementos sin nivel ---
    for alias in cats:
        try:
            bic = bic_of(alias)
            els = list(collector(doc, bic))
            out["conteos"][alias] = len(els)
            if alias in ("columnas", "vigas", "losas", "muros", "zapatas"):
                sin = 0
                for e in els:
                    try:
                        lid = e.LevelId
                        if lid == DB.ElementId.InvalidElementId:
                            # vigas y columnas inclinadas no usan LevelId: leen el nivel de referencia
                            p = e.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                            if p is None:
                                p = e.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
                            lid = p.AsElementId() if p is not None else lid
                        if lid == DB.ElementId.InvalidElementId:
                            sin += 1
                    except Exception as ex:
                        note(E, "LevelId", ex)
                out["sin_nivel"][alias] = sin
        except Exception as ex:
            note(E, "conteo " + alias, ex)

    # --- rooms ---
    try:
        rooms = list(collector(doc, DB.BuiltInCategory.OST_Rooms))
        r = {"total": len(rooms), "sin_colocar": 0, "sin_cerrar": 0, "fugas": [], "area_total_m2": 0.0}
        for rm in rooms:
            try:
                a = rm.Area * 0.09290304
                if rm.Location is None:
                    r["sin_colocar"] += 1
                elif a <= 1e-6:
                    r["sin_cerrar"] += 1
                else:
                    r["area_total_m2"] += a
                    if a > umbral:
                        r["fugas"].append({"id": eidv(rm.Id), "name": element_name(rm), "area_m2": round(a, 1),
                                           "level": level_name(doc, rm.LevelId)})
            except Exception as ex:
                note(E, "room", ex)
        r["area_total_m2"] = round(r["area_total_m2"], 1)
        out["rooms"] = r
    except Exception as ex:
        note(E, "rooms", ex)

    # --- vistas y laminas ---
    try:
        sheets = list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))
        placed = set()
        for s in sheets:
            try:
                for vid in s.GetAllPlacedViews():
                    placed.add(eidv(vid))
            except Exception as ex:
                note(E, "sheet " + s.SheetNumber, ex)
        views = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
                 if not v.IsTemplate and v.ViewType not in (DB.ViewType.DrawingSheet, DB.ViewType.ProjectBrowser,
                                                             DB.ViewType.SystemBrowser, DB.ViewType.Undefined,
                                                             DB.ViewType.Internal, DB.ViewType.Schedule)]
        fuera = [v.Name for v in views if eidv(v.Id) not in placed]
        out["vistas"] = {"total": len(views), "laminas": len(sheets), "en_lamina": len(placed),
                         "fuera_de_lamina": fuera[:60], "n_fuera": len(fuera),
                         "laminas_lista": sorted([s.SheetNumber + " " + s.Name for s in sheets])[:60]}
    except Exception as ex:
        note(E, "vistas", ex)

    # --- lo que dejo marcado un agente ---
    try:
        mk = {}
        for alias in ("columnas", "vigas", "losas", "muros", "zapatas", "acero", "ejes", "niveles", "rooms"):
            n = 0
            for e in collector(doc, bic_of(alias)):
                try:
                    if has_mark(e, marker):
                        n += 1
                except Exception as ex:
                    note(E, "mark", ex)
            if n:
                mk[alias] = n
        out["marcados"] = {"marker": marker, "por_categoria": mk, "total": sum(mk.values())}
    except Exception as ex:
        note(E, "marcados", ex)
    out["ok"] = E["n"] == 0
    return out
