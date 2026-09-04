# -*- coding: utf-8 -*-
"""exportar_hojas: exporta hojas a DWG y/o DXF.

Parametros:
  folder:     carpeta destino (obligatoria; se crea si falta).
  prefix:     prefijo de nombre de archivo (default el titulo del documento).
  sheets:     lista de numeros de hoja; vacio = todas las hojas.
  formats:    ["dwg","dxf"] (default ambos).
  version:    "2018" | "2013" | "2010" | "2007" (default 2018).
  merged:     True fusiona vistas en un archivo por hoja (default True).
  clean:      True borra archivos previos con el mismo prefijo (default False).
Devuelve los archivos generados por formato.
"""


def run(doc, uidoc, DB, P):
    import os
    from System.Collections.Generic import List
    folder = P.get("folder")
    if not folder:
        raise Exception("falta 'folder'")
    prefix = P.get("prefix") or doc.Title
    formats = [f.lower() for f in (P.get("formats") or ["dwg", "dxf"])]
    ver = str(P.get("version", "2018"))
    VER = {"2018": DB.ACADVersion.R2018, "2013": DB.ACADVersion.R2013, "2010": DB.ACADVersion.R2010, "2007": DB.ACADVersion.R2007}
    if ver not in VER:
        raise Exception("version no soportada: %s" % ver)
    want = set(P.get("sheets") or [])
    sheets = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet) if not want or s.SheetNumber in want]
    if not sheets:
        raise Exception("no hay hojas que exportar")
    ids = List[DB.ElementId]()
    for s in sorted(sheets, key=lambda s: s.SheetNumber):
        ids.Add(s.Id)
    out = {"folder": folder, "sheets": [s.SheetNumber for s in sheets], "files": {}}
    for fmt in formats:
        sub = os.path.join(folder, fmt.upper())
        if not os.path.isdir(sub):
            os.makedirs(sub)
        if P.get("clean"):
            for fn in os.listdir(sub):
                if fn.startswith(prefix):
                    try:
                        os.remove(os.path.join(sub, fn))
                    except Exception:
                        pass
        if fmt == "dwg":
            o = DB.DWGExportOptions()
            o.FileVersion = VER[ver]
            o.MergedViews = bool(P.get("merged", True))
            ok = doc.Export(sub, prefix, ids, o)
        elif fmt == "dxf":
            o = DB.DXFExportOptions()
            o.FileVersion = VER[ver]
            ok = doc.Export(sub, prefix, ids, o)
        else:
            raise Exception("formato no soportado: %s" % fmt)
        out["files"][fmt] = {"ok": bool(ok),
                             "list": sorted(fn for fn in os.listdir(sub) if fn.lower().endswith("." + fmt) and fn.startswith(prefix))}
    out["ok"] = all(v["ok"] for v in out["files"].values())
    return out
