# -*- coding: utf-8 -*-
# Helpers compartidos. Se inyectan como texto delante de cada tool, asi que
# deben ser IronPython 2.7: sin f-strings, sin anotaciones, sin print().
# Contrato de cada tool: def run(doc, uidoc, DB, P) -> dict serializable.

FT = 304.8


def eidv(element_id):
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


def element_name(el):
    if el is None:
        return None
    try:
        n = el.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None:
            return p.AsString()
    except Exception:
        pass
    return None


def type_name(doc, el):
    try:
        return element_name(doc.GetElement(el.GetTypeId()))
    except Exception:
        return None


def level_name(doc, level_id):
    try:
        lv = doc.GetElement(level_id)
        return lv.Name if lv is not None else None
    except Exception:
        return None


def mm(feet):
    return round(feet * FT, 1)


def find_view(doc, name):
    """Vista por nombre exacto (no plantilla). None si no existe."""
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if not v.IsTemplate and v.Name == name:
            return v
    return None


def active_or_named_view(doc, uidoc, name):
    if name:
        v = find_view(doc, name)
        if v is None:
            raise Exception("no existe la vista '%s'" % name)
        return v
    v = uidoc.ActiveView if uidoc is not None else doc.ActiveView
    if v is None or v.IsTemplate:
        raise Exception("no hay vista activa utilizable; pase view_name")
    return v


def collector(doc, bic, view=None):
    if view is not None:
        return DB.FilteredElementCollector(doc, view.Id).OfCategory(bic).WhereElementIsNotElementType()
    return DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType()


def tx(doc, name, fn):
    """Transaccion unica con rollback; devuelve lo que devuelva fn()."""
    t = DB.Transaction(doc, name)
    t.Start()
    try:
        r = fn()
        t.Commit()
        return r
    except Exception:
        t.RollBack()
        raise


def location_curve(el):
    loc = el.Location
    if loc is not None and hasattr(loc, "Curve"):
        return loc.Curve
    return None


def comment(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    return (p.AsString() or "") if p is not None else ""


# ----------------------------------------------------------------------
# Helpers agregados 2026-09-06 para las tools de modelado, documentacion
# y puente. Reglas que encarnan (ver ERRORES-IA del BRAIN):
#   - E-101: un except que silencia cuenta cuantas veces se activo (errs()).
#   - E-041/E-044: todo lo que una tool crea lleva marca en Comments para
#     poder encontrarlo y borrarlo (mark(), has_mark()).
#   - E-039: Duplicate() devuelve ElementType; re-leer por Id (dup_type()).
#   - E-099: Grid/Level.Create nacen sin extension vertical (fix_datum()).
# ----------------------------------------------------------------------

def ft(mm_value):
    """mm -> pies (unidad interna de Revit)."""
    return float(mm_value) / FT


def xyz_mm(x, y, z=0.0):
    return DB.XYZ(ft(x), ft(y), ft(z))


def pt_mm(p):
    return [mm(p.X), mm(p.Y), mm(p.Z)]


def m(feet):
    """pies -> metros con 3 decimales (para proyecto.json)."""
    return round(feet * FT / 1000.0, 3)


def errs():
    """Cubeta de errores contados. errs()['n'] dice cuantas excepciones se
    tragaron; 'items' guarda hasta 20 con contexto. Reportarla siempre."""
    return {"n": 0, "items": []}


def note(bucket, ctx, ex):
    bucket["n"] += 1
    if len(bucket["items"]) < 20:
        bucket["items"].append([str(ctx), "%s: %s" % (type(ex).__name__, str(ex)[:160])])


def levels_sorted(doc):
    return sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)


def find_level(doc, name):
    """Nivel por nombre exacto; None si no existe."""
    if name is None:
        return None
    for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level):
        if lv.Name == name:
            return lv
    return None


def need_level(doc, name):
    lv = find_level(doc, name)
    if lv is None:
        raise Exception("no existe el nivel '%s'; niveles: %s" % (name, [l.Name for l in levels_sorted(doc)]))
    return lv


def family_and_type(sym):
    try:
        return "%s: %s" % (sym.FamilyName, element_name(sym))
    except Exception:
        return element_name(sym)


def symbols(doc, bic):
    """FamilySymbols de una categoria, como lista."""
    return list(DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType())


def find_symbol(doc, bic, name):
    """Tipo por 'Tipo' o 'Familia: Tipo'. None si no hay."""
    if not name:
        return None
    for s in symbols(doc, bic):
        if element_name(s) == name or family_and_type(s) == name:
            return s
    return None


