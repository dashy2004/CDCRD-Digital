# -*- coding: utf-8 -*-
"""rooms: crea rooms en todos los recintos cerrados de un nivel, los nombra por punto e informa areas.

Parametros:
  level:       nombre de nivel; vacio = todos (solo para el informe; crear exige un nivel).
  create:      True crea rooms con NewRooms2 en cada recinto cerrado del nivel que no tenga uno.
  names:       lista de {"name": "Sala", "number": "101", "x_mm": .., "y_mm": ..}: el room que
               contiene ese punto recibe nombre y numero.
  umbral_m2:   area a partir de la cual se marca 'fuga' (default 150): un room que se fuga
               dice donde no cierra un muro, no es basura.
  dry_run:     True no escribe (default True).
Devuelve por room: id, nombre, numero, nivel, area_m2, centro, y las banderas
sin_colocar (no tiene ubicacion), sin_cerrar (area 0) y fuga (area > umbral).
"""


def run(doc, uidoc, DB, P):
    dry = bool(P.get("dry_run", True))
    lname = P.get("level") or ""
    lv = need_level(doc, lname) if lname else None
    umbral = float(P.get("umbral_m2", 150.0))
    names = P.get("names") or []
    E = errs()
    out = {"dry_run": dry, "level": lname or None, "creados": 0, "nombrados": [], "no_encontrados": [],
           "rooms": [], "resumen": {}, "excepciones": E}

    def create_and_name():
        n = 0
        if P.get("create"):
            if lv is None:
                raise Exception("create=True exige 'level'")
            ids = doc.Create.NewRooms2(lv)
            n = len(list(ids)) if ids is not None else 0
            doc.Regenerate()
        if names:
            rooms = [r for r in collector(doc, DB.BuiltInCategory.OST_Rooms) if lv is None or r.LevelId == lv.Id]
            for spec in names:
                z = (lv.Elevation if lv is not None else 0.0) + ft(300)
                pt = DB.XYZ(ft(spec.get("x_mm", 0)), ft(spec.get("y_mm", 0)), z)
                hit = None
                for r in rooms:
                    try:
                        if r.Location is not None and r.IsPointInRoom(pt):
                            hit = r
                            break
                    except Exception as ex:
                        note(E, "IsPointInRoom", ex)
                if hit is None:
                    out["no_encontrados"].append(spec)
                    continue
                try:
                    if spec.get("name"):
                        set_param(hit, DB.BuiltInParameter.ROOM_NAME, spec["name"])
                    if spec.get("number"):
                        set_param(hit, DB.BuiltInParameter.ROOM_NUMBER, str(spec["number"]))
                    out["nombrados"].append([eidv(hit.Id), spec.get("name"), spec.get("number")])
                except Exception as ex:
                    note(E, "nombrar " + str(spec.get("name")), ex)
        return n

    if not dry and (P.get("create") or names):
        out["creados"] = tx(doc, "tools: rooms", create_and_name)

    res = {"total": 0, "sin_colocar": 0, "sin_cerrar": 0, "fugas": 0, "area_m2": 0.0}
    for r in collector(doc, DB.BuiltInCategory.OST_Rooms):
        try:
            if lv is not None and r.LevelId != lv.Id:
                continue
            a = r.Area * 0.09290304
            row = {"id": eidv(r.Id), "name": element_name(r), "number": None, "level": level_name(doc, r.LevelId),
                   "area_m2": round(a, 2), "centro_mm": None, "sin_colocar": r.Location is None,
                   "sin_cerrar": (r.Location is not None and a <= 1e-6), "fuga": a > umbral}
            try:
                row["number"] = r.Number
            except Exception:
                pass
            try:
                if r.Location is not None:
                    p = r.Location.Point
                    row["centro_mm"] = [mm(p.X), mm(p.Y)]
            except Exception as ex:
                note(E, "centro", ex)
            res["total"] += 1
            res["area_m2"] += a
            if row["sin_colocar"]:
                res["sin_colocar"] += 1
            if row["sin_cerrar"]:
                res["sin_cerrar"] += 1
            if row["fuga"]:
                res["fugas"] += 1
            out["rooms"].append(row)
        except Exception as ex:
            note(E, "room", ex)
    res["area_m2"] = round(res["area_m2"], 1)
    out["resumen"] = res
    out["ok"] = E["n"] == 0
    return out
