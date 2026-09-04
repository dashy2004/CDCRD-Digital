# -*- coding: utf-8 -*-
"""material_vigas: fija el Structural Material (parametro de instancia) de las vigas.

Del pushbutton MaterialVigas, con el material como parametro en vez de
constante. Parametros:
  material:  nombre exacto del material (obligatorio).
  view_name: limitar a las vigas visibles en esa vista (opcional).
  dry_run:   True = solo cuenta cuantas cambiarian, no escribe.
Idempotente: las que ya lo tienen se cuentan aparte.
"""


def run(doc, uidoc, DB, P):
    name = P.get("material")
    if not name:
        raise Exception("falta 'material'")
    mat = None
    for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if m.Name == name:
            mat = m
            break
    if mat is None:
        raise Exception("no existe el material '%s'" % name)
    view = find_view(doc, P["view_name"]) if P.get("view_name") else None
    dry = bool(P.get("dry_run", False))
    out = {"material": name, "material_id": eidv(mat.Id), "total": 0,
           "ya_correctas": 0, "a_corregir": 0, "corregidas": 0, "sin_parametro": 0,
           "errores": {}, "dry_run": dry}
    vigas = list(collector(doc, DB.BuiltInCategory.OST_StructuralFraming, view))
    out["total"] = len(vigas)

    def work():
        for v in vigas:
            p = v.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
            if p is None:
                p = v.LookupParameter("Structural Material")
            if p is None:
                out["sin_parametro"] += 1
                continue
            actual = p.AsElementId()
            if actual is not None and eidv(actual) == out["material_id"]:
                out["ya_correctas"] += 1
                continue
            out["a_corregir"] += 1
            if dry:
                continue
            try:
                p.Set(mat.Id)
                out["corregidas"] += 1
            except Exception as ex:
                k = "%s: %s" % (type(ex).__name__, ex)
                out["errores"][k] = out["errores"].get(k, 0) + 1
    if dry:
        work()
    else:
        tx(doc, "tools: material de vigas", work)
    out["ok"] = dry or (out["corregidas"] == out["a_corregir"])
    return out
