# -*- coding: utf-8 -*-
"""ver_vista: exporta vistas o laminas a PNG para que el agente las MIRE antes de entregarlas.

Regla del proyecto (ADR-0005): ninguna salida grafica se da por buena sin
haberla visto. Un PDF "existe" no significa que el plano este bien: underlay
del nivel de abajo, cotas cruzadas, vista cortada por la lamina, tags sobre
cotas, nada de eso lo detecta la API. Esta tool produce el PNG; el agente lo
abre con vision y recien entonces decide.

Parametros:
  views:       lista de nombres de vista o numeros de lamina; vacio = vista activa.
  folder:      carpeta destino (se crea). Default: %TEMP%\\revit-tools\\ver_vista.
  prefix:      prefijo del archivo (default "vista"). Revit agrega " - <tipo> - <nombre>.png".
  pixel_width: ancho en pixeles (default 2000; 4000 para laminas con texto chico).
  clean:       True borra PNG previos con el mismo prefijo en la carpeta.
Devuelve la ruta de cada PNG con su tamano en pixeles. Lo que sigue es
responsabilidad del agente: leer el PNG y describir lo que ve.
"""


def run(doc, uidoc, DB, P):
    import os
    import struct
    import tempfile
    names = P.get("views") or []
    folder = P.get("folder") or os.path.join(tempfile.gettempdir(), "revit-tools", "ver_vista")
    ensure_dir(folder)
    prefix = P.get("prefix") or "vista"
    width = int(P.get("pixel_width", 2000))
    if P.get("clean"):
        for fn in os.listdir(folder):
            if fn.startswith(prefix) and fn.lower().endswith(".png"):
                try:
                    os.remove(os.path.join(folder, fn))
                except Exception:
                    pass
    views = []
    missing = []
    if names:
        sheets = dict((s.SheetNumber, s) for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))
        for n in names:
            v = find_view(doc, n)
            if v is None and n in sheets:
                v = sheets[n]
            if v is None:
                missing.append(n)
            else:
                views.append(v)
        if missing:
            raise Exception("no existen las vistas/laminas %s" % missing)
    else:
        v = uidoc.ActiveView if uidoc is not None else doc.ActiveView
        if v is None or v.IsTemplate:
            raise Exception("no hay vista activa utilizable; pase views")
        views.append(v)
    before = set(os.listdir(folder))
    o = DB.ImageExportOptions()
    o.FilePath = os.path.join(folder, prefix)
    o.HLRandWFViewsFileType = DB.ImageFileType.PNG
    o.ShadowViewsFileType = DB.ImageFileType.PNG
    o.ZoomType = DB.ZoomFitType.FitToPage
    o.FitDirection = DB.FitDirectionType.Horizontal
    o.PixelSize = width
    o.ImageResolution = DB.ImageResolution.DPI_150
    o.ExportRange = DB.ExportRange.SetOfViews
    o.SetViewsAndSheets(id_list([v.Id for v in views]))
    doc.ExportImage(o)
    after = set(os.listdir(folder))
    new = sorted(f for f in (after - before) if f.lower().endswith(".png"))
    files = []
    for fn in new:
        path = os.path.join(folder, fn)
        w = h = None
        try:
            fh = open(path, "rb")
            head = fh.read(24)
            fh.close()
            if len(head) >= 24 and head[12:16] == b"IHDR":
                w, h = struct.unpack(">II", head[16:24])
        except Exception:
            pass
        files.append({"file": path, "px": [w, h], "kb": int(os.path.getsize(path) / 1024)})
    return {"views": [v.Name for v in views], "folder": folder, "files": files,
            "ok": len(files) >= len(views),
            "siguiente_paso": "abrir cada PNG y describir lo que se ve antes de dar la vista por buena (E-102)"}
