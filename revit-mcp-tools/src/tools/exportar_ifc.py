# -*- coding: utf-8 -*-
"""exportar_ifc: exporta el modelo a IFC (intercambio abierto, ISO 16739).

Parametros:
  folder:     carpeta destino (se crea).
  file_name:  nombre sin extension (default "modelo").
  version:    "IFC4" (default) | "IFC2x3" | "IFC4RV" (Reference View) | "IFC4DTV" (Design Transfer View).
  view:       nombre de una vista 3D; si se da, exporta solo lo visible en ella.
  base_quantities: True incluye cantidades base (default True).
  split_walls:     True parte muros y columnas por nivel (default False).
Devuelve la ruta y el tamano del IFC. La exportacion corre dentro de una
transaccion porque el exportador lo exige; no deja cambios en el modelo.
"""


def run(doc, uidoc, DB, P):
    import os
    folder = P.get("folder")
    if not folder:
        raise Exception("falta 'folder'")
    ensure_dir(folder)
    name = P.get("file_name") or "modelo"
    ver = str(P.get("version", "IFC4"))
    VER = {"IFC4": "IFC4", "IFC2x3": "IFC2x3CV2", "IFC4RV": "IFC4RV", "IFC4DTV": "IFC4DTV"}
    if ver not in VER:
        raise Exception("version debe ser una de %s" % sorted(VER.keys()))
    o = DB.IFCExportOptions()
    try:
        o.FileVersion = getattr(DB.IFCVersion, VER[ver])
    except Exception:
        o.FileVersion = DB.IFCVersion.IFC4
    o.ExportBaseQuantities = bool(P.get("base_quantities", True))
    o.WallAndColumnSplitting = bool(P.get("split_walls", False))
    if P.get("view"):
        v = find_view(doc, P["view"])
        if v is None:
            raise Exception("no existe la vista '%s'" % P["view"])
        o.FilterViewId = v.Id
    path = os.path.join(folder, name + ".ifc")

    def work():
        return doc.Export(folder, name, o)
    ok = tx(doc, "tools: exportar ifc", work)
    exists = os.path.isfile(path)
    return {"ok": bool(ok) and exists, "file": path if exists else None,
            "kb": int(os.path.getsize(path) / 1024) if exists else None, "version": ver}
