# -*- coding: utf-8 -*-
"""guardar_modelo: doc.Save() sin dialogos. Correr despues de cada escritura.

Del pushbutton GuardarModelo: dos corridas de acero se perdieron por un crash
de Revit antes de guardar. El JSON de una tool describe la memoria de Revit,
no el disco. Parametros:
  save_as: ruta .rvt opcional (SaveAs con sobrescritura); si el documento
           nunca se guardo, es obligatoria.
"""


def run(doc, uidoc, DB, P):
    out = {"document": doc.Title, "path_antes": None, "path_despues": None, "ok": False}
    try:
        out["path_antes"] = doc.PathName
    except Exception:
        pass
    save_as = P.get("save_as")
    if save_as:
        opts = DB.SaveAsOptions()
        opts.OverwriteExistingFile = True
        doc.SaveAs(save_as, opts)
    else:
        if not out["path_antes"]:
            raise Exception("el documento no tiene ruta; pase save_as con la ruta .rvt")
        doc.Save()
    out["path_despues"] = doc.PathName
    out["modified"] = doc.IsModified
    out["ok"] = True
    return out