def need_symbol(doc, bic, name, what):
    s = find_symbol(doc, bic, name)
    if s is None:
        have = sorted(set(family_and_type(x) for x in symbols(doc, bic)))
        raise Exception("no existe el tipo de %s '%s'; disponibles: %s" % (what, name, have[:40]))
    return s


def activate(sym):
    try:
        if hasattr(sym, "IsActive") and not sym.IsActive:
            sym.Activate()
    except Exception:
        pass
    return sym


def dup_type(doc, base, new_name):
    """Duplica un tipo y lo re-lee por Id (Duplicate devuelve ElementType)."""
    return doc.GetElement(base.Duplicate(new_name).Id)


def mark(el, text):
    """Escribe Comments = text. Devuelve True si pudo."""
    try:
        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p is not None and not p.IsReadOnly:
            p.Set(text)
            return True
    except Exception:
        pass
    return False


def has_mark(el, marker):
    if not marker:
        return False
    return comment(el).startswith(marker)


def set_param(el, name, value):
    """Set por nombre o BuiltInParameter. Length en mm -> pies; ElementId y
    str tal cual; int/bool a Integer. Devuelve el valor leido de vuelta."""
    if isinstance(name, str):
        p = el.LookupParameter(name)
    else:
        p = el.get_Parameter(name)
    if p is None:
        raise Exception("no existe el parametro '%s' en %s" % (name, element_name(el)))
    if p.IsReadOnly:
        raise Exception("parametro de solo lectura: '%s'" % name)
    st = str(p.StorageType)
    if st == "Double":
        try:
            is_len = p.Definition.GetDataType() == DB.SpecTypeId.Length
        except Exception:
            is_len = True
        p.Set(ft(value) if is_len else float(value))
        return mm(p.AsDouble()) if is_len else p.AsDouble()
    if st == "Integer":
        p.Set(int(value))
        return p.AsInteger()
    if st == "ElementId":
        p.Set(value if isinstance(value, DB.ElementId) else DB.ElementId(int(value)))
        return eidv(p.AsElementId())
    p.Set(str(value))
    return p.AsString()


def param_mm(el, name):
    """Lee un parametro Length en mm; None si no existe."""
    try:
        p = el.LookupParameter(name) if isinstance(name, str) else el.get_Parameter(name)
        if p is None:
            return None
        return mm(p.AsDouble())
    except Exception:
        return None


def grids_info(doc):
    """{nombre: {"grid", "p0", "p1", "dir"}} con puntos en pies y direccion
    'X' (constante X, tipicamente letras), 'Y' (constante Y) o 'inclinado'."""
    out = {}
    for g in DB.FilteredElementCollector(doc).OfClass(DB.Grid):
        try:
            c = g.Curve
            a = c.GetEndPoint(0)
            b = c.GetEndPoint(1)
            if abs(a.X - b.X) < 1e-6:
                d = "X"
            elif abs(a.Y - b.Y) < 1e-6:
                d = "Y"
            else:
                d = "inclinado"
            out[g.Name] = {"grid": g, "p0": a, "p1": b, "dir": d}
        except Exception:
            pass
    return out


def intersect_2d(p0, p1, q0, q1):
    """Interseccion de dos rectas (no segmentos) en planta. None si paralelas."""
    x1, y1, x2, y2 = p0.X, p0.Y, p1.X, p1.Y
    x3, y3, x4, y4 = q0.X, q0.Y, q1.X, q1.Y
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def grid_point(gi, a, b):
    """Interseccion de los ejes a y b (nombres) como (x, y) en pies."""
    if a not in gi or b not in gi:
        raise Exception("eje inexistente en (%s, %s); ejes: %s" % (a, b, sorted(gi.keys())))
    r = intersect_2d(gi[a]["p0"], gi[a]["p1"], gi[b]["p0"], gi[b]["p1"])
    if r is None:
        raise Exception("los ejes %s y %s son paralelos" % (a, b))
    return r


def in_segment(r, a, b, tol_ft):
    """True si el punto (x, y) cae dentro de la caja del segmento a-b (+tol)."""
    return (min(a.X, b.X) - tol_ft <= r[0] <= max(a.X, b.X) + tol_ft and
            min(a.Y, b.Y) - tol_ft <= r[1] <= max(a.Y, b.Y) + tol_ft)


