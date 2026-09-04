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
