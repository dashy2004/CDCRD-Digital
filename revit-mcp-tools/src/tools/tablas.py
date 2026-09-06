# -*- coding: utf-8 -*-
"""tablas: crea tablas de planificacion (schedules) por categoria y las exporta a CSV.

Parametros:
  tablas:  lista de {"name": "TABLA DE COLUMNAS", "category": "columnas",
                     "fields": ["Type", "Base Level", "Top Level", "Count"],
                     "sort": "Type", "itemize": false, "total": true}.
           category acepta alias (columnas, vigas, losas, muros, zapatas, rooms,
           puertas, ventanas...) o un OST_*. "multi" = tabla multicategoria.
           Los nombres de campo son los que Revit muestra (idioma de la instalacion).
  export_folder: si se da, exporta cada tabla a <folder>/<name>.csv.
  replace:       True borra la tabla previa con el mismo nombre.
  dry_run:       True solo informa (default True). En dry_run devuelve, por
                 categoria, los campos disponibles: util para armar 'fields'.
Devuelve por tabla los campos agregados, los que no existen, filas del cuerpo y CSV.
"""


def run(doc, uidoc, DB, P):
    specs = P.get("tablas") or []
    if not specs:
        raise Exception("falta 'tablas'")
    dry = bool(P.get("dry_run", True))
    folder = P.get("export_folder")
    existing = {}
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        if not v.IsTemplate:
            existing.setdefault(v.Name, v)
    E = errs()
    out = {"dry_run": dry, "plan": [], "creadas": [], "existian": [], "errores": [], "excepciones": E}

    def cat_id(alias):
        if alias == "multi":
            return DB.ElementId.InvalidElementId
        return DB.ElementId(bic_of(alias))

    def available(alias):
        # tabla temporal para leer los campos disponibles; se descarta por rollback.
        names = []
        t = DB.Transaction(doc, "tools: campos disponibles")
        t.Start()
        try:
            vs = DB.ViewSchedule.CreateSchedule(doc, cat_id(alias))
            for sf in vs.Definition.GetSchedulableFields():
                try:
                    names.append(sf.GetName(doc))
                except Exception as ex:
                    note(E, "field name", ex)
        finally:
            t.RollBack()
        return sorted(set(names))

    jobs = []
    for spec in specs:
        name = spec.get("name")
        alias = spec.get("category")
        if not name or not alias:
            raise Exception("cada tabla necesita 'name' y 'category'")
        st = "existe" if name in existing else "crear"
        if st == "existe" and P.get("replace"):
            st = "reemplazar"
        item = {"name": name, "category": alias, "accion": st, "fields": spec.get("fields") or []}
        if dry:
            try:
                item["campos_disponibles"] = available(alias)
            except Exception as ex:
                note(E, "disponibles " + alias, ex)
        out["plan"].append(item)
        jobs.append((spec, name, alias, st))
    if dry:
        return out
    if folder:
        ensure_dir(folder)
    out["vista_activa_cambiada_a"] = leave_view(doc, uidoc, [existing[n].Id for _, n, _, st in jobs if st == "reemplazar"])

    def work():
        for spec, name, alias, st in jobs:
            try:
                if st == "existe":
                    out["existian"].append(name)
                    continue
                if st == "reemplazar":
                    doc.Delete(existing[name].Id)
                vs = DB.ViewSchedule.CreateSchedule(doc, cat_id(alias))
                vs.Name = name
                d = vs.Definition
                d.IsItemized = bool(spec.get("itemize", False))
                d.ShowGrandTotal = bool(spec.get("total", True))
                sfs = {}
                for sf in d.GetSchedulableFields():
                    try:
                        sfs.setdefault(sf.GetName(doc), sf)
                    except Exception as ex:
                        note(E, "field name", ex)
                added = []
                missing = []
                fields_by_name = {}
                for fname in (spec.get("fields") or []):
                    if fname in sfs:
                        f = d.AddField(sfs[fname])
                        fields_by_name[fname] = f
                        added.append(fname)
                    else:
                        missing.append(fname)
                sort = spec.get("sort")
                if sort and sort in fields_by_name:
                    d.AddSortGroupField(DB.ScheduleSortGroupField(fields_by_name[sort].FieldId))
                doc.Regenerate()
                rows = None
                try:
                    rows = vs.GetTableData().GetSectionData(DB.SectionType.Body).NumberOfRows
                except Exception as ex:
                    note(E, "rows " + name, ex)
                rec = {"name": name, "id": eidv(vs.Id), "campos": added, "campos_inexistentes": missing, "filas": rows}
                out["creadas"].append(rec)
            except Exception as ex:
                out["errores"].append([name, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: tablas", work)
    # la exportacion va fuera de la transaccion: escribe en disco, no en el modelo.
    if folder:
        for rec in out["creadas"]:
            try:
                vs = doc.GetElement(DB.ElementId(rec["id"]))
                o = DB.ViewScheduleExportOptions()
                o.FieldDelimiter = ","
                o.Title = False
                o.HeadersFootersBlanks = False
                vs.Export(folder, rec["name"] + ".csv", o)
                rec["csv"] = folder + "\\" + rec["name"] + ".csv"
            except Exception as ex:
                note(E, "csv " + rec["name"], ex)
    out["ok"] = not out["errores"]
    return out
