# -*- coding: utf-8 -*-
"""familias_cargar: carga familias .rfa desde la biblioteca de Revit o rutas absolutas.

Parametros:
  familias:     lista de rutas. Relativas se resuelven contra library_root; absolutas tal cual.
                Ejemplos (biblioteca imperial de Revit 2027, verificada):
                  "Structural Columns\\Concrete\\Concrete-Rectangular-Column.rfa"
                  "Structural Framing\\Concrete\\Concrete-Rectangular Beam.rfa"
                  "Structural Foundations\\Footing-Rectangular.rfa"
  library_root: default "C:\\ProgramData\\Autodesk\\RVT 2027\\Libraries\\English-Imperial\\US".
                La rama "English\\US" es la metrica (familias con prefijo M_).
  dry_run:      True solo verifica que los archivos existan y si la familia ya esta cargada (default True).
Devuelve por familia: cargada / ya_estaba / no_existe_archivo, con sus tipos.
No recorre la biblioteca (7575 .rfa): las rutas se dan explicitas.
"""


def run(doc, uidoc, DB, P):
    import os
    dry = bool(P.get("dry_run", True))
    root = P.get("library_root") or r"C:\ProgramData\Autodesk\RVT 2027\Libraries\English-Imperial\US"
    fams = P.get("familias") or []
    if not fams:
        raise Exception("falta 'familias'")
    loaded = {}
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        loaded.setdefault(f.Name, f)
    E = errs()
    out = {"dry_run": dry, "library_root": root, "familias": [], "excepciones": E}

    def types_of(fam):
        names = []
        try:
            for sid in fam.GetFamilySymbolIds():
                names.append(element_name(doc.GetElement(sid)))
        except Exception as ex:
            note(E, "types " + fam.Name, ex)
        return sorted(n for n in names if n)

    jobs = []
    for rel in fams:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        name = os.path.splitext(os.path.basename(path))[0]
        rec = {"pedida": rel, "path": path, "nombre": name, "estado": None, "tipos": []}
        if name in loaded:
            rec["estado"] = "ya_estaba"
            rec["tipos"] = types_of(loaded[name])
        elif not os.path.isfile(path):
            rec["estado"] = "no_existe_archivo"
        else:
            rec["estado"] = "cargar" if dry else "pendiente"
            jobs.append((rec, path, name))
        out["familias"].append(rec)
    if dry:
        return out

    def work():
        for rec, path, name in jobs:
            try:
                ok = doc.LoadFamily(path)
                doc.Regenerate()
                fam = None
                for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
                    if f.Name == name:
                        fam = f
                        break
                if fam is not None:
                    rec["estado"] = "cargada"
                    rec["tipos"] = types_of(fam)
                    for sid in fam.GetFamilySymbolIds():
                        activate(doc.GetElement(sid))
                else:
                    rec["estado"] = "LoadFamily=%s pero la familia no aparece (nombre distinto al archivo?)" % ok
            except Exception as ex:
                rec["estado"] = "error: %s: %s" % (type(ex).__name__, str(ex)[:160])
    tx(doc, "tools: cargar familias", work)
    out["ok"] = all(r["estado"] in ("cargada", "ya_estaba") for r in out["familias"])
    return out
