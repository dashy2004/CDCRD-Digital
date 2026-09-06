# -*- coding: utf-8 -*-
"""exportar_pdf: exporta laminas (o vistas) a PDF con el exportador nativo de Revit.

Parametros:
  folder:     carpeta destino (se crea).
  file_name:  nombre del PDF sin extension (default "laminas"). Con combine=False
              Revit genera un archivo por lamina con su propio nombre.
  sheets:     numeros de lamina; vacio = todas las laminas.
  views:      nombres de vista adicionales (opcional).
  combine:    True un solo PDF (default True).
  gray:       True escala de grises (default False).
  paper:      "default" usa el tamano del cajetin (default); tambien "A1", "A2", "A3", "A4",
              "ANSI_D", "ANSI_E", "ARCH_D", "ARCH_E".
  hide_crop:  True oculta limites de recorte y scope boxes (default True).
Devuelve la ruta y el tamano del PDF. El PDF NO se da por bueno sin mirarlo:
rasterizar con pdftoppm (o usar ver_vista sobre la lamina) y leerlo con vision (E-102).
"""


def run(doc, uidoc, DB, P):
    import os
    folder = P.get("folder")
    if not folder:
        raise Exception("falta 'folder'")
    ensure_dir(folder)
    name = P.get("file_name") or "laminas"
    want = set(P.get("sheets") or [])
    sheets = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet) if not want or s.SheetNumber in want]
    faltan = want - set(s.SheetNumber for s in sheets)
    if faltan:
        raise Exception("no existen las laminas %s" % sorted(faltan))
    ids = [s.Id for s in sorted(sheets, key=lambda s: s.SheetNumber)]
    for vn in (P.get("views") or []):
        v = find_view(doc, vn)
        if v is None:
            raise Exception("no existe la vista '%s'" % vn)
        ids.append(v.Id)
    if not ids:
        raise Exception("no hay laminas ni vistas que exportar")
    o = DB.PDFExportOptions()
    o.Combine = bool(P.get("combine", True))
    o.FileName = name
    o.HideCropBoundaries = bool(P.get("hide_crop", True))
    o.HideScopeBoxes = bool(P.get("hide_crop", True))
    o.HideReferencePlane = True
    o.HideUnreferencedViewTags = True
    o.ColorDepth = DB.ColorDepthType.GrayScale if P.get("gray") else DB.ColorDepthType.Color
    o.RasterQuality = DB.RasterQualityType.High
    o.ZoomType = DB.ZoomType.Zoom
    o.ZoomPercentage = 100
    paper = str(P.get("paper", "default"))
    if paper.lower() != "default":
        try:
            o.PaperFormat = getattr(DB.ExportPaperFormat, "ISO_" + paper) if paper.startswith("A") else getattr(DB.ExportPaperFormat, paper)
        except Exception:
            raise Exception("paper no reconocido: %s" % paper)
    else:
        o.PaperFormat = DB.ExportPaperFormat.Default
    before = set(os.listdir(folder))
    ok = doc.Export(folder, id_list(ids), o)
    after = set(os.listdir(folder))
    new = sorted(f for f in (after - before) if f.lower().endswith(".pdf"))
    target = os.path.join(folder, name + ".pdf")
    files = []
    for fn in (new or ([name + ".pdf"] if os.path.isfile(target) else [])):
        p = os.path.join(folder, fn)
        files.append({"file": p, "kb": int(os.path.getsize(p) / 1024)})
    return {"ok": bool(ok) and len(files) > 0, "laminas": [s.SheetNumber for s in sheets], "n_vistas": len(ids),
            "files": files,
            "siguiente_paso": "rasterizar (pdftoppm -r 80) y mirar cada pagina antes de entregar (E-102)"}