def grid_segments(gi, names, tol_ft):
    """Tramos entre intersecciones consecutivas a lo largo de cada eje de
    'names', contando solo cruces con otros ejes de 'names' que caigan dentro
    de AMBOS segmentos. Devuelve [(xy0, xy1, etiqueta)] en pies."""
    segs = []
    for g in names:
        pts = []
        for o in names:
            if o == g or gi[o]["dir"] == gi[g]["dir"]:
                continue
            r = intersect_2d(gi[g]["p0"], gi[g]["p1"], gi[o]["p0"], gi[o]["p1"])
            if r is None:
                continue
            if not in_segment(r, gi[o]["p0"], gi[o]["p1"], tol_ft) or not in_segment(r, gi[g]["p0"], gi[g]["p1"], tol_ft):
                continue
            d = gi[g]["p1"] - gi[g]["p0"]
            pts.append(((r[0] - gi[g]["p0"].X) * d.X + (r[1] - gi[g]["p0"].Y) * d.Y, r, o))
        pts.sort(key=lambda q: q[0])
        for i in range(len(pts) - 1):
            if abs(pts[i + 1][0] - pts[i][0]) > 1e-6:
                segs.append((pts[i][1], pts[i + 1][1], "%s:%s-%s" % (g, pts[i][2], pts[i + 1][2])))
    return segs


def fix_datum(doc, datum, bottom_ft=None, top_ft=None):
    """E-099: tras Grid.Create / Level.Create la extension vertical es nula y el
    datum no cruza ninguna planta. Maximiza y, si se dan, fija extremos."""
    done = []
    try:
        datum.Maximize3DExtents()
        done.append("Maximize3DExtents")
    except Exception as ex:
        done.append("Maximize3DExtents fallo: %s" % str(ex)[:80])
    if bottom_ft is not None and top_ft is not None:
        try:
            datum.SetVerticalExtents(bottom_ft, top_ft)
            done.append("SetVerticalExtents")
        except Exception as ex:
            done.append("SetVerticalExtents fallo: %s" % str(ex)[:80])
    return done


def close_xy(p, q, tol_ft):
    return abs(p.X - q.X) <= tol_ft and abs(p.Y - q.Y) <= tol_ft


def same_segment(c, a, b, tol_ft):
    """True si la curva c une a y b (en cualquier orden) en planta."""
    try:
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
    except Exception:
        return False
    return (close_xy(p0, a, tol_ft) and close_xy(p1, b, tol_ft)) or (close_xy(p0, b, tol_ft) and close_xy(p1, a, tol_ft))


def leave_view(doc, uidoc, view_ids):
    """Si la vista activa esta entre las que se van a borrar, activa otra
    antes (no se puede borrar la vista activa, y ExportImage deja activa la
    ultima exportada). Debe llamarse FUERA de la transaccion."""
    if uidoc is None:
        return None
    try:
        av = uidoc.ActiveView
        targets = set(eidv(i) for i in view_ids)
        if av is None or eidv(av.Id) not in targets:
            return None
        for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
            if not v.IsTemplate and eidv(v.Id) not in targets:
                uidoc.ActiveView = v
                return v.Name
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
            if not v.IsTemplate and eidv(v.Id) not in targets:
                uidoc.ActiveView = v
                return v.Name
    except Exception:
        pass
    return None


def ensure_dir(path):
    import os
    if path and not os.path.isdir(path):
        os.makedirs(path)
    return path


def id_list(ids):
    from System.Collections.Generic import List
    L = List[DB.ElementId]()
    for i in ids:
        L.Add(i if isinstance(i, DB.ElementId) else DB.ElementId(int(i)))
    return L


CAT = {"columnas": "OST_StructuralColumns", "vigas": "OST_StructuralFraming",
       "losas": "OST_Floors", "muros": "OST_Walls", "zapatas": "OST_StructuralFoundation",
       "acero": "OST_Rebar", "ejes": "OST_Grids", "niveles": "OST_Levels", "rooms": "OST_Rooms",
       "puertas": "OST_Doors", "ventanas": "OST_Windows", "techos": "OST_Roofs",
       "escaleras": "OST_Stairs", "laminas": "OST_Sheets", "muebles": "OST_Furniture",
       "columns": "OST_StructuralColumns", "framing": "OST_StructuralFraming",
       "floors": "OST_Floors", "walls": "OST_Walls", "foundations": "OST_StructuralFoundation"}


def bic_of(name):
    """BuiltInCategory desde alias en espanol/ingles o nombre OST_*."""
    key = CAT.get(name, name)
    try:
        return getattr(DB.BuiltInCategory, key)
    except Exception:
        raise Exception("categoria desconocida '%s'; alias: %s" % (name, sorted(CAT.keys())))
